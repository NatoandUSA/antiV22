"""Research candidates + YTuong import log — the EXECUTION pipeline.

YTuong/HeyEtsy finds the market data; we IMPORT it here, auto-classify product-fit,
guess the product mode, and move each idea through the research queue toward a
manager-approved MANUAL publish. Nothing is ever auto-published.

Stored as JSON (gitignored runtime data):
  data/research/saved_candidates.json   — the research queue
  data/imports/ytuong_imports.json      — raw import log
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

CAND_FILE = Path("data/research/saved_candidates.json")
IMPORT_FILE = Path("data/imports/ytuong_imports.json")

SOURCES = ["YTuong", "HeyEtsy", "Etsy", "manual", "saved_shop"]

# The research-queue pipeline (idea -> researched -> drafted -> reviewed ->
# manual publish -> Day 3/7 -> scale/kill). Order matters for the UI.
STATUSES = ["NEW_IDEA", "RESEARCHING", "SUPPLIER_CHECK", "COMPETITOR_AUDIT",
            "DESIGN_TASK", "LISTING_DRAFT", "MANAGER_REVIEW",
            "READY_FOR_MANUAL_PUBLISH", "PUBLISHED_MANUALLY", "DAY_3_CHECK",
            "DAY_7_DECISION", "SCALE", "KILL", "BLOCKED"]

IMPORT_KINDS = {
    "product_idea": "Product idea",
    "competitor_listing": "Competitor listing",
    "shop_to_watch": "Shop to watch",
    "keyword_to_track": "Keyword to track",
    "task": "Task",
}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(p):
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return []
    return []


def _save(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def _next_id(rows):
    return max([r.get("id", 0) for r in rows], default=0) + 1


def kw_from_url(url):
    """Best-effort keyword from an Etsy/YTuong listing URL slug."""
    m = re.search(r"/listing/\d+/([a-z0-9\-]+)", url or "", re.I)
    if m:
        return " ".join(m.group(1).replace("-", " ").split()[:6])
    return ""


def import_candidate(kind, source, value, mode=None, note="", by=None):
    """Import one item from YTuong/HeyEtsy/Etsy/manual. Logs the raw import, then
    creates a saved candidate: classifies product-fit, guesses the product mode,
    and drops it into the research queue at NEW_IDEA. Returns the candidate dict."""
    from src import product_fit as pf
    from src.discover import matches_mode
    value = (value or "").strip()
    is_url = value.lower().startswith("http")
    kw = kw_from_url(value) if is_url else value
    guess = mode if mode in ("pod", "embroidery") else (
        "embroidery" if matches_mode((kw or "").lower(), "embroidery") else "pod")
    fit = pf.classify(kw or value, None)

    imports = _load(IMPORT_FILE)
    imports.append({"id": _next_id(imports), "at": _now(), "kind": kind,
                    "source": source, "value": value, "note": note, "by": by})
    _save(IMPORT_FILE, imports)

    rows = _load(CAND_FILE)
    cand = {
        "id": _next_id(rows), "created_at": _now(),
        "title": kw or value, "keyword": kw or "",
        "source": source if source in SOURCES else "manual",
        "source_url": value if is_url else "", "kind": kind,
        "product_mode": guess, "fit_status": fit["status"],
        "launchable": bool(fit["launchable"]), "assigned_to": None,
        "status": "NEW_IDEA", "next_action": "Classify + assign research",
        "due_date": "", "manager_decision": "", "note": note, "by": by,
    }
    rows.append(cand)
    _save(CAND_FILE, rows)
    return cand


def list_candidates(status=None, assigned_to=None):
    rows = _load(CAND_FILE)
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if assigned_to is not None:
        rows = [r for r in rows if r.get("assigned_to") == assigned_to]
    return sorted(rows, key=lambda r: r.get("id", 0), reverse=True)


def get_candidate(cid):
    return next((r for r in _load(CAND_FILE) if r.get("id") == cid), None)


def update_candidate(cid, **fields):
    rows = _load(CAND_FILE)
    for r in rows:
        if r.get("id") == cid:
            for k, v in fields.items():
                if v is not None:
                    r[k] = v
            r["updated_at"] = _now()
            _save(CAND_FILE, rows)
            return r
    return None


def delete_candidate(cid):
    rows = [r for r in _load(CAND_FILE) if r.get("id") != cid]
    _save(CAND_FILE, rows)


def counts_by_status():
    d = {}
    for r in _load(CAND_FILE):
        d[r.get("status")] = d.get(r.get("status"), 0) + 1
    return d


def imported_today():
    # Bucket by the TEAM's day (ICT), not UTC: records store `at` in UTC, so an
    # early-morning ICT import lands on the previous UTC day and would miscount.
    from datetime import datetime
    from src.timestamp import tz
    _tz = tz()
    today = datetime.now(_tz).strftime("%Y-%m-%d")

    def _day(at):
        try:
            dt = datetime.fromisoformat(at)
            return (dt.astimezone(_tz) if dt.tzinfo else dt).strftime("%Y-%m-%d")
        except ValueError:
            return (at or "")[:10]

    return [r for r in _load(IMPORT_FILE) if _day(r.get("at") or "") == today]
