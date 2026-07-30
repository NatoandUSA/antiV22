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

            CREATE TABLE IF NOT EXISTS keywords (
                keyword         TEXT PRIMARY KEY,
                source          TEXT,     -- ytrends | ext | keyword-lab | listing-mined
                etsy_listings   INTEGER,
                seller_count    INTEGER,
                views_24h       INTEGER,
                avg_price       REAL,
                avg_revenue     REAL,
                conversion_rate REAL,
                momentum        REAL,
                tm_risk         TEXT,
                source_search   TEXT,     -- the captured search that surfaced it
                first_seen      TEXT,
                last_seen       TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_keywords_seen ON keywords(last_seen);
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


# --------------------------------------------------------------------------- #
# keywords  (the store the discovery pages read — YOUR data, not a live pull)
# --------------------------------------------------------------------------- #
_KW_COLS = ["keyword", "source", "etsy_listings", "seller_count", "views_24h",
            "avg_price", "avg_revenue", "conversion_rate", "momentum", "tm_risk",
            "source_search", "first_seen", "last_seen"]


def upsert_keywords(rows):
    """Insert/update keyword rows. first_seen is preserved on conflict (honest
    'when did I first see this'); last_seen advances. Never raises."""
    if not rows:
        return 0
    try:
        init_db()
        con = _connect()
        try:
            con.executemany(
                f"INSERT INTO keywords ({','.join(_KW_COLS)}) "
                f"VALUES ({','.join('?' * len(_KW_COLS))}) "
                "ON CONFLICT(keyword) DO UPDATE SET "
                "source=excluded.source, "
                "etsy_listings=COALESCE(excluded.etsy_listings, keywords.etsy_listings), "
                "seller_count=COALESCE(excluded.seller_count, keywords.seller_count), "
                "views_24h=COALESCE(excluded.views_24h, keywords.views_24h), "
                "avg_price=COALESCE(excluded.avg_price, keywords.avg_price), "
                "avg_revenue=COALESCE(excluded.avg_revenue, keywords.avg_revenue), "
                "conversion_rate=COALESCE(excluded.conversion_rate, keywords.conversion_rate), "
                "momentum=COALESCE(excluded.momentum, keywords.momentum), "
                "tm_risk=COALESCE(excluded.tm_risk, keywords.tm_risk), "
                "last_seen=excluded.last_seen",
                [[r.get(c) for c in _KW_COLS] for r in rows],
            )
            con.commit()
            return len(rows)
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return 0


def import_keyword_base(path="keyword_data.csv"):
    """Mirror the existing keyword base (with its YTrends metrics + first-seen
    dates) into the store. This is what lets the discovery pages show YOUR whole
    accumulated base instead of a 25-row live pull. Returns count."""
    import csv as _csv
    p = Path(path)
    if not p.is_file():
        return 0
    rows = []
    try:
        with p.open(encoding="utf-8-sig") as fh:
            for r in _csv.DictReader(fh):
                kw = (r.get("keyword") or "").strip()
                if not kw:
                    continue
                d = (r.get("collected_at") or "").strip() or None
                rows.append({
                    "keyword": kw.lower(),
                    "source": (r.get("source") or "").split(":")[0] or "ytrends",
                    "etsy_listings": _num(r.get("etsy_listings")),
                    "seller_count": _num(r.get("seller_count")),
                    "views_24h": _num(r.get("views_24h")),
                    "avg_price": _num(r.get("avg_price")),
                    "avg_revenue": _num(r.get("avg_revenue")),
                    "conversion_rate": _num(r.get("conversion_rate")),
                    "momentum": _num(r.get("momentum")),
                    "tm_risk": (r.get("tm_risk") or "").strip() or None,
                    "source_search": None,
                    "first_seen": d, "last_seen": d,
                })
    except OSError:
        return 0
    return upsert_keywords(rows)


_KW_STOP = _STOP | {"custom", "personalized", "gift", "gifts", "set", "sets"}


def mine_keywords_from_listings(min_listings=2):
    """CLOSE THE LOOP: derive fresh keyword candidates from the tags of the
    listings you captured. A tag used across several listings/shops is a real,
    buyer-used keyword — often ones YTuong doesn't rank. Demand/competition are
    proxied from how many listings/shops use the tag. Returns count."""
    try:
        if not DB_PATH.is_file():
            return 0
        con = _connect()
        try:
            agg = {}   # tag -> {listings, shops:set, prices:[]}
            for r in con.execute(
                    "SELECT tags, shop, price_usd, source_keyword FROM listings"):
                for t in re.split(r"[;|,]", r["tags"] or ""):
                    t = re.sub(r"\s+", " ", t).strip().lower()
                    if not (2 < len(t) <= 40):
                        continue
                    toks = [w for w in re.findall(r"[a-z0-9]+", t)
                            if w not in _KW_STOP]
                    if not toks:
                        continue
                    a = agg.setdefault(t, {"n": 0, "shops": set(), "px": [],
                                           "src": r["source_keyword"]})
                    a["n"] += 1
                    if r["shop"]:
                        a["shops"].add(r["shop"])
                    if r["price_usd"]:
                        a["px"].append(r["price_usd"])
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return 0
    today = date.today().isoformat()
    rows = []
    for tag, a in agg.items():
        if a["n"] < min_listings:
            continue
        rows.append({
            "keyword": tag, "source": "listing-mined",
            "etsy_listings": a["n"], "seller_count": len(a["shops"]),
            "views_24h": None,
            "avg_price": round(sum(a["px"]) / len(a["px"]), 2) if a["px"] else None,
            "avg_revenue": None, "conversion_rate": None, "momentum": None,
            "tm_risk": None, "source_search": a["src"],
            "first_seen": today, "last_seen": today,
        })
    return upsert_keywords(rows)


# --------------------------------------------------------------------------- #
# Local Data Safety Contract  (senior-review W01/W02 — the critical fix)
# --------------------------------------------------------------------------- #
# A keyword row that entered the store from CAPTURED LISTINGS carries demand and
# competition PROXIES (tag frequency, unique-shop count) — supply-side evidence,
# NOT buyer search demand. It must never be scored like a real YTrends market row.
# Every row therefore declares its provenance, and — critically — a proxy row
# emits NO scorer-facing demand/competition metric, so the FROZEN scorer can only
# reach WATCH for it. No ranking-math change; the input semantics are made honest.

def _source_kind(source):
    s = (source or "").lower()
    if s in ("mcp", "ytrends", "ytrends-en"):
        return "live_ytrends"
    if s == "listing-mined":
        return "local_mined_proxy"
    if s == "keyword-lab":
        return "keyword_lab"
    return "user_import"          # extension file-drops / ext:*


def _freshness(last_seen):
    if not last_seen:
        return "unknown"
    try:
        d = date.fromisoformat(str(last_seen)[:10])
    except (ValueError, TypeError):
        return "unknown"
    age = (date.today() - d).days
    return "fresh" if age <= 14 else ("stale" if age <= 60 else "old")


def _kw_confidence(keyword):
    """How much we trust that this keyword IS the search it claims to be. View
    names get truncated (~40 chars), so a clipped-looking key is low confidence
    until the extension supplies an explicit focus_keyword / URL query."""
    k = (keyword or "").strip()
    if not k:
        return "unknown"
    # view-derived keys clip at ~40 chars and often end mid-word
    if len(k) >= 38 or (len(k) >= 30 and not k.endswith(tuple("aeiouy s"))):
        return "view_name_truncated"
    return "view_name"


def _contract_row(r):
    """Turn a keywords-table row into a discovery row + full safety contract.
    PROXY rows null their scorer-facing demand/competition so the frozen scorer
    caps them at WATCH; their captured counts live in labeled display fields."""
    kind = _source_kind(r["source"])
    proxy = kind == "local_mined_proxy"
    return {
        "tag": r["keyword"],
        # ---- scorer-facing metrics (None for proxy => frozen scorer => WATCH) ----
        "sellers": None if proxy else r["seller_count"],
        "momentum_score": None if proxy else r["momentum"],
        "avg_conversion_rate": None if proxy else r["conversion_rate"],
        "etsy_listings": None if proxy else r["etsy_listings"],
        "avg_price_usd": r["avg_price"],
        # ---- Local Data Safety Contract ----
        "source": r["source"],
        "source_kind": kind,
        "is_proxy_metric": proxy,
        "metric_confidence": ("low" if proxy
                              else "high" if kind == "live_ytrends" else "medium"),
        "demand_metric_type": ("captured_listing_tag_frequency_not_search_volume"
                               if proxy else "ytrends_search_signal"),
        "competition_metric_type": ("captured_unique_shop_count_not_market_competition"
                                    if proxy else "ytrends_seller_signal"),
        "captured_listing_count": r["etsy_listings"] if proxy else None,
        "captured_unique_shop_count": r["seller_count"] if proxy else None,
        "price_confidence": "low" if proxy else "medium",
        "action_cap": "WATCH_OR_CONFIRM_FIRST" if proxy else None,
        "build_eligible": (not proxy),
        "build_ineligible_reason": (
            "supply-side proxy (listing-tag & shop counts), not buyer demand — "
            "confirm on Live YTrends before Build Now" if proxy else None),
        "source_keyword": r["source_search"],
        "source_keyword_confidence": _kw_confidence(r["keyword"]),
        "first_seen": r["first_seen"],
        "last_seen": r["last_seen"],
        "freshness_status": _freshness(r["last_seen"]),
    }


def keyword_rows(mode=None, limit=200, sort="recent", include_mined=True):
    """Keyword rows for the discovery pages, each carrying the full Local Data
    Safety Contract. Proxy (listing-mined) rows emit no real demand/competition,
    so the UNCHANGED frozen scorer can only reach WATCH for them."""
    try:
        if not DB_PATH.is_file():
            return []
        con = _connect()
        try:
            where = "" if include_mined else "WHERE source != 'listing-mined'"
            order = ("first_seen DESC, last_seen DESC" if sort == "recent"
                     else "momentum DESC")
            q = f"SELECT * FROM keywords {where} ORDER BY {order} LIMIT ?"
            return [_contract_row(r) for r in con.execute(q, (int(limit),))]
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return []


def keyword_payload(limit=400, sort="recent"):
    """The keyword store as a Winner-Finder import payload {view, headers, rows}.
    Headers use the base column names the scorer already maps, so Winner Finder
    scores the WHOLE store with its existing math — not just the latest import."""
    hdrs = ["keyword", "etsy_listings", "seller_count", "views_24h", "avg_price",
            "avg_revenue", "conversion_rate", "momentum"]
    try:
        if not DB_PATH.is_file():
            return None
        con = _connect()
        try:
            order = ("first_seen DESC, last_seen DESC" if sort == "recent"
                     else "momentum DESC")
            rows = []
            for r in con.execute(
                    f"SELECT * FROM keywords ORDER BY {order} LIMIT ?",
                    (int(limit),)):
                proxy = _source_kind(r["source"]) == "local_mined_proxy"
                # proxy rows null their demand/competition so Winner Finder's
                # scorer can't rank a supply-side proxy as a GO/Build winner.
                rows.append([
                    r["keyword"],
                    None if proxy else r["etsy_listings"],
                    None if proxy else r["seller_count"],
                    r["views_24h"],
                    r["avg_price"], r["avg_revenue"],
                    None if proxy else r["conversion_rate"],
                    None if proxy else r["momentum"],
                ])
            return ({"view": "my-keyword-store", "headers": hdrs, "rows": rows}
                    if rows else None)
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return None


def master_rows(mined_only=False):
    """Store keywords as keyword_data.csv-shaped dicts, for Build Queue and other
    master readers. mined_only=True -> just the listing-mined candidates (so we can
    ADD them to the on-disk base without duplicating it)."""
    try:
        if not DB_PATH.is_file():
            return []
        con = _connect()
        try:
            where = "WHERE source='listing-mined'" if mined_only else ""
            out = []
            for r in con.execute(f"SELECT * FROM keywords {where}"):
                out.append({
                    "keyword": r["keyword"],
                    "etsy_listings": r["etsy_listings"] if r["etsy_listings"] is not None else "",
                    "seller_count": r["seller_count"] if r["seller_count"] is not None else "",
                    "views_24h": r["views_24h"] if r["views_24h"] is not None else "",
                    "avg_price": r["avg_price"] if r["avg_price"] is not None else "",
                    "avg_revenue": r["avg_revenue"] if r["avg_revenue"] is not None else "",
                    "conversion_rate": r["conversion_rate"] if r["conversion_rate"] is not None else "",
                    "momentum": r["momentum"] if r["momentum"] is not None else "",
                    "tm_risk": r["tm_risk"] or "",
                    "source": r["source"] or "",
                    "collected_at": r["first_seen"] or "",
                })
            return out
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return []


def rebuild_keywords(path="keyword_data.csv"):
    """Populate the keyword store: mirror the metric-rich base, then mine fresh
    candidates from captured listings. Returns {base, mined, total}."""
    base = import_keyword_base(path)
    mined = mine_keywords_from_listings()
    return {"base": base, "mined": mined, "total": base + mined}


def stats():
    """{listings, search_keywords, keywords, mined} — health/debug view."""
    try:
        if not DB_PATH.is_file():
            return {"listings": 0, "search_keywords": 0, "keywords": 0, "mined": 0}
        con = _connect()
        try:
            n = con.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
            sk = con.execute(
                "SELECT COUNT(DISTINCT source_keyword) FROM listings").fetchone()[0]
            try:
                k = con.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
                m = con.execute("SELECT COUNT(*) FROM keywords "
                                "WHERE source='listing-mined'").fetchone()[0]
                rng = con.execute("SELECT MIN(last_seen), MAX(last_seen) "
                                  "FROM keywords").fetchone()
                oldest, newest = (rng[0], rng[1]) if rng else (None, None)
            except Exception:  # noqa: BLE001
                k = m = 0
                oldest = newest = None
            return {"listings": n, "search_keywords": sk, "keywords": k,
                    "mined": m, "live_or_real": max(0, k - m),
                    "proxy_pct": round(100 * m / k) if k else 0,
                    "newest_capture": newest, "oldest_capture": oldest,
                    "freshness": _freshness(newest)}
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return {"listings": 0, "search_keywords": 0, "keywords": 0, "mined": 0}
