"""Activity logging — records ACTIONS INSIDE THIS DASHBOARD only.

Never records keystrokes, screens, browser history, passwords, cookies, tokens,
or anything outside the app. For team workflow + quality review, not surveillance.
"""
import csv
from datetime import date, datetime, timezone

from src import appdb

# The event vocabulary (documented; not enforced, so new events don't break logging).
EVENT_TYPES = {
    "AUTH_LOGIN_SUCCESS", "AUTH_LOGIN_FAILED", "AUTH_LOGOUT",
    "WORKSPACE_BUILD", "WORKSPACE_SAVE", "WORKSPACE_EXPORT_JSON",
    "SPY_SEARCH", "KEYWORD_ANALYZE", "KEYWORD_EXPAND", "SHOULD_I_SELL",
    "SUPPLIER_MATCH", "SUPPLIER_CSV_UPLOAD", "SUPPLIER_USE", "SUPPLIER_REJECT",
    "LISTING_DRAFT_EDIT", "PUBLISH_GATE_CHECK", "MANAGER_APPROVE", "MANAGER_REJECT",
    "PDF_EXPORT_MANAGER", "PDF_EXPORT_SELLER", "PDF_EXPORT_DESIGNER",
    "FEEDBACK_ADD", "FEEDBACK_UPDATE_DAY3", "FEEDBACK_UPDATE_DAY7",
    "TASK_CREATE", "TASK_ASSIGN", "TASK_STATUS_CHANGE", "TASK_REVIEW_APPROVE",
    "TASK_REVIEW_REJECT",
    "DAILY_RUN_START", "DAILY_RUN_COMPLETE", "DAILY_RUN_FAILED",
}

# Field names we refuse to ever store, defensively.
_FORBIDDEN = ("password", "secret", "token", "cookie", "api_key", "authorization")


def _clean(v, n=300):
    if v is None:
        return None
    v = str(v)
    low = v.lower()
    if any(f in low for f in _FORBIDDEN):
        return "[redacted]"
    return v[:n]


def log(event_type, user=None, module=None, action=None, entity_type=None,
        entity_id=None, keyword=None, product_mode=None, summary=None,
        ip=None, user_agent=None, success=True, error=None):
    """Record one dashboard action. `user` is an auth user dict or None (SYSTEM)."""
    try:
        appdb.init_db()
        appdb.execute(
            "INSERT INTO activity_logs (timestamp, user_id, user_email, user_role, "
            "event_type, module, action, entity_type, entity_id, keyword, "
            "product_mode, summary, ip_address, user_agent, success, error_message) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),
             (user or {}).get("user_id"), (user or {}).get("email") or "SYSTEM",
             (user or {}).get("role") or "SYSTEM",
             event_type, module, action, entity_type, _clean(entity_id, 80),
             _clean(keyword, 120), product_mode, _clean(summary),
             _clean(ip, 60), _clean(user_agent, 200), 1 if success else 0,
             _clean(error, 300)))
    except Exception:  # noqa: BLE001 - logging must never break a request
        pass


def list_events(user_id=None, event_type=None, module=None, keyword=None,
                since=None, until=None, limit=200):
    where, params = [], []
    if user_id:
        where.append("user_id = ?"); params.append(user_id)
    if event_type:
        where.append("event_type = ?"); params.append(event_type)
    if module:
        where.append("module = ?"); params.append(module)
    if keyword:
        where.append("keyword LIKE ?"); params.append(f"%{keyword}%")
    if since:
        where.append("timestamp >= ?"); params.append(since)
    if until:
        where.append("timestamp <= ?"); params.append(until)
    sql = "SELECT * FROM activity_logs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY event_id DESC LIMIT ?"
    params.append(limit)
    return appdb.q(sql, tuple(params))


COLS = ["event_id", "timestamp", "user_email", "user_role", "event_type",
        "module", "action", "entity_type", "entity_id", "keyword",
        "product_mode", "summary", "ip_address", "success", "error_message"]


def export_csv(path):
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    rows = list_events(limit=100000)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path, len(rows)


def summary_today():
    today = date.today().isoformat()
    rows = appdb.q("SELECT event_type, user_email FROM activity_logs "
                   "WHERE timestamp >= ?", (today,))
    def n(*types):
        return sum(1 for r in rows if r["event_type"] in types)
    return {
        "active_users": len({r["user_email"] for r in rows if r["user_email"] != "SYSTEM"}),
        "workspaces_built": n("WORKSPACE_BUILD"),
        "spy_searches": n("SPY_SEARCH"),
        "supplier_checks": n("SUPPLIER_MATCH", "SUPPLIER_USE"),
        "listing_edits": n("LISTING_DRAFT_EDIT"),
        "pdf_exports": n("PDF_EXPORT_MANAGER", "PDF_EXPORT_SELLER", "PDF_EXPORT_DESIGNER"),
        "approvals": n("MANAGER_APPROVE"),
        "total_events": len(rows),
    }
