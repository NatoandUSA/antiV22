"""Interactive keyword lookups for the team portal — a teammate types a keyword
and gets a live answer in the browser, no terminal, no waiting on the operator.

All data is live from the official YTrends MCP (src/ytrends_mcp). Read-only:
these functions only fetch + format, they never run shell or write files. Output
is Markdown so the portal renders it with the same styling as the reports.
"""
from src import ytrends_mcp as mcp
from src.trademark import check as tm_check


def _money(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "-"


def _int(v):
    try:
        return f"{int(round(float(v))):,}"
    except (TypeError, ValueError):
        return "-"


def _pct(v):
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _clean(t):
    return str(t or "").replace("|", "/").replace("\n", " ").strip()


def _g(d, *keys):
    """First present, non-None value among keys."""
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return None


def _rel_rows(items, limit=15):
    """Render a related-keyword list (shapes vary by tool) as a Markdown table."""
    out = ["| Keyword | Listings | Avg price | Conv | Trademark |",
           "|---|---|---|---|---|"]
    n = 0
    for r in items or []:
        tag = _clean(_g(r, "tag", "keyword", "title", "term"))
        if not tag:
            continue
        risk, _ = tm_check(tag.lower())
        out.append(
            f"| {tag} | {_int(_g(r, 'listing_count', 'listings', 'total_listings'))} "
            f"| {_money(_g(r, 'avg_price', 'avg_price_usd'))} "
            f"| {_pct(_g(r, 'avg_conversion_rate', 'conversion', 'conversion_rate'))} "
            f"| {risk} |")
        n += 1
        if n >= limit:
            break
    return out if n else ["_No related keywords returned._"]


def analyze_keyword(kw):
    """Full live analysis of one keyword: demand, price, competition shape,
    what's winning, and related keywords."""
    kw = kw.strip()
    L = [f"# Analysis — {kw}", "",
         "_Live from the YTrends index. **Market intel — always verify the "
         "trademark before using a keyword.**_", ""]

    stats = {}
    try:
        rk = mcp.research_keyword(kw)
        stats = rk.get("stats", {}) if isinstance(rk, dict) else {}
    except Exception as exc:  # noqa: BLE001
        L.append(f"_Could not load keyword stats: {exc}_")
        rk = {}

    if stats:
        rc7 = stats.get("rank_change_7d")
        trend = ("rising" if (rc7 or 0) < 0 else "cooling" if (rc7 or 0) > 0
                 else "flat")   # rank going DOWN (toward #1) = rising
        risk, reason = tm_check(kw.lower())
        L += [
            "## Demand & price", "",
            f"- **{_int(stats.get('total_listings'))} listings** from "
            f"**{_int(stats.get('total_sellers'))} sellers** "
            f"({stats.get('listings_per_seller', '-')} per seller)",
            f"- Avg price **{_money(stats.get('avg_price'))}** "
            f"(median {_money(stats.get('median_price'))}, "
            f"sweet spot {_money(stats.get('price_sweet_spot'))}, "
            f"typical {_money(stats.get('price_p25'))}–{_money(stats.get('price_p75'))})",
            f"- Conversion **{_pct(stats.get('avg_conversion_rate'))}** | "
            f"avg views/listing {_int(stats.get('avg_views'))} "
            f"(24h {_int(stats.get('avg_views_24h'))}) | "
            f"demand:supply {stats.get('demand_supply_ratio', '-')}",
            f"- Market revenue **{_money(stats.get('total_revenue'))}** "
            f"(avg {_money(stats.get('avg_revenue'))} per listing)",
            f"- Global rank **#{_int(stats.get('rank'))}**, 7-day move "
            f"{stats.get('rank_change_7d', '-')} → **{trend}**",
            f"- **Trademark: {risk}** — {reason}",
            "",
        ]

    try:
        comp = mcp.call("ytrends_analyze_competition", seed=kw,
                        seed_type="keyword")
        comp = comp.get("data", comp) if isinstance(comp, dict) else {}
    except Exception:  # noqa: BLE001
        comp = {}
    if comp:
        tiers = comp.get("price_tiers")
        tiers_txt = ""
        if isinstance(tiers, dict):
            tiers_txt = " | ".join(f"{k}: {v}" for k, v in list(tiers.items())[:4])
        elif isinstance(tiers, list):
            tiers_txt = ", ".join(
                f"{_money(_g(t, 'min', 'low'))}-{_money(_g(t, 'max', 'high'))} "
                f"({_g(t, 'count', 'listings')})" for t in tiers[:4])
        L += [
            "## Competition", "",
            f"- Saturation: **{_clean(comp.get('saturation'))}** | "
            f"seller concentration index {comp.get('seller_concentration_index', '-')} "
            f"(higher = fewer shops dominate)",
            f"- New sellers entering: **{_pct(comp.get('new_entrant_rate'))}** | "
            f"avg listing age {_int(comp.get('avg_listing_age_days'))}d",
        ]
        if tiers_txt:
            L.append(f"- Price tiers: {tiers_txt}")
        L += [f"- **Read:** _{_clean(comp.get('recommended_action'))}_"
              f"{' — ' + _clean(comp.get('action_reason')) if comp.get('action_reason') else ''}",
              ""]

    listings = _g(rk, "top_listings") or comp.get("top_listings") or []
    if listings:
        L += ["## What's winning now (do NOT copy — study the angle)", "",
              "| Listing | Price | Sold 24h | Total sold | Conv |",
              "|---|---|---|---|---|"]
        for r in listings[:8]:
            L.append(
                f"| {_clean(_g(r, 'title'))[:70]} | {_money(_g(r, 'price'))} "
                f"| {_int(_g(r, 'sold_24h'))} | {_int(_g(r, 'total_sold'))} "
                f"| {_pct(_g(r, 'conversion_rate'))} |")
        L.append("")

    related = _g(rk, "related_keywords") or []
    if not related:
        try:
            en = mcp.call("ytrends_explore_niche", seed=kw)
            related = (en.get("data", {}) or {}).get("adjacent_tags") or []
        except Exception:  # noqa: BLE001
            related = []
    L += ["## Related keywords to consider", ""] + _rel_rows(related) + [""]
    L += ["---", "_Next: pick a clean (Trademark OK) keyword, then ask the "
          "operator to build a listing pack for it, or run `expand` on it._"]
    return "\n".join(L)


def expand_keyword(kw):
    """Related keywords for a seed — the browser version of `main.py expand`."""
    kw = kw.strip()
    L = [f"# Expand — {kw}", "",
         "_Related keywords from the live YTrends index. Verify trademark "
         "before use._", ""]
    related = []
    try:
        rk = mcp.research_keyword(kw)
        related = (rk.get("related_keywords") if isinstance(rk, dict) else None) or []
    except Exception:  # noqa: BLE001
        related = []
    if not related:
        try:
            en = mcp.call("ytrends_explore_niche", seed=kw)
            related = (en.get("data", {}) or {}).get("adjacent_tags") or []
        except Exception:  # noqa: BLE001
            related = []
    L += _rel_rows(related, limit=25)
    return "\n".join(L)
