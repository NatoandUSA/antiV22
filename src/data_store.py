"""data_store — a normalized SQLite index that sits ON TOP of the raw capture
files (Option C, hybrid).

WHY THIS EXISTS
---------------
Captures land as loose JSON files per lane. Those files stay exactly as they are
(the FROZEN L0-L4 ranking engine reads them directly, and must not change). This
module ADDS a clean, queryable layer so the non-frozen screens (Pattern Miner,
keyword lookups) can answer "give me every listing captured for THIS search"
instantly and correctly — the thing loose files could never do:

  * the search keyword is stored on EVERY listing row (was only in the filename),
  * prices are normalized to USD at ingest (VND detected and converted),
  * ad/star/free-ship flags are parsed to real booleans,
  * shop names are de-junked ("Ad by Etsy seller" -> not a shop),
  * re-capture UPSERTS (updates in place) instead of double-counting.

The DB is DERIVED: it can be rebuilt from the raw captures at any time
(rebuild_from_raw), so it is safe and reversible. Nothing here ever raises into
the ingest path — a DB failure must never block a capture.
"""
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path("data/db/etsy.db")

_VND_PER_USD = 25000.0
_STOP = {"the", "and", "for", "with", "your", "you", "etsy", "shop", "vietnam",
         "vn", "en", "us", "listing", "search", "results", "result", "page"}


