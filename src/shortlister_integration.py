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


def _find(headers, *needles, exclude=()):
    for i, h in enumerate(headers):
        hl = str(h).lower()
        if any(n in hl for n in needles) and not any(x in hl for x in exclude):
            return i
    return None


def map_row_to_scorer(headers, row, view=""):
    """One extension row -> the field names opportunity_score.score reads."""
    idx = {
        "keyword": _find(headers, "keyword"),
        "views": _find(headers, "views", "view"),
        "conv": _find(headers, "conversion", "conv"),
        "listings": _find(headers, "listing", exclude=("/", "seller")),
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


def score_latest(source=None, limit=None, threshold=None, mode=None):
    """Load the newest import, score every row, return ranked results (best first)."""
    payload = load_latest_import(source)
    if not payload:
        return {"ok": False, "results": [],
                "error": "no extension import found in data/imports/ytrends_ext/"}
    headers = payload.get("headers") or []
    rows = payload.get("rows") or []
    view = payload.get("view") or source or ""
    from src import product_fit as pf
    out = []
    for row in rows:
        d = map_row_to_scorer(headers, row, view)
        if not d["tag"]:
            continue
        # Skip genuine junk (shop handles, broad seeds, policy/spell, digital,
        # non-products) so it can't score GO - same filter the discovery pages use.
        fit = pf.classify(d["tag"], mode)
        if not fit["launchable"] and fit["status"] not in pf.LAUNCHABLE:
            continue
        s = osc.score(d, keyword=d["tag"], mode=mode)
        s["category"] = d.get("category")
        out.append(s)
    rank = {"GO": 0, "CONDITIONAL": 1, "WATCH": 2, "SKIP": 3}
    out.sort(key=lambda s: (rank.get(s["verdict"], 9), -(s["overall_score"] or 0)))
    if threshold is not None:
        out = [s for s in out if (s["overall_score"] or 0) >= threshold]
    if limit:
        out = out[:limit]
    return {"ok": True, "view": view, "captured_at": payload.get("captured_at"),
            "count": len(out), "results": out}
