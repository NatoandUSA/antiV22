"""Score the latest YTrends extension import with the composite Opportunity Score.

Bridges the browser-extension import (data/imports/ytrends_ext/*.json) with
src/opportunity_score.py so a team member can click "Score latest import" and get
ranked GO / CONDITIONAL / WATCH / SKIP verdicts - no terminal needed. It maps each
imported row to the fields the scorer reads and injects the view's implied
opportunity signal (a "hidden gems" export IS an opportunity signal even when the
table has no gem-score column). Nothing here publishes anything.
"""
import json
from pathlib import Path

from src import ytx_import as yi
from src import opportunity_score as osc

EXT_DIR = Path("data/imports/ytrends_ext")


def _latest_files(source=None):
    if not EXT_DIR.is_dir():
        return []
    files = sorted(EXT_DIR.glob("*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if source:
        s = source.lower().replace(" ", "-")
        files = [f for f in files if f.name.lower().startswith(s)]
    return files


def load_latest_import(source=None):
    """Newest extension payload (optionally filtered by source view), or None."""
    for f in _latest_files(source):
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
    return None


def latest_import_info():
    """Tiny status for the homepage: {rows, view, age_seconds} for the newest
    import, or None. Reads the file's mtime for the age so it needs no clock in
    the payload. Never raises."""
    import time
    files = _latest_files()
    if not files:
        return None
    f = files[0]
    try:
        payload = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    try:
        age = max(0, int(time.time() - f.stat().st_mtime))
    except Exception:  # noqa: BLE001
        age = None
    return {"rows": len(payload.get("rows") or []),
            "view": str(payload.get("view") or ""), "age_seconds": age}


def _find(headers, *needles, exclude=()):
    for i, h in enumerate(headers):
        hl = str(h).lower()
        if any(n in hl for n in needles) and not any(x in hl for x in exclude):
            return i
    return None


def map_row_to_scorer(headers, row, view=""):
    """One extension row -> the field names opportunity_score.score reads."""
    idx = {
        "keyword": _find(headers, "keyword", "phrase"),
        # "search volume"/"volume" = Amazon Xray/Cerebro demand; maps to the same
        # demand slot as Etsy views so an Amazon reference export scores normally.
        "views": _find(headers, "views", "view", "search volume", "volume"),
        "conv": _find(headers, "conversion", "conv"),
        # "competing products" = Amazon Xray competition count -> the listings slot.
        # exclude "id"/"url" so "listing_id"/"listing_url" don't mis-map as a count.
        "listings": _find(headers, "listing", "competing",
                          exclude=("/", "seller", "id", "url")),
        "sellers": _find(headers, "seller", exclude=("/",)),
        "price": _find(headers, "avg price", "price"),
        "revenue": _find(headers, "revenue"),
        "gem": _find(headers, "gem score", "opportunity", "momentum", "score"),
        "comp": _find(headers, "competition"),
        "category": _find(headers, "category"),
    }

    def cell(k):
        i = idx[k]
        return row[i] if (i is not None and i < len(row)) else None

    d = {
        "tag": (cell("keyword") or "").strip(),
        # Only views_24h (a raw count). opportunity_score._market normalises it to
        # 0-100 via its proxy; do NOT also set "demand" (a raw count in the 0-100
        # 'demand' slot makes Market blow past 100).
        "views_24h": yi.parse_number(cell("views")),
        "avg_conversion_rate": yi.parse_percent(cell("conv")),
        "listing_count": yi.parse_number(cell("listings")),
        "seller_count": yi.parse_number(cell("sellers")),
        "avg_price": yi.parse_number(cell("price")),
        "revenue": yi.parse_number(cell("revenue")),
        "category": cell("category"),
    }
    gem = yi.parse_number(cell("gem"))
    if gem is not None:
        d["gem_score"] = gem
        d["momentum_score"] = gem
    comp = cell("comp")
    if comp:
        d["competition_level"] = comp
    if "gem" in (view or "").lower():          # view-implied opportunity signal
        d.setdefault("is_hidden_gem", True)
    return d


# How many top rows get the (slow, rate-limited) Google Trends read. We only
# spend Google requests on rows that already look worth building, never on the
# SKIP junk - so a 40-row import costs at most a couple of Trends batches.
GT_TOP = 12


def _coerce_num(v):
    """A number from a research field, tolerating '2.5%', '$12.00', '1.8K'."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    n = yi.parse_number(v)
    return n


def _enrich_row(d, mode=None):
    """Fill a scorer row's BLANKS from the live YTrends MCP, so the score rests on
    real market data instead of the few columns the captured table happened to
    show. Only fills fields that are missing/empty - never overwrites a real
    captured value, never invents one. Returns True if anything real was added.
    Any MCP failure leaves the row untouched (best-effort)."""
    kw = d.get("tag")
    if not kw:
        return False
    try:
        from src import ytrends_mcp as mcp
    except Exception:  # noqa: BLE001
        return False
    added = [False]

    def put(key, val):
        if val is not None and d.get(key) in (None, "", 0, 0.0):
            d[key] = val
            added[0] = True

    # 1) keyword research -> conversion, price, listings, competition
    try:
        rk = mcp.research_keyword(kw) or {}
    except (SystemExit, Exception):  # noqa: BLE001 - one dead call can't abort the run
        rk = {}
    stats = rk.get("stats", rk) if isinstance(rk, dict) else {}
    if isinstance(stats, dict):
        put("avg_conversion_rate", _coerce_num(stats.get("avg_conversion_rate")))
        put("listing_count", _coerce_num(stats.get("listing_count")
                                         or stats.get("total_listings")))
        put("seller_count", _coerce_num(stats.get("seller_count")
                                        or stats.get("total_sellers")))
        put("avg_price", _coerce_num(stats.get("median_price")
                                     or stats.get("avg_price")))
        cl = stats.get("competition_level") or rk.get("competition_level")
        if cl and not d.get("competition_level"):
            d["competition_level"] = cl
            added[0] = True

    # 2) momentum / opportunity for the velocity + opportunity components
    try:
        hit = {}
        for t in mcp.trending_keywords(limit=8, search=kw):
            if (t.get("tag") or "").lower() == kw.lower():
                hit = t
                break
        if not hit:
            for r in mcp.scout_opportunities(limit=8, search=kw):
                if (r.get("tag") or "").lower() == kw.lower():
                    hit = r
                    break
    except (SystemExit, Exception):  # noqa: BLE001
        hit = {}
    if isinstance(hit, dict) and hit:
        put("momentum_score", _coerce_num(hit.get("momentum_score")))
        put("opportunity_score", _coerce_num(hit.get("opportunity_score")))
        put("gem_score", _coerce_num(hit.get("gem_score")))
        cl = hit.get("competition_level")
        if cl and not d.get("competition_level"):
            d["competition_level"] = cl
            added[0] = True
    return added[0]


def score_latest(source=None, limit=None, threshold=None, mode=None,
                 enrich=False, gtrends=False):
    """Load the newest import, score every row, return ranked results (best first).

    enrich=True first tops up each launch-ready row's blank fields from the live
    YTrends MCP, so the verdict rests on real market data instead of the handful
    of columns the captured table showed (rows the server has no data on are left
    as-is, not guessed).

    gtrends=True cross-checks the top rows against free Google Trends demand and
    blends that into the Market score (a rising/cooling external corroboration).
    Both are opt-in because they hit the network."""
    payload = load_latest_import(source)
    if not payload:
        return {"ok": False, "results": [],
                "error": "no extension import found in data/imports/ytrends_ext/"}
    headers = payload.get("headers") or []
    rows = payload.get("rows") or []
    view = payload.get("view") or source or ""
    from src import product_fit as pf
    out = []
    enriched_count = 0
    for row in rows:
        d = map_row_to_scorer(headers, row, view)
        if not d["tag"]:
            continue
        # Skip genuine junk (shop handles, broad seeds, policy/spell, digital,
        # non-products) so it can't score GO - same filter the discovery pages use.
        fit = pf.classify(d["tag"], mode)
        if not fit["launchable"] and fit["status"] not in pf.LAUNCHABLE:
            continue
        did = _enrich_row(d, mode) if enrich else False
        if did:
            enriched_count += 1
        s = osc.score(d, keyword=d["tag"], mode=mode)
        s["category"] = d.get("category")
        s["enriched"] = did
        s["_row"] = d               # kept for an optional Google Trends re-score
        out.append(s)
    rank = {"GO": 0, "CONDITIONAL": 1, "WATCH": 2, "SKIP": 3}
    out.sort(key=lambda s: (rank.get(s["verdict"], 9), -(s["overall_score"] or 0)))

    # Google Trends: only worth spending requests on the rows already near the
    # top; re-score just those with the Trends read blended in, then re-rank.
    if gtrends and out:
        top = out[:GT_TOP]
        gt_map = osc.gtrends_dirs([s["keyword"] for s in top])
        if gt_map:
            for s in top:
                gt = gt_map.get(s["keyword"])
                if not gt:
                    continue
                rs = osc.score(s["_row"], keyword=s["keyword"], mode=mode,
                               gtrends_dir=gt)
                rs["category"] = s.get("category")
                rs["enriched"] = s.get("enriched")
                rs["gtrends"] = gt
                s.update(rs)
            out.sort(key=lambda s: (rank.get(s["verdict"], 9),
                                    -(s["overall_score"] or 0)))

    for s in out:
        s.pop("_row", None)         # internal only - never leaks to the view
    ranked = out
    if threshold is not None:
        ranked = [s for s in ranked if (s["overall_score"] or 0) >= threshold]
    if limit:
        ranked = ranked[:limit]
    return {"ok": True, "view": view, "captured_at": payload.get("captured_at"),
            "count": len(ranked), "rows_in_import": len(rows),
            "enriched_count": enriched_count, "results": ranked}
