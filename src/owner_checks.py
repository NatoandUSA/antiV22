"""Owner Check + owner-set price persistence (SQLite via src/appdb.py).

Studio (src/contracts.py, called from src/interactive.py's studio()) compiles
a fresh, deterministic package on every visit -- everything about a listing
is recomputed from real ranked/captured data each time. This module is the
one deliberate exception: which Owner Check fields have actually been
verified by a human, with what real value, and any real owner-set price.
Without persisting this, publish_ready could never reach YES through the
UI at all, since every compile would start from zero every time.
"""
from datetime import datetime, timezone

from src import appdb


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _kw(keyword):
    return (keyword or "").strip().lower()


def get_checks(keyword, mode):
    """{field: {value, verified, note, updated_at, updated_by}} for every
    saved check on this keyword+mode. Fields never saved simply aren't in
    the returned dict -- callers treat "not present" as unverified."""
    rows = appdb.q(
        "SELECT field, value, verified, note, updated_at, updated_by "
        "FROM owner_checks WHERE keyword=? AND mode=?",
        (_kw(keyword), mode))
    return {r["field"]: {"value": r["value"], "verified": bool(r["verified"]),
                         "note": r["note"] or "", "updated_at": r["updated_at"],
                         "updated_by": r["updated_by"] or ""}
            for r in rows}


def save_check(keyword, mode, field, value="", verified=False, note="",
               updated_by=""):
    """Create or update one Owner Check field. Verified=True with an empty
    value is allowed for fields with no bound fact (Exact SKU / Supplier,
    Design-Level IP QA) -- the field, not this function, decides whether a
    value is meaningful for it."""
    appdb.execute(
        "INSERT INTO owner_checks "
        "(keyword, mode, field, value, verified, note, updated_by, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?) "
        "ON CONFLICT(keyword, mode, field) DO UPDATE SET "
        "value=excluded.value, verified=excluded.verified, "
        "note=excluded.note, updated_by=excluded.updated_by, "
        "updated_at=excluded.updated_at",
        (_kw(keyword), mode, field, (value or "").strip(), int(bool(verified)),
         (note or "").strip(), updated_by, _now()))


def get_price(keyword, mode):
    """{price, currency, updated_at, updated_by} or None if never set."""
    return appdb.q(
        "SELECT price, currency, updated_at, updated_by FROM owner_prices "
        "WHERE keyword=? AND mode=?",
        (_kw(keyword), mode), one=True)


def save_price(keyword, mode, price, currency="USD", updated_by=""):
    appdb.execute(
        "INSERT INTO owner_prices "
        "(keyword, mode, price, currency, updated_by, updated_at) "
        "VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(keyword, mode) DO UPDATE SET "
        "price=excluded.price, currency=excluded.currency, "
        "updated_by=excluded.updated_by, updated_at=excluded.updated_at",
        (_kw(keyword), mode, float(price), currency, updated_by, _now()))
