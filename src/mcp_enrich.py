"""Hybrid enrich: fill gaps in a browser-extension import from the YTrends MCP.

The extension captures the TABLE you were looking at, which is a narrow slice of
what YTrends knows. The Trending view, for example, has Momentum + Competition
but no conversion / listings / sellers, so opportunity_score._market scores that
row on 1 of its 3 signals ("over what's present") and still reports
core_complete=True - a confident-looking number standing on one leg. This fills
ONLY the missing fields from the official MCP server so the score is grounded in
real market data instead of extrapolated from one column.

Hybrid = the extension is ground truth for what you saw (never overwritten); MCP
only fills the blanks.

Safety rules (do NOT remove):
- The MCP server answers for keywords it has NO data on with
  opportunity_score=100, opportunity_grade="N", competition_level="low" and
  recommended_action="insufficient_data". Injecting those would hand the scorer a
  MAXIMUM opportunity signal plus a best-case competition level built on zero
  listings - a near-certain false GO. is_trustworthy() refuses those payloads.
- stats has avg_views_24h (average per LISTING, e.g. 2.78) but the scorer's
  views_24h means a per-keyword TOTAL (harvest maps total_views_24h). Feeding one
  into the other is ~1000x wrong and would wreck the demand proxy, so views are
  deliberately NOT enriched. Missing beats fabricated.

competition_level is stored raw ('very_high'); opportunity_score._competition
normalises the form on read, so every source gets the same treatment.

Nothing here publishes anything.
"""
from src import ytrends_mcp as mcp

# stats key -> the field name opportunity_score.score reads.
# NOTE: avg_views_24h is intentionally absent (see module docstring).
FIELD_MAP = {
    "total_listings": "listing_count",
    "total_sellers": "seller_count",
    "avg_price": "avg_price",
    "avg_conversion_rate": "avg_conversion_rate",
    "avg_revenue": "revenue",
    "opportunity_score": "opportunity_score",
}


def is_trustworthy(stats):
    """False when MCP is guessing. It reports opportunity_score=100 + 'low'
    competition for unknown keywords, which would score as a false GO."""
    if not isinstance(stats, dict) or not stats:
        return False
    if str(stats.get("recommended_action") or "").lower() == "insufficient_data":
        return False
    if str(stats.get("opportunity_grade") or "").upper() == "N":
        return False
    return bool(stats.get("total_listings"))          # 0 / None = nothing to say


def enrich_row(d, stats):
    """Fill blanks in scorer-row `d` from MCP `stats`. Returns (d, note).
    Never overwrites a value the extension already captured."""
    if not is_trustworthy(stats):
        reason = (str(stats.get("recommended_action") or "no data")
                  if isinstance(stats, dict) else "no data")
        return d, {"enriched": False, "reason": reason, "filled": []}
    filled = []
    for src, dest in FIELD_MAP.items():
        if d.get(dest) is None and stats.get(src) is not None:
            d[dest] = stats[src]
            filled.append(dest)
    # Stored raw ('very_high'); opportunity_score._competition normalises on read.
    lvl = stats.get("competition_level")
    if lvl and not d.get("competition_level"):
        d["competition_level"] = lvl
        filled.append("competition_level")
    return d, {"enriched": bool(filled), "reason": "ok", "filled": filled}


def enrich(rows, limit=15, log=lambda s: None):
    """Enrich scorer-rows in place (best-first order assumed). One MCP call per
    keyword, rate-limited + cached for the day by ytrends_mcp, so a repeat run
    costs no quota. `limit` caps the calls so a 200-row import can't drain it."""
    notes = {}
    for d in rows[:limit]:
        kw = (d.get("tag") or "").strip()
        if not kw:
            continue
        try:
            stats = mcp.research_keyword(kw).get("stats", {})
        except Exception as exc:  # noqa: BLE001  - enrich is best-effort
            notes[kw] = {"enriched": False, "reason": "mcp error", "filled": []}
            log(f"  enrich failed for {kw}: {exc}")
            continue
        _, note = enrich_row(d, stats)
        notes[kw] = note
        log(f"  {kw}: {note['reason']} {note['filled']}")
    return notes
