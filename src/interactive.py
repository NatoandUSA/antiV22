"""Interactive keyword lookups for the team portal — a teammate types a keyword
and gets a live answer in the browser, no terminal, no waiting on the operator.

All data is live from the official YTrends MCP (src/ytrends_mcp). Read-only:
these functions only fetch + format, they never run shell or write files. Output
is Markdown so the portal renders it with the same styling as the reports.
"""
from src import ytrends_mcp as mcp
from src.discover import matches_mode
from src.trademark import check as tm_check

MODE_LABEL = {"pod": "Print on Demand", "embroidery": "Embroidery",
              None: "All lines"}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


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


def _competition(kw):
    try:
        c = mcp.call("ytrends_analyze_competition", seed=kw, seed_type="keyword")
        return c.get("data", c) if isinstance(c, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _momentum_for(kw):
    """momentum_score / opportunity_score for one keyword, best-effort."""
    try:
        for t in mcp.trending_keywords(limit=8, search=kw):
            if (t.get("tag") or "").lower() == kw.lower():
                return t
        for r in mcp.scout_opportunities(limit=8, search=kw):
            if (r.get("tag") or "").lower() == kw.lower():
                return r
    except Exception:  # noqa: BLE001
        pass
    return {}


def should_sell(kw):
    """GO / CONDITIONAL GO / NO-GO verdict for a niche, with the reasons."""
    kw = kw.strip()
    comp = _competition(kw)
    try:
        stats = (mcp.research_keyword(kw) or {}).get("stats", {})
    except Exception:  # noqa: BLE001
        stats = {}
    mo = _momentum_for(kw)
    risk, reason = tm_check(kw.lower())

    signals = []
    sat = (comp.get("saturation") or "").lower()
    if sat == "low":
        signals.append(("Competition", "GO", "market saturation is low"))
    elif sat == "high":
        signals.append(("Competition", "NO", "market saturation is high"))
    else:
        signals.append(("Competition", "MIXED", f"saturation {sat or 'unknown'}"))

    conv, dsr = _f(stats.get("avg_conversion_rate")), _f(stats.get("demand_supply_ratio"))
    if conv >= 0.025 and dsr >= 0.8:
        signals.append(("Demand", "GO", f"conversion {conv*100:.1f}% + healthy demand"))
    elif conv and conv < 0.015:
        signals.append(("Demand", "NO", f"weak conversion {conv*100:.1f}%"))
    else:
        signals.append(("Demand", "MIXED",
                        f"conversion {conv*100:.1f}%" if conv else "thin demand data"))

    ms = mo.get("momentum_score")
    if ms is not None:
        if ms > 55:
            signals.append(("Momentum", "GO", f"momentum {ms} (rising)"))
        elif ms < 45:
            signals.append(("Momentum", "NO", f"momentum {ms} (cooling)"))
        else:
            signals.append(("Momentum", "MIXED", f"momentum {ms}"))
    else:
        rc = _f(stats.get("rank_change_7d"))
        signals.append(("Momentum",
                        "GO" if rc < 0 else "NO" if rc > 0 else "MIXED",
                        "rank rising this week" if rc < 0 else
                        "rank slipping this week" if rc > 0 else "rank flat"))

    ner = _f(comp.get("new_entrant_rate"))
    if ner > 0 and sat != "high":
        signals.append(("Room to enter", "GO", f"{ner*100:.1f}% new sellers getting in"))
    else:
        signals.append(("Room to enter", "MIXED", f"{ner*100:.1f}% new sellers"))

    go = sum(1 for _, v, _ in signals if v == "GO")
    no = sum(1 for _, v, _ in signals if v == "NO")
    if risk == "HIGH":
        verdict, why = "NO-GO", ("the trademark risk on this exact phrase is HIGH "
                                 "— pick a different wording")
    elif go >= 3 and no == 0:
        verdict, why = "GO", "the signals line up in your favor"
    elif no >= 3:
        verdict, why = "NO-GO", "too many signals work against it"
    else:
        verdict, why = "CONDITIONAL GO", "mixed signals — enter carefully or narrow the niche"

    icon = {"GO": "✅ good", "NO": "❌ bad", "MIXED": "🟡 mixed"}
    L = [f"# Should I sell: {kw}?", "", f"## Verdict: **{verdict}**", "",
         f"_{why}._", "", "| Signal | Read | Why |", "|---|---|---|"]
    for name, v, detail in signals:
        L.append(f"| {name} | {icon[v]} | {detail} |")
    L += ["", f"**Trademark:** {risk} — "
          f"{reason or 'no obvious brand match (still verify on USPTO)'}"]
    if comp.get("recommended_action"):
        L.append(f"\n**YTrends read:** {_clean(comp.get('recommended_action'))} — "
                 f"{_clean(comp.get('action_reason'))}")
    L += ["", "_Next: **Analyze** for the full numbers, or **Draft listing** to start._"]
    return "\n".join(L)


def trending(mode=None):
    picks = [t for t in mcp.trending_keywords(limit=45)
             if matches_mode((t.get("tag") or "").lower(), mode)][:20]
    L = [f"# Trending now — {MODE_LABEL.get(mode)}", "",
         "_Rising keywords in the live index. Market intel — verify trademark._", "",
         "| Keyword | Momentum | Competition | Conv | Avg price | Trademark |",
         "|---|---|---|---|---|---|"]
    for t in picks:
        tag = _clean(t.get("tag"))
        risk, _ = tm_check(tag.lower())
        L.append(f"| {tag} | {t.get('momentum_score', '-')} "
                 f"| {_clean(t.get('competition_level'))} "
                 f"| {_pct(t.get('avg_conversion_rate'))} "
                 f"| {_money(t.get('avg_price'))} | {risk} |")
    if not picks:
        L.append("_No trending keywords for this line right now._")
    return "\n".join(L)


def opportunities(mode=None):
    picks = [r for r in mcp.scout_opportunities(limit=50)
             if matches_mode((r.get("tag") or "").lower(), mode)][:20]
    L = [f"# Opportunities — {MODE_LABEL.get(mode)}", "",
         "_Sweet-spot niches: low competition + high opportunity score. "
         "Verify trademark._", "",
         "| Keyword | Opportunity | Momentum | Sellers | Conv | Avg price | Trademark |",
         "|---|---|---|---|---|---|---|"]
    for r in picks:
        tag = _clean(r.get("tag"))
        risk, _ = tm_check(tag.lower())
        L.append(f"| {tag} | {r.get('opportunity_score', '-')} "
                 f"| {r.get('momentum_score', '-')} | {_int(r.get('sellers'))} "
                 f"| {_pct(r.get('avg_conversion_rate'))} "
                 f"| {_money(r.get('avg_price_usd'))} | {risk} |")
    if not picks:
        L.append("_No opportunities for this line right now._")
    return "\n".join(L)


def calendar():
    events = mcp.trend_calendar(window="next_90d", limit=25)
    L = ["# Seasonal calendar — next 90 days", "",
         "_Event-tied niches gaining demand. Launch **4–6 weeks before** the peak "
         "so listings have time to rank._", "",
         "| Niche | Listings | Conv | Avg price | Sold 24h | Trademark |",
         "|---|---|---|---|---|---|"]
    for e in events:
        tag = _clean(e.get("tag"))
        risk, _ = tm_check(tag.lower())
        L.append(f"| {tag} | {_int(e.get('listing_count'))} "
                 f"| {_pct(e.get('avg_conversion_rate'))} "
                 f"| {_money(e.get('avg_price_usd'))} "
                 f"| {_int(e.get('total_sold_24h'))} | {risk} |")
    if not events:
        L.append("_No calendar data right now._")
    return "\n".join(L)


def draft_listing(kw):
    """A first-draft listing pack (title, 13 tags, price, description) built from
    live keyword data. DRAFT ONLY — the team reviews + personalizes before use."""
    kw = kw.strip()
    try:
        rk = mcp.research_keyword(kw)
        stats = rk.get("stats", {}) if isinstance(rk, dict) else {}
        related = (rk.get("related_keywords") if isinstance(rk, dict) else None) or []
    except Exception:  # noqa: BLE001
        stats, related = {}, []
    risk, reason = tm_check(kw.lower())

    tags, seen = [], set()
    for cand in [kw] + [_g(r, "tag", "keyword", "title") for r in related]:
        c = (cand or "").strip().lower()
        if c and c not in seen and 3 <= len(c) <= 20:
            r2, _ = tm_check(c)
            if r2 != "HIGH":
                seen.add(c)
                tags.append(c)
        if len(tags) >= 13:
            break

    title = kw.title()
    lo, hi = _money(stats.get("price_p25")), _money(stats.get("price_p75"))
    mid = _money(stats.get("median_price"))
    L = [f"# Listing draft — {kw}", "",
         "> **DRAFT for review — do NOT publish as-is.** Verify the trademark, "
         "personalize the copy, add your own photos.", ""]
    if risk == "HIGH":
        L += [f"⚠️ **Trademark risk is HIGH on '{kw}'** — {reason}. Change the "
              "wording before using it.", ""]
    L += ["## Suggested title",
          f"`{title} — Personalized Gift, Custom [Detail], Gift for [Recipient]`", "",
          "_Front-load the keyword; fill the [brackets]; keep under ~140 chars._", "",
          "## 13 tags (clean of obvious trademarks)", ""]
    L += ["- " + t for t in tags[:13]]
    if len(tags) < 13:
        L.append(f"_(only {len(tags)} clean tags found — add "
                 f"{13 - len(tags)} more of your own)_")
    L += ["", "## Price guidance",
          f"- Typical selling range **{lo}–{hi}** (midpoint ~{mid}). Price for "
          "your margin — embroidery cost ~$17, POD ~$9–12.", "",
          "## Description skeleton", "", "```",
          f"{title} — made just for you.", "",
          "★ Personalized: [what the buyer customizes]",
          "★ Material / size: [fill in]",
          "★ Ships in [X] business days", "",
          "How to order:",
          "1. Add to cart", "2. Leave your personalization in the note to seller",
          "3. We make it and ship", "",
          "Perfect gift for [occasion / recipient].", "```", "",
          f"**Trademark:** {risk} — {reason or 'verify on USPTO before publishing'}", ""]
    return "\n".join(L)
