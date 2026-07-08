"""Team feedback ABOUT THE TOOL itself — bugs, ideas, "this is confusing".

Distinct from src/feedback.py (that logs listing *sales* performance). Any
signed-in member submits a note; the owner/managers see the whole list and tick
items resolved. Backed by data/app.db (appdb), so it lives with the team system.
"""
from datetime import datetime, timezone

from src import appdb

CATEGORIES = ["idea", "bug", "question", "other"]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def submit(user_id, author, message, category="other"):
    """Record one piece of feedback. Returns the new id (or None if empty)."""
    message = (message or "").strip()
    if not message:
        return None
    cat = category if category in CATEGORIES else "other"
    return appdb.execute(
        "INSERT INTO tool_feedback (created_at, user_id, author, category, "
        "message, status) VALUES (?,?,?,?,?, 'open')",
        (_now(), user_id, author or "", cat, message[:2000]))


def list_all():
    """All feedback, open first (newest within each group)."""
    return appdb.q("SELECT * FROM tool_feedback "
                   "ORDER BY (status='resolved') ASC, id DESC")


def list_by_user(user_id):
    return appdb.q("SELECT * FROM tool_feedback WHERE user_id=? ORDER BY id DESC",
                   (user_id,))


def set_resolved(fb_id, resolved, resolver_name=None):
    """Mark one item resolved (True) or reopen it (False)."""
    if resolved:
        appdb.execute("UPDATE tool_feedback SET status='resolved', resolved_by=?, "
                      "resolved_at=? WHERE id=?", (resolver_name or "", _now(), fb_id))
    else:
        appdb.execute("UPDATE tool_feedback SET status='open', resolved_by=NULL, "
                      "resolved_at=NULL WHERE id=?", (fb_id,))


def get(fb_id):
    return appdb.q("SELECT * FROM tool_feedback WHERE id=?", (fb_id,), one=True)


def counts():
    rows = appdb.q("SELECT status, COUNT(*) n FROM tool_feedback GROUP BY status")
    d = {r["status"]: r["n"] for r in rows}
    return {"open": d.get("open", 0), "resolved": d.get("resolved", 0)}
