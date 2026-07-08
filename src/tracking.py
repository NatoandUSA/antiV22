"""Keyword + Market trackers — snapshot metrics over time so we see the trend.

Self-populating: daily-run snapshots the current top keywords and refreshes any
saved markets, so the trend history builds itself. The team can also add a
keyword/market manually. Stores: data/tracking/keyword_tracker.{json,csv} and
market_tracker.{json,csv}. All data is from the official YTrends MCP.
"""
import csv
import json
from datetime import date
from pathlib import Path

DIR = Path("data/tracking")
KW_JSON, KW_CSV = DIR / "keyword_tracker.json", DIR / "keyword_tracker.csv"
MK_JSON, MK_CSV = DIR / "market_tracker.json", DIR / "market_tracker.csv"

KW_COLS = ["date", "keyword", "product_mode", "demand_24h", "conversion",
           "listings", "sellers", "avg_price", "source", "source_confidence"]
MK_COLS = ["date", "niche", "product_mode", "demand_24h", "listings", "sellers",
           "avg_price", "opportunity", "competition"]


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _load(p):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save(store, jpath, cpath, cols):
    DIR.mkdir(parents=True, exist_ok=True)
    jpath.write_text(json.dumps(store, indent=2), encoding="utf-8")
    with cpath.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for snaps in store.values():
            for s in snaps:
                w.writerow(s)


def _trend(history, key="demand_24h"):
    vals = [_f(s.get(key)) for s in history]
    if len(vals) < 2:
        return "new"
    head = vals[0] if len(vals) < 4 else sum(vals[:len(vals)//3]) / (len(vals)//3)
    tail = vals[-1] if len(vals) < 4 else sum(vals[-(len(vals)//3):]) / (len(vals)//3)
    if tail > head * 1.15:
        return "rising"
    if tail < head * 0.85:
        return "falling"
    return "stable"


# ------------------------------------------------------------- keywords ----
def snapshot_keyword(kw, mode="", stats=None):
    kw = (kw or "").strip().lower()
    if not kw:
        return None
    if stats is None:
        try:
            from src import ytrends_mcp as mcp
            rk = mcp.research_keyword(kw)
            stats = rk.get("stats", {}) if isinstance(rk, dict) else {}
        except Exception:  # noqa: BLE001
            stats = {}
    snap = {
        "date": str(date.today()), "keyword": kw, "product_mode": mode,
        "demand_24h": int(_f(stats.get("total_views_24h") or stats.get("avg_views_24h"))),
        "conversion": round(_f(stats.get("avg_conversion_rate")), 4),
        "listings": int(_f(stats.get("total_listings") or stats.get("listing_count"))),
        "sellers": int(_f(stats.get("total_sellers") or stats.get("seller_count"))),
        "avg_price": round(_f(stats.get("avg_price") or stats.get("median_price")), 2),
        "source": "ytrends_mcp",
        "source_confidence": "MEDIUM" if stats else "SOURCE_NOT_AVAILABLE",
    }
    store = _load(KW_JSON)
    day = snap["date"]
    hist = [s for s in store.get(kw, []) if s.get("date") != day]  # one snap/day
    hist.append(snap)
    store[kw] = hist
    _save(store, KW_JSON, KW_CSV, KW_COLS)
    return snap


def keyword_rows():
    """Latest snapshot per keyword + trend + a simple action classification."""
    store = _load(KW_JSON)
    out = []
    for kw, hist in store.items():
        if not hist:
            continue
        last = hist[-1]
        tr = _trend(hist)
        age = (date.today() - _to_date(last.get("date"))).days if last.get("date") else 0
        action = ("recheck" if age >= 7 else
                  "drop" if (tr == "falling" and last.get("demand_24h", 0) < 50) else
                  "watch")
        out.append({**last, "trend": tr, "days_since": age,
                    "snapshots": len(hist), "action": action})
    out.sort(key=lambda r: (-r.get("demand_24h", 0)))
    return out


def _to_date(iso):
    from datetime import datetime
    try:
        return datetime.strptime(str(iso)[:10], "%Y-%m-%d").date()
    except Exception:  # noqa: BLE001
        return date.today()


# -------------------------------------------------------------- markets ----
def snapshot_market(niche, mode=""):
    niche = (niche or "").strip().lower()
    if not niche:
        return None
    demand = listings = sellers = 0
    avg_price = opportunity = competition = 0
    try:
        from src import ytrends_mcp as mcp
        rk = mcp.research_keyword(niche)
        st = rk.get("stats", {}) if isinstance(rk, dict) else {}
        demand = int(_f(st.get("total_views_24h") or st.get("avg_views_24h")))
        listings = int(_f(st.get("total_listings")))
        sellers = int(_f(st.get("total_sellers")))
        avg_price = round(_f(st.get("avg_price")), 2)
        comp = mcp.analyze_competition(niche)
        competition = comp.get("saturation", "")
    except Exception:  # noqa: BLE001
        pass
    snap = {"date": str(date.today()), "niche": niche, "product_mode": mode,
            "demand_24h": demand, "listings": listings, "sellers": sellers,
            "avg_price": avg_price, "opportunity": opportunity,
            "competition": competition}
    store = _load(MK_JSON)
    hist = [s for s in store.get(niche, []) if s.get("date") != snap["date"]]
    hist.append(snap)
    store[niche] = hist
    _save(store, MK_JSON, MK_CSV, MK_COLS)
    return snap


def market_rows():
    store = _load(MK_JSON)
    out = []
    for niche, hist in store.items():
        if not hist:
            continue
        out.append({**hist[-1], "trend": _trend(hist), "snapshots": len(hist)})
    out.sort(key=lambda r: (-r.get("demand_24h", 0)))
    return out


def tracked_markets():
    return list(_load(MK_JSON).keys())


# ------------------------------------------------- daily auto-snapshot ----
def daily_snapshot(limit=15):
    """Called by daily-run: snapshot today's top trending keywords + refresh
    every saved market. Returns a short summary string."""
    from src import ytrends_mcp as mcp
    kn = 0
    try:
        for t in mcp.trending_keywords(limit=limit):
            tag = (t.get("tag") or "").strip()
            if tag:
                snapshot_keyword(tag, "", {
                    "avg_views_24h": t.get("avg_views_24h"),
                    "avg_conversion_rate": t.get("avg_conversion_rate"),
                    "avg_price": t.get("avg_price"),
                    "listing_count": t.get("listing_count"),
                    "seller_count": t.get("sellers")})
                kn += 1
    except Exception:  # noqa: BLE001
        pass
    mk = 0
    for niche in tracked_markets():
        if snapshot_market(niche):
            mk += 1
    return f"tracked {kn} keywords, refreshed {mk} markets"