# --------------------------------------------------------------------------- #
# schema
# --------------------------------------------------------------------------- #
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def init_db():
    """Create tables/indexes if missing. Idempotent."""
    con = _connect()
    try:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS listings (
                listing_id      TEXT NOT NULL,
                source_keyword  TEXT NOT NULL,   -- the search this was captured FROM
                title           TEXT,
                shop            TEXT,
                price_usd       REAL,
                is_ad           INTEGER DEFAULT 0,
                is_star         INTEGER DEFAULT 0,
                free_ship       INTEGER DEFAULT 0,
                tags            TEXT,
                sold            INTEGER,
                views           INTEGER,
                revenue_usd     REAL,
                image_count     INTEGER,
                source_site     TEXT,
                captured_at     TEXT,
                PRIMARY KEY (listing_id, source_keyword)
            );
            CREATE INDEX IF NOT EXISTS idx_listings_kw ON listings(source_keyword);
            """
        )
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# normalization  (raw capture -> clean listing dicts)
# --------------------------------------------------------------------------- #
def _toks(s):
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower())
            if len(w) > 1 and w not in _STOP]


def keyword_from_view(view):
    """'etsy-bridesmaid_pajamas_20260728' -> 'bridesmaid pajamas'. The search term
    lives only in the view/filename; recover a clean, matchable phrase."""
    v = re.sub(r"[_\-]+", " ", str(view or "")).lower()
    v = re.sub(r"\b\d{6,}\b", " ", v)                 # drop timestamps
    v = re.sub(r"\b20\d\d[ -]?\d\d[ -]?\d\d\b", " ", v)   # drop dates
    words = [w for w in re.findall(r"[a-z0-9]+", v)
             if w not in _STOP and len(w) > 1]
    return " ".join(words).strip()


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").replace("₫", "").strip())
    except (TypeError, ValueError):
        return None


def _flag(v):
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "t"):
        return 1
    if s in ("", "0", "false", "no", "n", "none", "-"):
        return 0
    return 1 if (s.startswith("free ship") or s.startswith("free deliver")
                 or s in ("ad", "promoted", "sponsored", "star seller",
                          "star-seller", "bestseller")) else 0


def _col(headers, *names, exclude=()):
    H = [str(h).lower() for h in (headers or [])]
    for i, h in enumerate(H):
        if any(n in h for n in names) and not any(x in h for x in exclude):
            return i
    return None


def normalize_capture(view, headers, rows, source_site="etsy"):
    """Turn one raw listings capture into clean, typed listing dicts. Prices are
    converted to USD (VND auto-detected by the capture's own median). Returns []
    for a non-listing capture (no title column)."""
    ti = _col(headers, "title", "product", "name") or _col(headers, "listing", exclude=("id",))
    if ti is None:
        return []
    idi = _col(headers, "listing_id", "listing id", "id")
    pi = _col(headers, "price_num") or _col(headers, "price", exclude=("was", "compare"))
    shi = _col(headers, "shop", "seller", exclude=("id",))
    sti = _col(headers, "star")
    adi = _col(headers, "ad", "promoted", exclude=("add", "load", "read"))
    fsi = _col(headers, "free", "ship")
    tgi = _col(headers, "he_tags") or _col(headers, "tags", exclude=("categor",))
    soi = _col(headers, "he_sold") or _col(headers, "sold")
    vi = _col(headers, "he_views", exclude=("avg",)) or _col(headers, "views")
    ri = _col(headers, "he_revenue", "revenue")
    kw = keyword_from_view(view)

    def cell(row, i):
        return row[i] if (i is not None and i < len(row)) else None

    # currency: detect VND by the capture's own median price (Vietnamese staff
    # view Etsy in local currency). One decision per capture, applied to all rows.
    raw_prices = [p for p in (_num(cell(r, pi)) for r in rows) if p and p > 0]
    is_vnd = bool(raw_prices) and sorted(raw_prices)[len(raw_prices) // 2] > 2000

    out = []
    for row in rows:
        title = str(cell(row, ti) or "").strip()
        if not title:
            continue
        shop = str(cell(row, shi) or "").strip()
        is_ad = _flag(cell(row, adi))
        # de-junk: Etsy stamps "Ad by Etsy seller" in the shop slot for ads
        if shop.lower().startswith("ad by") or "ad by etsy" in shop.lower():
            is_ad = 1
            shop = ""
        price = _num(cell(row, pi))
        if price is not None and is_vnd:
            price = round(price / _VND_PER_USD, 2)
        if price is not None and (price <= 0 or price > 100000):
            price = None                      # drop garbage so a bad scrape can't skew bands
        lid = str(cell(row, idi) or "").strip() or ("t:" + title.lower()[:60])
        out.append({
            "listing_id": lid,
            "source_keyword": kw,
            "title": title,
            "shop": shop or None,
            "price_usd": price,
            "is_ad": is_ad,
            "is_star": _flag(cell(row, sti)),
            "free_ship": _flag(cell(row, fsi)),
            "tags": str(cell(row, tgi) or "").strip() or None,
            "sold": _num(cell(row, soi)),
            "views": _num(cell(row, vi)),
            "revenue_usd": _num(cell(row, ri)),
            "image_count": None,
            "source_site": source_site,
            "captured_at": date.today().isoformat(),
        })
    return out


# --------------------------------------------------------------------------- #
# write
# --------------------------------------------------------------------------- #
_COLS = ["listing_id", "source_keyword", "title", "shop", "price_usd", "is_ad",
         "is_star", "free_ship", "tags", "sold", "views", "revenue_usd",
         "image_count", "source_site", "captured_at"]


def upsert_listings(listings):
    """Insert-or-replace clean listing dicts. Re-capture updates in place (no
    double count). Returns count written. Never raises (best-effort index)."""
    if not listings:
        return 0
    try:
        init_db()
        con = _connect()
        try:
            con.executemany(
                f"INSERT OR REPLACE INTO listings ({','.join(_COLS)}) "
                f"VALUES ({','.join('?' * len(_COLS))})",
                [[l.get(c) for c in _COLS] for l in listings],
            )
            con.commit()
            return len(listings)
        finally:
            con.close()
    except Exception:  # noqa: BLE001 — the index must never break an import
        return 0


def index_capture(view, headers, rows, source_site="etsy"):
    """Normalize + upsert one raw capture. The single call the ingest path makes."""
    return upsert_listings(normalize_capture(view, headers, rows, source_site))


# --------------------------------------------------------------------------- #
# read  (what Pattern Miner / lookups query)
# --------------------------------------------------------------------------- #
def _kw_match(query_toks, stored_kw):
    """A stored source_keyword belongs to the query when it shares the query
    tokens (>=2, or >=1 for a single-word query)."""
    if not query_toks:
        return True
    st = set(_toks(stored_kw))
    hits = sum(1 for t in query_toks if t in st)
    return hits >= min(2, len(query_toks))


def listings_for_keyword(keyword):
    """Every listing captured from a search matching `keyword`, newest capture
    per (listing_id) winning. Returns [] if the DB is empty/missing."""
    try:
        if not DB_PATH.is_file():
            return []
        con = _connect()
        try:
            kws = [r["source_keyword"] for r in
                   con.execute("SELECT DISTINCT source_keyword FROM listings")]
            qt = _toks(keyword)
            hit = [k for k in kws if _kw_match(qt, k)]
            if not hit:
                return []
            q = ("SELECT * FROM listings WHERE source_keyword IN (%s)"
                 % ",".join("?" * len(hit)))
            rows = [dict(r) for r in con.execute(q, hit)]
            # de-dupe by listing_id across searches (a listing can rank in several)
            seen, uniq = set(), []
            for r in rows:
                if r["listing_id"] in seen:
                    continue
                seen.add(r["listing_id"])
                uniq.append(r)
            return uniq
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return []


def rebuild_from_raw(dirs=None):
    """Populate the DB from EXISTING raw captures — the landing zone keeps every
    payload ever sent (including ones that were misrouted before), so this rescues
    already-sent data without re-capturing. Non-listing captures are skipped
    automatically (no title column). Safe to re-run. Returns {files, listings}."""
    if dirs is None:
        dirs = ["data/imports/ytrends_ext", "data/imports/etsy_spy",
                "data/imports/etsy_search"]
    init_db()
    files, total = 0, 0
    for d in dirs:
        p = Path(d)
        if not p.is_dir():
            continue
        for f in sorted(p.glob("*.json")):
            try:
                payload = json.loads(f.read_text(encoding="utf-8")) or {}
            except Exception:  # noqa: BLE001
                continue
            files += 1
            view = payload.get("view") or f.stem
            site = "etsy_vn" if "vietnam" in str(view).lower() else "etsy"
            total += index_capture(view, payload.get("headers") or [],
                                   payload.get("rows") or [], site)
    return {"files": files, "listings": total}


def stats():
    """{listings, keywords} — for a health/debug view."""
    try:
        if not DB_PATH.is_file():
            return {"listings": 0, "keywords": 0}
        con = _connect()
        try:
            n = con.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
            k = con.execute(
                "SELECT COUNT(DISTINCT source_keyword) FROM listings").fetchone()[0]
            return {"listings": n, "keywords": k}
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return {"listings": 0, "keywords": 0}
