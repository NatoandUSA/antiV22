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

# How deep to pull the (server-paginated) keyword surfaces, and how many
# launch-ready ideas to show/cluster per page. The raw pull is mode-independent
# (mode filtering happens after fetch), so warm_cache() warms all three modes at
# once. Deep pull + per-day cache: only the first load of the day pays for it.
PULL = 100
SHOW = 50


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
    # Strip "|" (breaks md tables), newlines, and "<>" (third-party listing
    # titles/tags flow into markdown raw-HTML — neutralize any injected tags).
    return (str(t or "").replace("|", "/").replace("\n", " ")
            .replace("<", "").replace(">", "").strip())


def _g(d, *keys):
    """First present, non-None value among keys."""
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return None


def _rel_rows(items, limit=15):
    """Render a related-keyword list (shapes vary by tool) as a Markdown table."""
    # Listings + avg-price aren't returned by the suggestions feed (they'd always
    # render "-"), so we drop those dead columns rather than show empty cells.
    out = ["| Keyword | Conv | Trademark |", "|---|---|---|"]
    n = 0
    for r in items or []:
        tag = _clean(_g(r, "tag", "keyword", "title", "term"))
        if not tag:
            continue
        risk, _ = tm_check(tag.lower())
        out.append(
            f"| {tag} "
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


def _split_fit(rows, key, mode, want=SHOW):
    """Classify rows by product-fit; return (launchable[:want], junk).

    `junk` is only genuine off-fit (shop names, spells, brands, digital, broad
    seeds) — a real product that simply fits the OTHER mode (e.g. an embroidery
    term while POD is selected) is dropped silently, not shown as 'risky'. This
    is what keeps Embroidery mode from being starved: themes stay launchable in
    both modes, and POD products just don't appear under Embroidery."""
    from src import product_fit as pf
    good, junk = [], []
    for r in rows:
        c = pf.classify(r.get(key) or "", mode)
        r["_fit"] = c
        if c["launchable"]:
            good.append(r)
        elif c["status"] not in pf.LAUNCHABLE:   # real junk, not just wrong-mode
            junk.append(r)
    return good[:want], junk


def _hidden_block(hidden, key, show_all):
    if not hidden:
        return []
    L = ["", f"_🔎 {len(hidden)} off-fit / risky ideas hidden — shop names, "
         "spells/psychic, brands, digital, and broad seeds. Toggle **Show risky / "
         "review** to see them._"]
    if show_all:
        L += ["", "## Needs review / risky (NOT launch-ready)", "",
              "| Keyword | Status | Why it's not a launch idea |", "|---|---|---|"]
        for r in hidden[:25]:
            c = r["_fit"]
            L.append(f"| {_clean(r.get(key))} | {c['status']} | {_clean(c['reason'])} |")
    return L


def trending(mode=None, show_all=False):
    # Pull the full pool; product-fit (mode-aware) decides what shows. No mode
    # pre-filter — that used to starve Embroidery by dropping design themes.
    raw = mcp.trending_keywords(limit=PULL)
    picks, hidden = _split_fit(raw, "tag", mode)
    L = [f"# Trending now — {MODE_LABEL.get(mode)}", "",
         "_Rising keywords, **product-fit filtered** (junk hidden). Verify trademark._",
         ""]
    cb = _cluster_block(picks)
    L += cb
    if cb:
        L += ["## Individual keyword ideas", ""]
    L += ["| Keyword | Fit | Momentum | Competition | Conv | Avg price | TM |",
          "|---|---|---|---|---|---|---|"]
    for t in picks:
        tag = _clean(t.get("tag"))
        risk, _ = tm_check(tag.lower())
        L.append(f"| {tag} | {t['_fit']['product_type'] or 'ok'} "
                 f"| {t.get('momentum_score', '-')} "
                 f"| {_clean(t.get('competition_level'))} "
                 f"| {_pct(t.get('avg_conversion_rate'))} "
                 f"| {_money(t.get('avg_price'))} | {risk} |")
    if not picks:
        L.append("_No launch-ready trending keywords for this line right now._")
    return "\n".join(L + _hidden_block(hidden, "tag", show_all))


def _cluster_block(picks, key="tag"):
    """Group the launch-ready keywords into product clusters (build ONE listing
    per cluster that targets all its keywords)."""
    from src import clusters as cl
    groups, _ = cl.cluster([r.get(key) for r in picks])
    if not groups:
        return []
    L = ["## 🧩 Product clusters — build ONE listing per cluster", "",
         "_Related keywords collapsed into a single product idea — build one strong "
         "listing that targets them all, instead of a separate listing for each._",
         "", "| Product idea | Keywords | Base title | Cover these keywords |",
         "|---|---|---|---|"]
    for c in groups[:10]:
        L.append(f"| **{c['name'].title()}** | {c['size']} | {c['primary']} "
                 f"| {', '.join(c['members'])} |")
    return L + [""]


def opportunities(mode=None, show_all=False):
    from src import opportunity_score as oscore
    raw = mcp.scout_opportunities(limit=PULL)
    picks, hidden = _split_fit(raw, "tag", mode)
    L = [f"# Opportunities — {MODE_LABEL.get(mode)}", "",
         "_Launch-ready, **product-fit** ideas only (shop names, spells, brands, "
         "digital + broad seeds filtered out). Opp score = composite 0-100 "
         "(WATCH when core data is incomplete). Verify trademark._", ""]
    L += _cluster_block(picks)
    L += ["## Individual keyword ideas", "",
          "| Keyword | Fit | Opportunity | Momentum | Sellers | Conv | Avg price | TM | Opp score |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in picks:
        tag = _clean(r.get("tag"))
        risk, _ = tm_check(tag.lower())
        L.append(f"| {tag} | {r['_fit']['product_type'] or 'ok'} "
                 f"| {r.get('opportunity_score', '-')} "
                 f"| {r.get('momentum_score', '-')} | {_int(r.get('sellers'))} "
                 f"| {_pct(r.get('avg_conversion_rate'))} "
                 f"| {_money(r.get('avg_price_usd'))} | {risk} "
                 f"| {oscore.cell(r, keyword=tag, mode=mode)} |")
    if not picks:
        L.append("_No launch-ready opportunities for this line right now._")
    return "\n".join(L + _hidden_block(hidden, "tag", show_all))


# ---- Hidden gems: full sortable review table (#3) ----------------------------
def gems(mode=None, show_all=False):
    """Hidden Gems as a full review table (previously only folded into Market
    Pulse). High-conversion, low-competition niches a NEW shop can rank for."""
    from src import signals, opportunity_score as oscore
    raw = mcp.hidden_gems(limit=PULL)
    picks, hidden = _split_fit(raw, "tag", mode)
    L = [f"# Hidden gems - {MODE_LABEL.get(mode)}", "",
         "_Underexploited niches: high conversion + low competition. gem_score is "
         "YTuong's opportunity rank; Opp score is the composite 0-100 verdict "
         "(WATCH when core data is incomplete). Verify trademark before building._", ""]
    L += _cluster_block(picks)
    L += ["## Individual gems", "",
          "| Keyword | Fit | Gem score | Listings | Sellers | L/S | Conv | "
          "Sold 24h | Trend | Avg price | TM | Opp score |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in picks:
        tag = _clean(t.get("tag"))
        risk, _ = tm_check(tag.lower())
        listings = _g(t, "listing_count", "listings")
        sellers = _g(t, "seller_count", "sellers")
        ls = (round(listings / sellers, 1)
              if isinstance(listings, (int, float))
              and isinstance(sellers, (int, float)) and sellers else "-")
        phase, _note = signals.trend_velocity(
            momentum_score=_g(t, "momentum_score", "gem_score"))
        gem = t.get("gem_score", "-")
        action = oscore.cell(t, keyword=tag, mode=mode)
        L.append(f"| {tag} | {t['_fit']['product_type'] or 'ok'} | {gem} "
                 f"| {_int(listings)} | {_int(sellers)} | {ls} "
                 f"| {_pct(_g(t, 'avg_conversion_rate', 'conversion_rate'))} "
                 f"| {_int(_g(t, 'sold_24h'))} | {phase} "
                 f"| {_money(_g(t, 'avg_price', 'avg_price_usd'))} | {risk} | {action} |")
    if not picks:
        L.append("_No launch-ready hidden gems for this line right now._")
    return "\n".join(L + _hidden_block(hidden, "tag", show_all))


# ---- Newest fresh winners: browsable review list (#2) ------------------------
def _why_hot(r):
    """One-line 'why is this new listing outperforming' from the peer signals."""
    reasons = []
    op = r.get("outperforms_peers_on")
    if op:
        reasons.append(_clean(op) if isinstance(op, str)
                       else ", ".join(_clean(x) for x in op))
    cr = _g(r, "peer_conversion_ratio")
    if isinstance(cr, (int, float)) and cr > 1:
        reasons.append(f"{cr:.1f}x peer conv")
    vr = _g(r, "peer_views_ratio")
    if isinstance(vr, (int, float)) and vr > 1:
        reasons.append(f"{vr:.1f}x peer views")
    if not reasons:
        ps = _g(r, "performance_score")
        if ps is not None:
            reasons.append(f"performance {ps}")
    return "; ".join(reasons) or "new + already selling"


def newest(mode=None, show_all=False):
    """Brand-new listings already outperforming their niche. Study the ANGLE
    (what/why it's working) and the gap - never copy the design, title, or tags."""
    from src import product_fit as pf
    raw = mcp.browse_new_listings(limit=60)
    picks, junk = [], 0
    for r in raw:
        hay = " ".join([_clean(r.get("primary_tag")), _clean(r.get("title")),
                        " ".join(str(t) for t in (r.get("tags") or []))]).lower()
        c = pf.classify(hay, mode)
        if c["launchable"]:
            picks.append(r)
        elif c["status"] not in pf.LAUNCHABLE:
            junk += 1
    picks = picks[:SHOW]
    L = [f"# Newest fresh winners - {MODE_LABEL.get(mode)}", "",
         "_Brand-new listings (young + already outperforming peers). Study the angle "
         "and the gap to beat them - never copy the design, title, or tags._", "",
         "| Listing | Price | Perf | Sold 24h | Conv | Age | Why it's hot | Sample tags |",
         "|---|---|---|---|---|---|---|---|"]
    for r in picks:
        title = _clean(r.get("title"))[:60]
        tags = ", ".join(_clean(t) for t in (r.get("tags") or [])[:4])
        L.append(f"| {title} | {_money(_g(r, 'price_usd', 'price'))} "
                 f"| {_g(r, 'performance_score') if _g(r, 'performance_score') is not None else '-'} "
                 f"| {_int(_g(r, 'sold_24h'))} "
                 f"| {_pct(_g(r, 'conversion_rate', 'avg_conversion_rate'))} "
                 f"| {_int(_g(r, 'listing_age_days'))}d | {_why_hot(r)} | {tags} |")
    if not picks:
        L.append("_No mode-matching fresh winners in the index this run._")
    if junk:
        L += ["", f"_{junk} off-fit new listings hidden (other mode / not a product)._"]
    return "\n".join(L)


# ---- Category intelligence: whole-category demand vs supply (#1) -------------
def _cat_verdict(opp, ds):
    if isinstance(opp, (int, float)):
        return "ENTER" if opp >= 70 else "NICHE DOWN" if opp >= 45 else "AVOID"
    if isinstance(ds, (int, float)):
        return "ENTER" if ds >= 1.5 else "NICHE DOWN" if ds >= 0.8 else "AVOID"
    return "REVIEW"


def category_intel(sort="opportunity"):
    """Category-level market intelligence: whole-category demand vs supply, so you
    pick an underserved CATEGORY before hunting keywords inside it. Category stats
    come from the YTuong REST endpoint (needs the cookie); degrades honestly if
    that path isn't configured, rather than inventing numbers."""
    from src import deeplinks as dl
    sort = sort if sort in ("opportunity", "revenue", "conversion",
                            "sellers") else "opportunity"
    err = ""
    try:
        from src.ytrends_client import categories as _cats
        rows = _cats(sort=sort, limit=40) or []
    except (SystemExit, Exception) as exc:  # noqa: BLE001
        # ytrends_client raises SystemExit (a BaseException) on 401 -- catching only
        # Exception let it escape to the generic route handler, so this graceful
        # block never rendered for the most common failure.
        rows, err = [], " ".join(str(exc).split())[:160]
    L = ["# Category intelligence", "",
         "_Whole-category demand vs supply - find an underserved CATEGORY first, "
         f"then pick keywords inside it. Sorted by {sort}._", ""]
    if not rows:
        # Extension path first: category data POSTed by the YTrends Exporter to
        # /api/import lands in data/imports/category_intel.csv, so the Categories
        # page works even without the REST cookie described below.
        try:
            from src import ytx_import
            imported = ytx_import.latest_categories()
        except Exception:  # noqa: BLE001
            imported = []
        if imported:
            def _cg(c, *keys):
                return next((c[k] for k in keys if c.get(k)), "-")
            L += [f"_Source: your latest YTrends extension import "
                  f"({len(imported)} categories)._", "",
                  "| Category | Listings | Sellers | Demand/Supply | Revenue | "
                  "Avg price | Conv | Competition | Opportunity | Verdict |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
            for c in imported:
                L.append(f"| {_clean(_cg(c, 'Category', 'category'))} "
                         f"| {_cg(c, 'Listings')} | {_cg(c, 'Sellers')} "
                         f"| {_cg(c, 'Demand/Supply')} | {_cg(c, 'Revenue')} "
                         f"| {_cg(c, 'Avg Price')} | {_cg(c, 'Conversion')} "
                         f"| {_cg(c, 'Competition')} | {_cg(c, 'Opportunity')} "
                         f"| {_cg(c, 'Verdict')} |")
            return "\n".join(L)
        L += ["> **Category data unavailable this run.**", ">",
              "> Category stats come from the YTuong REST endpoint, which needs your "
              "logged-in browser cookie in `.env` as **`YTRENDS_COOKIE`**. (The MCP "
              "index every other page uses does not expose categories.)", ">",
              "> **Fix (~1 minute):** open **trends.ytuong.ai** logged in -> `F12` -> "
              "**Network** tab -> refresh -> click the request named **`keywords`** -> "
              "**Request Headers** -> copy the FULL value of the `cookie:` line -> add "
              "`YTRENDS_COOKIE=<paste it>` to `.env` -> restart the app. Cookies expire, "
              "so re-copy it if 401 comes back. **Never share the cookie or `.env`** - "
              "it is your login session.",
              (f"> _(reason: {err})_" if err else ""), ">",
              f"> Or view them directly on YTuong: {dl.YTUONG}/categories"]
        return "\n".join(L)
    L += ["| Category | Listings | Sellers | Demand/Supply | Revenue | Avg price | "
          "Conv | Competition | Opportunity | Verdict |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for c in rows:
        name = _clean(_g(c, "category", "name", "path"))
        ds = _g(c, "demand_supply_ratio", "demand_supply")
        opp = _g(c, "opportunity_score", "opportunity")
        L.append(f"| {name} | {_int(_g(c, 'listing_count', 'listings'))} "
                 f"| {_int(_g(c, 'seller_count', 'sellers'))} "
                 f"| {ds if ds is not None else '-'} "
                 f"| {_money(_g(c, 'revenue', 'total_revenue'))} "
                 f"| {_money(_g(c, 'avg_price', 'avg_price_usd'))} "
                 f"| {_pct(_g(c, 'avg_conversion_rate', 'conversion'))} "
                 f"| {_clean(_g(c, 'competition_level', 'competition'))} "
                 f"| {opp if opp is not None else '-'} | {_cat_verdict(opp, ds)} |")
    return "\n".join(L)


# ---- Daily brief: scored, ranked build-list for the morning (Doc 2) ----------
def daily_brief(mode=None):
    """The morning operating brief: today's opportunities + hidden gems, scored by
    the composite Opportunity Score and ranked GO -> CONDITIONAL -> WATCH, plus the
    seasonal launch windows. One screen the manager reads first each day."""
    from src import opportunity_score as oscore, seasonal
    pool = []
    for fn in (lambda: mcp.scout_opportunities(limit=PULL),
               lambda: mcp.hidden_gems(limit=PULL)):
        try:
            pool += fn()
        except Exception:  # noqa: BLE001 - a dead source shouldn't blank the brief
            pass
    picks, _ = _split_fit(pool, "tag", mode)
    seen, scored = set(), []
    for r in picks:
        tag = _clean(r.get("tag"))
        key = tag.lower()
        if not tag or key in seen:
            continue
        seen.add(key)
        scored.append((oscore.score(r, keyword=tag, mode=mode), tag))
    rank = {"GO": 0, "CONDITIONAL": 1, "WATCH": 2, "SKIP": 3}
    scored.sort(key=lambda x: (rank.get(x[0]["verdict"], 9),
                               -(x[0]["overall_score"] or 0)))
    L = [f"# Daily brief - {MODE_LABEL.get(mode)}", "",
         "_Today's best niches, ranked by the composite Opportunity Score. "
         "Human review + trademark check still required before building._", "",
         "## Build-worthy today (GO / CONDITIONAL)", "",
         "| Keyword | Score | Verdict | Why |", "|---|---|---|---|"]
    go = [x for x in scored if x[0]["verdict"] in ("GO", "CONDITIONAL")][:12]
    if go:
        for s, tag in go:
            L.append(f"| {tag} | {s['overall_score']} | {s['verdict']} "
                     f"| {'; '.join(s['rationale'][:2])} |")
    else:
        L.append("| _nothing scored GO/CONDITIONAL this run_ |  |  |  |")
    watch = [x for x in scored if x[0]["verdict"] == "WATCH"][:8]
    if watch:
        L += ["", "## Watch - need more data or a sharper angle", "",
              "| Keyword | Score | Missing / why |", "|---|---|---|"]
        for s, tag in watch:
            note = ", ".join(s["missing"]) or (s["rationale"][0] if s["rationale"] else "-")
            disp = (s["overall_score"] if s.get("core_complete")
                    and s["overall_score"] is not None else "-")
            L.append(f"| {tag} | {disp} | {note} |")
    try:
        events = seasonal.upcoming_holidays(horizon_days=90, mode=mode)
    except Exception:  # noqa: BLE001
        events = []
    if events:
        L += ["", "## Seasonal launch windows (next 90 days)", "",
              "| Event | Peak | Launch by | Days left |", "|---|---|---|---|"]
        for e in events[:8]:
            L.append(f"| {_clean(e.get('event'))} | {_clean(e.get('peak'))} "
                     f"| {_clean(e.get('launch_by'))} | {_int(e.get('days_until'))} |")
    return "\n".join(L)


# ---- Score the latest browser-extension import (loop-closer) ------------------
def score_import(source=None, mode=None, enrich=False, gtrends=False):
    """Composite-score the most recent YTrends Exporter import and rank it.

    enrich=True fills each row's blanks from the YTrends MCP first, so the score
    rests on real market data instead of the handful of columns the captured
    table happened to show. gtrends=True cross-checks the top rows against free
    Google Trends demand and blends that into the Market score."""
    from src import shortlister_integration as si
    res = si.score_latest(source=source, mode=mode, enrich=enrich, gtrends=gtrends)
    if not res.get("ok"):
        return ("# Score latest import\n\n> **No YTrends extension import found yet.**"
                "\n>\n> On a YTrends page, use the **YTrends Exporter** toolbar and "
                "click **Send to agent**, then reload this page.")
    total = res.get("rows_in_import")
    skipped = (total - res["count"]) if isinstance(total, int) else 0
    scope = "{} scored".format(res["count"])
    if total:
        scope += " of {} captured".format(total)
    if skipped > 0:
        scope += "; {} filtered as junk".format(skipped)
    if res.get("captured_at"):
        scope += ", captured " + res["captured_at"]
    L = [f"# Score latest import - {res['view']}", "",
         f"_Composite Opportunity Score over your last import ({scope}). "
         "Verdicts are advisory - human review + trademark check still required._", ""]
    _qs = "&mode=" + mode if mode else ""
    if enrich:
        L += [f"_Hybrid enrich: ON - {res.get('enriched_count', 0)} row(s) topped up "
              "from the YTrends MCP (+ marks them). Rows the server has no data on "
              "are left as-is rather than guessed._", ""]
    else:
        L += ["_Scored on the captured columns only. "
              f"[Enrich from YTrends MCP](/score-import?enrich=1{_qs}) "
              "to fill the blanks with real market data (slower, uses quota)._", ""]
    if gtrends:
        L += ["_Google Trends: ON - the top rows are cross-checked against free "
              "Google search demand (GT column = 12-month momentum %; blended into "
              "Market). A blank GT means Trends had no read / was rate-limited._", ""]
    else:
        _eq = "&enrich=1" if enrich else ""
        L += ["_[+ Cross-check Google Trends](/score-import?gt=1"
              f"{_eq}{_qs}) to blend free external search demand into the top rows "
              "(slower, may be rate-limited)._", ""]
    L += ["| Keyword | Score | Verdict | M | C | O | GT | Why |",
          "|---|---|---|---|---|---|---|---|"]
    for s in res["results"]:
        sub = s.get("sub_scores", {})

        def _s(k):
            v = sub.get(k)
            return round(v) if isinstance(v, (int, float)) else "-"
        disp = (s["overall_score"] if s.get("core_complete")
                and s["overall_score"] is not None else "-")
        kw = _clean(s["keyword"]) + (" +" if s.get("enriched") else "")
        gt = s.get("gtrends") or {}
        mp = gt.get("momentum_pct")
        gt_cell = (f"{'+' if mp >= 0 else ''}{round(mp)}%"
                   if isinstance(mp, (int, float)) else "-")
        L.append(f"| {kw} | {disp} | {s['verdict']} "
                 f"| {_s('market_potential')} | {_s('competition_health')} "
                 f"| {_s('opportunity_signal')} | {gt_cell} "
                 f"| {'; '.join(s.get('rationale', [])[:2])} |")
    if not res["results"]:
        L.append("_Nothing to score in the latest import._")
    return "\n".join(L)


_SHORTLIST_NEXT = {
    "GO": "Confirm & Assign -> supplier check",
    "CONDITIONAL": "Validate: supplier + competitor audit",
    "WATCH": "Save & recheck in 1-2 weeks",
    "SKIP": "Skip",
}


def _verdict_from(score, risk):
    """Map a real YTrends opportunity_score (0-100) to a verdict. HIGH trademark is
    never launchable; a missing score can't be ranked, so it's WATCH (not invented)."""
    if risk == "HIGH":
        return "SKIP"
    if not isinstance(score, (int, float)):
        return "WATCH"
    if score >= 75:
        return "GO"
    if score >= 60:
        return "CONDITIONAL"
    if score >= 45:
        return "WATCH"
    return "SKIP"


def shortlist(mode="embroidery", limit=10):
    """Rank the current cached Opportunities into an actionable top-N.

    The composite IS the YTrends real `opportunity_score` (0-100) — we never invent a
    number. Only launch-ready, product-fit rows for `mode`; trademark flagged; verdict
    from the real score. Feeds Confirm & Assign. Returns a list of dicts (structured,
    not markdown) so the web layer renders one-click actions."""
    raw = mcp.scout_opportunities(limit=PULL)
    picks, _ = _split_fit(raw, "tag", mode)
    out = []
    for r in picks:
        tag = _clean(r.get("tag"))
        if not tag:
            continue
        risk, _ = tm_check(tag.lower())
        score = r.get("opportunity_score")
        verdict = _verdict_from(score, risk)
        comp = _clean(r.get("competition_level"))
        # "Why it matters" — built only from real fields present on the row.
        bits = []
        if isinstance(score, (int, float)):
            bits.append(f"opportunity {score}/100")
        if comp:
            bits.append(f"{comp} competition")
        if isinstance(r.get("momentum_score"), (int, float)):
            bits.append(f"momentum {r.get('momentum_score')}")
        if risk == "CAUTION":
            bits.append("verify trademark")
        out.append({
            "keyword": tag,
            "product_type": r["_fit"]["product_type"] or "theme",
            "score": score,
            "momentum": r.get("momentum_score"),
            "competition": comp,
            "conversion": r.get("avg_conversion_rate"),
            "price": r.get("avg_price_usd"),
            "tm": risk,
            "verdict": verdict,
            "reason": ", ".join(bits) or "limited signal - needs research",
            "next_action": _SHORTLIST_NEXT.get(verdict, "Review"),
        })
    out.sort(key=lambda x: (x["score"] or 0), reverse=True)
    return out[:limit]


def warm_cache(fresh=False, parallel=False):
    """Pre-fetch the heavy paginated surfaces so the first web load of the day is
    instant. The raw pull is mode-independent, so one pass warms pod/embroidery/all.
    Each page is cached per day; a blocked/slow MCP just no-ops (never raises).
    Called from the daily run — safe to call anytime on the fetching machine.

    fresh=True forces a live re-fetch (overwriting the day's cache) — use it for a
    scheduled every-N-hours warm so the team sees current data, not this morning's.

    parallel=True warms the three surfaces concurrently. The MCP client is
    thread-safe and rate-limited (issue-rate stays <=1/s), so this only overlaps
    the network WAIT between surfaces — a safe ~2-3x speed-up for the unattended
    warm job. Left off by default for any caller that wants the old serial walk."""
    try:   # keep agent.db bounded: the VPS warm cron is the natural place to prune
        from src import db
        db.prune_cache(keep_days=3)
    except Exception:  # noqa: BLE001
        pass
    surfaces = (
        ("trending", lambda: mcp.trending_keywords(limit=PULL, refresh=fresh)),
        ("opportunities", lambda: mcp.scout_opportunities(limit=PULL, refresh=fresh)),
        ("hidden_gems", lambda: mcp.hidden_gems(limit=PULL, refresh=fresh)),
    )

    def _one(item):
        name, fn = item
        try:
            return name, len(fn())
        except (SystemExit, Exception):  # noqa: BLE001 - warming must never break the run
            return name, 0

    warmed = {}
    if parallel:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(surfaces)) as ex:
            for name, n in ex.map(_one, surfaces):
                warmed[name] = n
    else:
        for item in surfaces:
            name, n = _one(item)
            warmed[name] = n
    return ("refreshed " if fresh else "warmed ") + ", ".join(
        f"{k}={v}" for k, v in warmed.items())


def calendar(mode=None, days=180):
    """Upcoming holiday/e-com calendar + live rising keywords + launch-by dates
    and product ideas, within `days`. Delegates to src.seasonal."""
    from src import seasonal
    return seasonal.calendar_plan(mode, days=days)


_SPARK = "▁▂▃▄▅▆▇█"


def sparkline(values):
    """Unicode sparkline from a series (e.g. views over time)."""
    vals = [float(v) for v in values if isinstance(v, (int, float))]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return _SPARK[0] * len(vals)
    return "".join(_SPARK[int((v - lo) / (hi - lo) * (len(_SPARK) - 1))]
                   for v in vals)


def trend_word(values):
    vals = [float(v) for v in values if isinstance(v, (int, float))]
    if len(vals) < 4:
        return "flat"
    n = max(1, len(vals) // 3)
    head, tail = sum(vals[:n]) / n, sum(vals[-n:]) / n
    return ("rising" if tail > head * 1.15 else
            "falling" if tail < head * 0.85 else "flat")


def demand_spark(timeline):
    """A 'demand over 6 months' sparkline line from research_keyword.timeline."""
    if not timeline:
        return ""
    views = [p.get("total_views_24h") for p in timeline]
    sp = sparkline(views)
    if not sp:
        return ""
    return f"Demand (last ~6 mo): `{sp}` — **{trend_word(views)}**"


def _typo_flag(tag):
    from src.workspace import _looks_typo
    return _looks_typo(tag)[1]


def grade_listing(title, tags_str, desc, kw="", mode=None):
    """Grade an EXISTING listing (paste title / 13 tags / description) 0–100 +
    exact fixes. Grade only — never publishes. Modelled on eRank/Marmalead."""
    title = (title or "").strip()
    desc = (desc or "").strip()
    kw = (kw or "").strip().lower()
    tags = [t.strip().lower() for t in (tags_str or "").replace("\n", ",").split(",")
            if t.strip()]
    fixes, comp = [], {}
    tl, dl = title.lower(), desc.lower()

    # Title (25)
    ts = 0
    if kw and tl.startswith(kw[:min(len(kw), 15)]):
        ts += 10
    elif kw and kw in tl:
        ts += 5
        fixes.append("Move the focus keyword to the FRONT of the title.")
    elif kw:
        fixes.append(f"Add '{kw}' to the title, front-loaded.")
    ts += 6 if "," in title else 0
    if "," not in title:
        fixes.append("Use commas to fit 2–3 keyword phrases in the title.")
    if 0 < len(title) <= 140:
        ts += 5
    elif len(title) > 140:
        fixes.append(f"Title is {len(title)} chars — trim to ≤140.")
    ts += 4 if title and not title.isupper() else 0
    comp["Title"] = (ts, 25)

    # Tags (35)
    gs, n = 0, len(tags)
    gs += 12 if n == 13 else max(0, int(12 * n / 13))
    if n != 13:
        fixes.append(f"You have {n}/13 tags — use all 13.")
    chars = sum(len(t) for t in tags)
    eff = chars / 260 if tags else 0
    gs += int(8 * min(1, eff))
    if eff < 0.6:
        fixes.append(f"Tags use {chars}/260 chars — pack longer multi-word tags.")
    typos = [t for t in tags if _typo_flag(t)]
    gs += 0 if typos else 5
    if typos:
        fixes.append(f"Fix typo tags: {', '.join(typos[:3])}.")
    caution = [t for t in tags if tm_check(t)[0] in ("HIGH", "CAUTION")]
    gs += 0 if caution else 5
    if caution:
        fixes.append(f"Trademark-risky tags — remove/verify: {', '.join(caution[:3])}.")
    if kw and any(kw in t for t in tags):
        gs += 5
    elif kw:
        fixes.append("Add the focus keyword as one of the 13 tags.")
    comp["Tags"] = (min(gs, 35), 35)

    # Description (25)
    ds = 0
    if kw and kw in dl:
        ds += 8
    elif kw:
        fixes.append("Mention the focus keyword in the first line of the description.")
    ds += 7 if len(desc) >= 100 else 0
    if len(desc) < 100:
        fixes.append("Description is thin — add materials, personalization, shipping.")
    if any(w in dl for w in ("personaliz", "custom", "name", "monogram")):
        ds += 5
    else:
        fixes.append("State the personalization + how to order.")
    if any(w in dl for w in ("ship", "processing", "delivery")):
        ds += 5
    else:
        fixes.append("Add a clear shipping / processing note.")
    comp["Description"] = (ds, 25)

    # Focus-keyword consistency (15)
    if kw:
        hits = sum([kw in tl, any(kw in t for t in tags), kw in dl])
        cs = int(15 * hits / 3)
        if hits < 3:
            fixes.append("Use the SAME focus keyword in the title, a tag, AND the description.")
    else:
        cs = 8
        fixes.append("Set a focus keyword so consistency can be graded.")
    comp["Focus keyword"] = (cs, 15)

    total = sum(s for s, _ in comp.values())
    band = ("A — strong" if total >= 85 else "B — good" if total >= 70 else
            "C — needs work" if total >= 55 else "D — weak" if total >= 40
            else "F — rebuild")
    L = [f"# Listing grade: {total}/100 ({band})", "", "| Component | Score |",
         "|---|---|"]
    for name, (s, m) in comp.items():
        L.append(f"| {name} | {s}/{m} |")
    L += ["", f"_Tags use {chars}/260 characters ({int(eff*100)}% of the space)._",
          "", "## Fixes (do these first)"]
    L += (["- " + f for f in fixes] if fixes
          else ["- Looks strong — only minor polish needed."])
    L += ["", "_Grade only — never auto-published. Verify any flagged trademark "
          "on USPTO before publishing._"]
    return "\n".join(L)


_PLACEHOLDERS = ("tbd", "xxx", "placeholder", "lorem", "todo", "your text here",
                 "[", "insert ", "example")


def analyze_listing(title, tags_str, desc, kw="", mode=None,
                    first_image_ready=False, supplier_ok=False):
    """Full pre-publish Listing Analyzer (Helium-10 Listing Analyzer idea, Etsy
    rules). Returns markdown with Listing / SEO / Trust / Image sub-scores + a
    hard publish gate and the EXACT failed checks. Never publishes."""
    title = (title or "").strip()
    desc = (desc or "").strip()
    kw = (kw or "").strip().lower()
    tags = [t.strip().lower() for t in (tags_str or "").replace("\n", ",").split(",")
            if t.strip()]
    tl, dl = title.lower(), desc.lower()
    failed = []

    # --- SEO (0-100) ---
    seo = 0
    if kw and tl.startswith(kw[:min(len(kw), 15)]):
        seo += 25
    elif kw and kw in tl:
        seo += 14
        failed.append("Move the focus keyword to the FRONT of the title.")
    elif kw:
        failed.append(f"Add '{kw}' to the title, front-loaded.")
    n = len(tags)
    seo += 20 if n == 13 else max(0, int(20 * n / 13))
    if n != 13:
        failed.append(f"Use exactly 13 tags (have {n}).")
    chars = sum(len(t) for t in tags)
    seo += int(15 * min(1, chars / 260))
    if chars < 156:
        failed.append(f"Tags use {chars}/260 chars — pack longer multi-word tags.")
    longtail = sum(1 for t in tags if len(t.split()) >= 2)
    seo += 15 if longtail >= 8 else int(15 * longtail / 8)
    typos = [t for t in tags if _typo_flag(t)]
    seo += 0 if typos else 15
    if typos:
        failed.append(f"Fix typo tags: {', '.join(typos[:3])}.")
    tm_high = [t for t in tags if tm_check(t)[0] == "HIGH"]
    tm_caution = [t for t in tags if tm_check(t)[0] == "CAUTION"]
    seo += 0 if tm_high else 10   # only real brands cost SEO points
    if tm_high:
        failed.append(f"Remove trademark tags (known brand): {', '.join(tm_high[:3])}.")
    if tm_caution:
        failed.append(f"Verify + manager-approve slogan-like tags: {', '.join(tm_caution[:3])}.")
    seo = min(100, seo)

    # --- Buyer Trust (0-100) ---
    trust = 0
    if any(w in dl for w in ("personaliz", "custom", "name", "monogram")):
        trust += 30
    else:
        failed.append("State the personalization + exactly how to order it.")
    if any(w in dl for w in ("ship", "processing", "delivery", "arrive")):
        trust += 30
    else:
        failed.append("Add a clear shipping / processing-time note.")
    if any(w in dl for w in ("material", "cotton", "acrylic", "metal", "thread",
                             "fabric", "size")):
        trust += 20
    else:
        failed.append("Name the material / size so buyers trust the product.")
    trust += 20 if len(desc) >= 100 else int(20 * len(desc) / 100)
    if len(desc) < 100:
        failed.append("Description is thin — add materials, personalization, shipping.")
    trust = min(100, trust)

    # --- Image Readiness (0-100) ---
    image = 85 if first_image_ready else 40
    if not first_image_ready:
        failed.append("First image not confirmed ready (needs the First Image Battle ≥ 75).")

    # --- placeholders + supplier ---
    ph = [t for t in tags + [title, desc] if any(p in t.lower() for p in _PLACEHOLDERS)]
    if ph:
        failed.append("Remove placeholder text before publishing.")
    if not supplier_ok:
        failed.append("Supplier not confirmed (SUPPLIER_CONFIRMED required).")

    clean_tags = n == 13 and not typos and not tm_high and not tm_caution
    listing_score = round(seo * 0.40 + trust * 0.30 + image * 0.30)
    gate = (seo >= 75 and trust >= 70 and image >= 75 and clean_tags
            and first_image_ready and supplier_ok and not ph
            and bool(kw) and kw in tl and any(kw in t for t in tags) and kw in dl)
    if kw and not (kw in tl and any(kw in t for t in tags) and kw in dl):
        failed.append("Use the SAME focus keyword in title, a tag, AND the description.")

    L = [f"# 📋 Listing Analyzer — {title[:48] or '(no title)'}", "",
         "| Score | /100 |", "|---|---|",
         f"| **Listing Score** | **{listing_score}** |",
         f"| SEO Score | {seo} |",
         f"| Buyer Trust Score | {trust} |",
         f"| Image Readiness Score | {image} |", "",
         f"**Publish Gate: {'true' if gate else 'false'}**", ""]
    if gate:
        L += ["✅ All pre-publish checks pass. Manager approval + manual publish "
              "only — the tool never publishes for you."]
    else:
        L += ["## ⛔ DRAFT ONLY — DO NOT PUBLISH", "", "**FAILED_PUBLISH_CHECKS:**"]
        L += [f"- {f}" for f in failed] or ["- (none listed)"]
    L += ["", f"_Tags: {n}/13 · {chars}/260 chars · {longtail} long-tail. "
          "Grade only — never auto-published._"]
    return "\n".join(L)


def ads_readiness(publish_ready, first_image_score, offer_score, margin=0.0,
                  has_traffic=False, price=0.0):
    """Etsy Ads readiness — MANUAL only. Decides if a listing is worth testing
    Etsy Ads; never runs ads. Returns markdown."""
    checks = {
        "PUBLISH_READY is true": bool(publish_ready),
        "First-image score ≥ 75": first_image_score >= 75,
        "Offer strength ≥ 70": offer_score >= 70,
        "Margin supports ad spend (≥ 25%)": margin >= 0.25,
        "Has early traffic / strong confidence": bool(has_traffic) or publish_ready,
    }
    ready = all(checks.values())
    budget = "$3–5/day" if margin < 0.4 else "$5–10/day"
    L = [f"# 📣 Etsy Ads Readiness — {'READY' if ready else 'NOT READY'}", "",
         "_Manual only — the tool never runs ads. This just says whether it's "
         "worth testing Etsy Ads yourself._", "",
         f"**ADS_READY: {'true' if ready else 'false'}**", "",
         "| Check | OK |", "|---|---|"]
    L += [f"| {k} | {'✅' if v else '❌'} |" for k, v in checks.items()]
    if ready:
        L += ["", f"- **Suggested test budget:** {budget}",
              "- **Suggested test duration:** 7–10 days",
              "- **Keywords to watch:** your 3 strongest long-tail tags",
              "- **Stop rule:** kill if ACOS > your margin after 10 days / 30 clicks.",
              "- **Scale rule:** raise budget only if orders come in profitably."]
    else:
        L += ["", "- Not worth ad spend yet — fix the ❌ checks first "
              "(publish-ready + first image + offer + margin)."]
    return "\n".join(L)


def _spy_feasibility(kw, mode):
    """Mode-aware 'can we actually make this?' — supplier match per mode + the
    design rules for that production method. Embroidery must check embroidery
    suppliers, POD must check POD suppliers."""
    from src import supplier_ops as so

    def best(mm):
        try:
            scored = so.match(kw, mode=mm, verbose=False)
        except Exception:  # noqa: BLE001
            scored = []
        return scored[0] if scored else None

    def line(mm):
        b = best(mm)
        if not b or b[0] <= 0:
            return (f"- **{mm.upper()}**: no matching supplier products on file — "
                    "**VALIDATE_SUPPLIER_FIRST** (PUBLISH_READY stays false).")
        sc, r = b
        band = ("strong" if sc >= 90 else "usable" if sc >= 70
                else "weak" if sc >= 50 else "too weak")
        warn = "" if sc >= 50 else " — ⚠️ VALIDATE_SUPPLIER_FIRST"
        return (f"- **{mm.upper()}**: best supplier **{_clean(r.get('supplier_name')) or '?'}** "
                f"({r.get('supplier_status', '')}) — match {sc}/100 ({band}){warn}")

    head = {"pod": "POD", "embroidery": "Embroidery",
            "both": "POD or Embroidery"}[mode]
    L = [f"## Can we make this in {head}? (supplier feasibility)", ""]
    L += [line("pod"), line("embroidery")] if mode == "both" else [line(mode)]
    if mode == "embroidery":
        L += ["", "**Embroidery design rules:** bold + simple — no gradients, no fine "
              "detail, ≤ 6 thread colors. Chenille / monogram / name convert; "
              "photoreal art does not. Confirm embroidery_area + stitch_limit first."]
    elif mode == "pod":
        L += ["", "**POD design rules:** high-res, print-ready art with a transparent "
              "background, inside the print area. Confirm print_method + mockups."]
    else:
        L += ["", "**Both:** Embroidery = premium price, stitch-safe art only, slower "
              "production. POD = cheaper, faster, full-colour. Pick per margin + design."]
    return L + [""]


def _spy_reverse(listings, mode, limit=3):
    """Competitor Reverse Engine — decode the strongest competitors' playbook:
    keyword/tag strategy, price positioning, offer angle, strength, weakness, and
    how WE beat them. Structural learning only — never copy art/titles/photos."""
    real = [r for r in listings if r.get("title")]
    L = ["## 🔬 Reverse-engineer the top competitors", "",
         "_Their playbook, decoded — so you can out-execute it. **Structural "
         "learning only; never copy** their artwork, titles, or photos._", ""]
    if not real:
        return L + ["_No competitor listings returned for this keyword._", ""]
    prices = [_f(r.get("price_usd") or r.get("price")) for r in real]
    prices = [p for p in prices if p > 0]
    niche_avg = sum(prices) / len(prices) if prices else 0
    ranked = sorted(real, key=lambda r: _f(r.get("total_sold")), reverse=True)[:limit]
    gaps = set()
    for i, r in enumerate(ranked, 1):
        title = _clean(r.get("title"))
        price = _f(r.get("price_usd") or r.get("price"))
        tags = [_clean(t) for t in (r.get("tags") or []) if _clean(t)][:8]
        tl = title.lower()
        pos = ("premium" if niche_avg and price > niche_avg * 1.2 else
               "budget" if niche_avg and price < niche_avg * 0.8 else "mid-market")
        pers = [w for w in ("personalized", "custom", "name", "monogram",
                            "embroidered", "bundle", "set", "gift", "matching")
                if w in tl]
        sold = _f(r.get("total_sold"))
        strength = ("STRONG" if sold > 500 else "moderate" if sold > 100
                    else "new / small")
        weak = []
        if not any(w in tl for w in ("name", "custom", "personal", "monogram")):
            weak.append("no personalization in the title"); gaps.add("personalization")
        if len(tl.split()) < 6:
            weak.append("broad / thin title (weak long-tail SEO)"); gaps.add("seo")
        if not any(w in tl for w in ("bundle", "set", "matching", "gift box")):
            weak.append("no bundle / set / gift-box offer"); gaps.add("bundle")
        if not weak:
            weak.append("solid listing — beat it on a bolder first image")
            gaps.add("first image")
        L += [f"### #{i} — {title[:60]} · {strength}", "",
              f"- **Keyword / tag strategy:** {', '.join(tags) or 'not shown'}",
              f"- **Price positioning:** {_money(price)} ({pos}"
              + (f" vs niche avg {_money(niche_avg)}" if niche_avg else "") + ")",
              f"- **Offer angle:** "
              + (', '.join(pers) if pers else "generic — no personalization/bundle in the title"),
              f"- **Strength:** {_int(r.get('total_sold'))} sold · "
              f"{_pct(r.get('conversion_rate'))} conv · {_int(r.get('favorites'))} favs",
              f"- **Weakness to beat:** {'; '.join(weak)}", ""]
    plays = {
        "personalization": "offer real personalization (name / date / monogram) most of them lack",
        "seo": "front-load a specific long-tail — their titles are broad",
        "bundle": "add a set / gift-box / matching option they don't offer",
        "first image": "win the thumbnail — bolder, clearer, gift-in-use hero shot",
    }
    L += ["### ✅ Our better angle (built from their gaps)", ""]
    L += [f"- {plays[g]}" for g in ("personalization", "seo", "bundle", "first image")
          if g in gaps]
    if mode == "embroidery":
        L.append("- A real stitched / chenille version = a premium they can't match cheaply.")
    L += ["", "_What NOT to copy: their artwork, exact title wording, photos, or "
          "branding. Learn the structure — make your own original._", ""]
    return L


_SLUG_GENERIC = {"personalized", "personalised", "custom", "customized", "customised",
                 "gift", "gifts", "the", "for", "your", "my", "and", "with", "new",
                 "best", "a", "of", "to", "in", "on", "handmade", "unique"}


def spy_target(raw):
    """Parse a Spy input — a keyword OR an Etsy listing URL — into
    (keyword, listing_id). For a plain keyword listing_id is None. For a listing
    URL we read the title slug and BROADEN it (drop generic modifiers, use fewer
    words) to a keyword the index actually has market data for — a full 5-word
    listing title usually returns nothing, but its 2–3 word product core is rich.
    A listing URL with no usable title slug returns ("", listing_id)."""
    import re
    raw = (raw or "").strip()
    m = re.search(r"etsy\.com\S*?/listing/(\d+)(?:/([a-z0-9\-]+))?", raw, re.I)
    if not m:
        kw = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()[:80]
        return kw, None
    lid, slug = m.group(1), (m.group(2) or "")
    words = [w for w in slug.split("-") if w and w not in _SLUG_GENERIC]
    if not words:
        return "", lid
    for n in (5, 4, 3, 2):                     # broaden until the index has data
        cand = " ".join(words[:n]).strip()
        if not cand:
            continue
        try:
            rk = mcp.research_keyword(cand) or {}
            tl = rk.get("top_listings") or (rk.get("data", {}) or {}).get("top_listings") or []
            if tl or (mcp.analyze_competition(cand, "keyword") or {}).get("listings"):
                return cand, lid
        except (SystemExit, Exception):        # noqa: BLE001 - fall back to a plain guess
            break
    return " ".join(words[:3]), lid


def spy(kw, mode=None):
    """Competitor intelligence + REVERSE ENGINE for a keyword — MODE-AWARE. Who
    wins, each top competitor's decoded playbook, who just launched, whether we can
    make it in this mode, and the gaps. Learning only: study structure, never copy."""
    kw = kw.strip()
    m = (mode or "").lower()
    if m not in ("pod", "embroidery", "both"):
        m = "embroidery" if matches_mode(kw.lower(), "embroidery") else "pod"
    label = {"pod": "Print on Demand", "embroidery": "Embroidery",
             "both": "POD vs Embroidery"}[m]
    L = [f"# 🕵️ Spy + Reverse Engine — {kw} · {label}", "",
         "_Competitor intelligence + a decoded **reverse-engineer** of the top "
         "sellers' playbook. **Learning only** — study structure + the gaps, never "
         "copy artwork, titles, descriptions, or photos._", ""]

    try:
        comp = mcp.call("ytrends_analyze_competition", seed=kw, seed_type="keyword")
        comp = comp.get("data", comp) if isinstance(comp, dict) else {}
    except Exception:  # noqa: BLE001
        comp = {}
    shops = comp.get("top_shops") or []
    L += ["## Who dominates this niche (top shops)", ""]
    if shops:
        L += ["| Shop | Listings | Revenue | Avg price | Country |",
              "|---|---|---|---|---|"]
        for s in shops[:8]:
            L.append(f"| {s.get('shop_id','?')} | {_int(s.get('listings'))} "
                     f"| {_money(s.get('total_revenue_usd'))} "
                     f"| {_money(s.get('avg_price_usd'))} "
                     f"| {_clean(s.get('shop_country'))} |")
    else:
        L.append("_No shop-level data returned._")
    sat = (comp.get("saturation") or "").lower()
    read = ("crowded — you need strong differentiation" if sat == "high"
            else "open — room for a well-optimized new listing" if sat == "low"
            else "mixed")
    L += ["", f"- Saturation: **{sat or 'unknown'}** · new sellers entering: "
          f"**{_pct(comp.get('new_entrant_rate'))}** · {read}", ""]

    # Mode-aware: can we actually make + supply this in the chosen mode?
    L += _spy_feasibility(kw, m)

    try:
        rk = mcp.research_keyword(kw)
        listings = (rk.get("top_listings") if isinstance(rk, dict) else None) or []
        timeline = (rk.get("timeline") if isinstance(rk, dict) else None) or []
    except Exception:  # noqa: BLE001
        listings, timeline = [], []
    _ds = demand_spark(timeline)
    if _ds:
        L += ["", _ds, ""]
    L += ["## What's winning right now (do NOT copy)", ""]
    if listings:
        L += ["| Listing | Price | Sold 24h | Total sold | Conv | Favs | Sample tags |",
              "|---|---|---|---|---|---|---|"]
        for r in listings[:8]:
            tags = ", ".join(_clean(t) for t in (r.get("tags") or [])[:4])
            L.append(f"| {_clean(r.get('title'))[:46]} | {_money(r.get('price'))} "
                     f"| {_int(r.get('sold_24h'))} | {_int(r.get('total_sold'))} "
                     f"| {_pct(r.get('conversion_rate'))} | {_int(r.get('favorites'))} "
                     f"| {tags} |")
    else:
        L.append("_No winning listings returned for this keyword._")

    if m in ("embroidery", "both") and listings:
        emb_ok = sum(1 for r in listings[:8]
                     if matches_mode((str(r.get("title") or "") + " "
                                      + " ".join(str(t) for t in (r.get("tags") or []))
                                      ).lower(), "embroidery"))
        L += ["", f"_Embroidery read: **{emb_ok} of {min(len(listings), 8)}** top "
              "listings look embroidery/monogram/stitch-friendly — the rest are POD "
              "art you should NOT reproduce as embroidery._"]

    from collections import Counter
    freq = Counter()
    for r in listings:
        for t in (r.get("tags") or []):
            c = _clean(t).lower()
            if c:
                freq[c] += 1
    shared = [(t, c) for t, c in freq.most_common(12) if c >= 2]
    if shared:
        L += ["", "## Tags the winners share (reference — write your own)", ""]
        L += [f"- **{t}** — used by {c} of the top listings" for t, c in shared]

    # Competitor Reverse Engine — decode each top competitor's playbook.
    L += [""] + _spy_reverse(listings, m)

    L += ["", "## Who just launched (new entrants — what's fresh)", ""]
    try:
        _seed = f"embroidered {kw}" if m == "embroidery" else kw
        ne = mcp.call("ytrends_browse_new_listings", search=_seed, limit=12,
                      listing_age_days_max=45, response_format="concise")
        ne = (ne.get("data", {}) or {}).get("listings", []) if isinstance(ne, dict) else []
    except Exception:  # noqa: BLE001
        ne = []
    if m == "embroidery":   # keep only embroidery-compatible new entrants
        ne = [r for r in ne
              if matches_mode((str(r.get("title") or "") + " "
                               + str(r.get("primary_tag") or "")).lower(), "embroidery")]
    ne = ne[:8]
    if ne:
        L += ["| New listing | Price | Age | Sold 24h |", "|---|---|---|---|"]
        for r in ne[:8]:
            L.append(f"| {_clean(r.get('title'))[:52]} | {_money(r.get('price'))} "
                     f"| {_int(r.get('listing_age_days'))}d | {_int(r.get('sold_24h'))} |")
    else:
        L.append("_No recent new listings for this keyword._")

    L += ["", "## Gaps to exploit (learn, then out-execute)", ""]
    gaps = []
    if sat == "low":
        gaps.append("Low saturation — a well-optimized listing can rank.")
    low_titles = " ".join(str(r.get("title") or "").lower() for r in listings)
    if not any(w in low_titles for w in ("name", "custom", "personal", "monogram")):
        gaps.append("Few winners personalize — offer name / date / monogram they lack.")
    gaps.append("Beat their first image — bolder, clearer, gift-in-use hero shot.")
    gaps.append("Front-load a specific long-tail; most of their titles are broad.")
    gaps.append("Consider a bundle / set the top shops don't offer.")
    if m == "embroidery":
        gaps.append("Most rivals here are POD prints — a real stitched/chenille "
                    "version is a premium angle they can't match cheaply.")
    elif m == "pod":
        gaps.append("Ship faster + cheaper than embroidery rivals with a clean POD "
                    "print at a sharper price.")
    else:
        gaps.append("Test BOTH: a cheap POD version for volume and a premium "
                    "embroidery version for margin — see which the niche rewards.")
    L += ["- " + g for g in gaps]
    L += ["", "_Original designs + your own copy only. This is to understand the "
          "market structure and find gaps — not to copy any seller's work._"]
    return "\n".join(L)


def draft_listing(kw):
    """A first-draft listing pack (title, 13 tags, price, description) built from
    live keyword data. DRAFT ONLY — the team reviews + personalizes before use."""
    kw = kw.strip()
    try:
        rk = mcp.research_keyword(kw)
        stats = rk.get("stats", {}) if isinstance(rk, dict) else {}
        related = (rk.get("related_keywords") if isinstance(rk, dict) else None) or []
    except (SystemExit, Exception):  # noqa: BLE001 - degrade to a draft skeleton offline
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
    mid_v = stats.get("median_price") or stats.get("avg_price")
    mid = _money(mid_v)

    # Real supplier cost + margin, same model the reports use.
    cost_line, margin_line = "", ""
    try:
        from src.idea_report import cluster_of, load_costs, margin_at
        mode = "embroidery" if matches_mode(kw.lower(), "embroidery") else "pod"
        cluster = cluster_of(kw.lower())
        costs = load_costs(mode=mode)
        c = costs.get(cluster) if cluster else None
        if c:
            base, ship, supplier = c[0], c[1], c[2]
            cost_line = (f"- **Supplier cost: {_money(base + ship)}** "
                         f"({supplier}, {mode}) for the *{cluster}* product line.")
            at_mid = margin_at(mid_v, cluster, costs) if mid_v else None
            # lowest price that clears ~$8 profit after Etsy fees
            rec = None
            p = 5.0
            while p < 200:
                if (margin_at(p, cluster, costs) or -1) >= 8:
                    rec = p
                    break
                p += 1
            bits = []
            if at_mid is not None:
                warn = " ⚠️ too thin — price higher" if at_mid < 5 else ""
                bits.append(f"at the market midpoint {mid} you'd make "
                            f"**{_money(at_mid)}/sale**{warn}")
            if rec:
                bits.append(f"price **≥ {_money(rec)}** to clear ~$8 profit/sale")
            margin_line = "- " + "; ".join(bits) + "." if bits else ""
    except Exception:  # noqa: BLE001
        pass

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
    L += ["", "## Cost, price & margin",
          f"- Market sells around **{lo}–{hi}** (midpoint {mid})."]
    if cost_line:
        L.append(cost_line)
    if margin_line:
        L.append(margin_line)
    if not cost_line:
        L.append("- _(No supplier cost on file for this product line — check "
                 "supplier_costs.csv.)_")
    L += ["", "## Description skeleton", "", "```",
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


def _mode_for(kw, mode=None):
    """Resolve pod/embroidery for a keyword (explicit mode wins)."""
    if mode in ("pod", "embroidery"):
        return mode
    return "embroidery" if matches_mode((kw or "").lower(), "embroidery") else "pod"


def _tags_for(kw, limit=13):
    """Best-effort clean tag list for a keyword, reusing the live related-keyword
    data (same source draft_listing draws its tags from). Never raises."""
    tags, seen = [], set()
    try:
        rk = mcp.research_keyword(kw) or {}
        related = (rk.get("related_keywords") if isinstance(rk, dict) else None) or []
    except (SystemExit, Exception):  # noqa: BLE001 - stay useful if the MCP is down
        related = []
    for cand in [kw] + [_g(r, "tag", "keyword", "title") for r in related]:
        c = (cand or "").strip().lower()
        if c and c not in seen and 3 <= len(c) <= 20:
            try:
                r2, _ = tm_check(c)
            except Exception:  # noqa: BLE001
                r2 = "OK"
            if r2 != "HIGH":
                seen.add(c)
                tags.append(c)
        if len(tags) >= limit:
            break
    return tags


def _price_cost_for(kw, mode):
    """(price, product_cost, shipping_cost, conversion_rate) for a keyword from
    live data + the supplier cost model. Any piece may be None (honest-null)."""
    price = conv = None
    try:
        stats = (mcp.research_keyword(kw) or {}).get("stats", {}) or {}
        price = _f(stats.get("median_price") or stats.get("avg_price")) or None
        conv = _f(stats.get("avg_conversion_rate")) or None
    except (SystemExit, Exception):  # noqa: BLE001 - degrade to honest-null
        pass
    base = ship = None
    try:
        from src.idea_report import cluster_of, load_costs
        cluster = cluster_of(kw.lower())
        costs = load_costs(mode=mode)
        c = costs.get(cluster) if cluster else None
        if c:
            base, ship = c[0], c[1]
    except (SystemExit, Exception):  # noqa: BLE001
        pass
    return price, base, ship, conv


def photo_prompts(kw, mode=None):
    """The full photo-prompt set for a listing - every image slot, each with a
    ready-to-paste AI prompt. DRAFT: the honesty rule (real product photos, AI for
    concept/graphics only) is printed on every product slot."""
    kw = (kw or "").strip()
    mode = _mode_for(kw, mode)
    product = "Embroidered Sweatshirt" if mode == "embroidery" else "Printed T-Shirt"
    from src import photo_brief
    slots = photo_brief.build(kw, product=product, mode=mode, pers=True)
    label = MODE_LABEL.get(mode, mode)
    L = [f"# Photo prompt set — {kw}", "",
         f"_{len(slots)} listing images for a **{product}** ({label}). "
         "Etsy allows up to 10 photos; image #1 is the thumbnail and does most of "
         "the converting._", "",
         "> **Honesty rule (baked in):** use AI for concept, mockups, graphics and "
         "styled scenes only. Any slot marked **REAL PHOTO** must show your actual "
         "product / sew-out — an AI render of your real item is a misleading "
         "product claim on Etsy.", ""]
    for s in slots:
        kind = "📸 REAL PHOTO" if s["real_photo"] else "🎨 AI ok"
        L += [f"## {s['n']}. {s['slot']}  ·  {kind}",
              f"_{s['purpose']}_", "",
              "```", s["prompt"], "```", ""]
    L += ["---",
          "**Next:** shoot the REAL-PHOTO slots first (hero + macro stitch decide "
          "the sale), generate the graphic slots, then load image #1 as your "
          "thumbnail."]
    return "\n".join(L)


def ads_plan(kw, mode=None):
    """An Etsy-accurate MANUAL Etsy Ads starter plan for a keyword: budget to
    start, breakeven ACOS/ROAS from the real fee model, a max average CPC, the
    tag coverage Etsy Ads matches on, and 2-week read/kill rules. No account
    access — it tells the human exactly what to set inside Etsy's Ads dashboard."""
    kw = (kw or "").strip()
    mode = _mode_for(kw, mode)
    tags = _tags_for(kw)
    price, base, ship, conv = _price_cost_for(kw, mode)
    from src import ads_plan as ap
    plan = ap.build(kw, tags=tags, price=price, product_cost=base,
                    shipping_cost=ship or 0.0, mode=mode, conversion_rate=conv)
    econ = plan["economics"]
    label = MODE_LABEL.get(mode, mode)

    L = [f"# Etsy Ads starter plan — {kw}", "",
         f"_Manual {label} plan. Etsy Ads is **one campaign, one daily budget** — "
         "there is no per-keyword bidding; Etsy matches shoppers to your listing "
         "by its **tags + title**. This tells you what to set; you set it inside "
         "Etsy._", ""]

    L += ["## 1. Budget to start"]
    L += [f"- Start **one** campaign at **${plan['start_daily']:.0f}/day** "
          f"(Etsy minimum is ${plan['min_daily']:.0f}/day).",
          f"- Advertise only your **best 3–5 listings** for this niche.",
          f"- Let it run **{plan['test_days']} days** before judging anything.", ""]

    L += ["## 2. The money math (from your real Etsy fees)"]
    if econ is None:
        L += ["- _No price/cost on file, so breakeven is a formula, not a number:_",
              "  `breakeven ACOS % = net profit per sale ÷ sale price × 100`",
              "- Fill in your price and supplier cost to get the real figure + a "
              "max average CPC.", ""]
    elif econ.get("unprofitable"):
        L += [f"- ⚠️ At **{_money(econ['price'])}** this sale **loses "
              f"{_money(econ['net_profit'])} before any ad spend** — do not "
              "advertise it. Raise the price or lower the cost first.", ""]
    else:
        L += [f"- Price **{_money(econ['price'])}** → net profit "
              f"**{_money(econ['net_profit'])}/sale** ({econ['margin_pct']}% margin).",
              f"- **Breakeven ACOS ≈ {econ['breakeven_acos_pct']}%** "
              f"(breakeven ROAS ≈ {econ['breakeven_roas']}×) — spend more than that "
              "on ads per sale and you lose money.",
              f"- **Target ACOS ≈ {econ['target_acos_pct']}%** "
              f"(ROAS ≈ {econ.get('target_roas')}×) — keeps ~40% of the margin as "
              "profit."]
        if plan["max_avg_cpc"] is not None:
            crnote = (" (assumed 2% — replace once you know your real rate)"
                      if plan["assumed_cr"] else "")
            L += [f"- At ~{plan['clicks_per_sale']} clicks per sale{crnote}, keep "
                  f"your **average CPC around ${plan['max_avg_cpc']:.2f} or less**. "
                  "Etsy sets the actual CPC — you can't bid it, but this is the "
                  "line where the campaign stays profitable."]
        L += [""]

    L += ["## 3. Tag coverage (this IS your ad targeting)"]
    if tags:
        L += ["Etsy Ads can only show you for searches your **tags/title** cover. "
              "Current tags:", "",
              ", ".join(f"`{t}`" for t in plan["priority_tags"]), ""]
    else:
        L += ["_No live tags found — build the 13 tags first (Listing draft tool), "
              "then re-run this._", ""]
    if plan["tag_gaps"]:
        L += ["**Add tags to cover these buyer-intent gaps** (each missing one is a "
              "shopper Etsy can't match you to): "
              + ", ".join(f"**{g}**" for g in plan["tag_gaps"]) + ".", ""]
    else:
        L += ["✅ Your tags already cover personalization, gift, buyer, occasion and "
              "product type.", ""]

    L += ["## 4. Read & kill (after 2 weeks)"]
    L += [f"- {r}" for r in plan["read_kill_rules"]]
    L += ["", "## Setup checklist"]
    L += [f"- {c}" for c in plan["checklist"]]
    L += ["", "## Notes"]
    L += [f"- {n}" for n in plan["notes"]]
    L += ["", "_Plan only — nothing here connects to or changes your Etsy account._"]
    return "\n".join(L)


# ---- Winner Finder (#2) + Competitor Edge Finder (#4) ------------------------
def _uq(kw):
    from urllib.parse import quote_plus
    return quote_plus((kw or "").strip())


def _barcell(v, width=10, full="█", empty="░"):
    """A 0-100 value as a 10-char unicode bar, for at-a-glance table cells."""
    if not isinstance(v, (int, float)):
        return "—"
    f = max(0, min(width, int(round(v / 100.0 * width))))
    return full * f + empty * (width - f)


def _proven_orders(kw):
    """OUR OWN proven order count for a keyword from the learning loop (0 when the
    shop has no sales history yet). Guarded: never breaks a page if learning data
    is absent or unreadable."""
    try:
        from src import learning
        if not learning.has_history():
            return 0
        return int(learning.winner_orders(kw) or 0)
    except (SystemExit, Exception):  # noqa: BLE001
        return 0


def winners(mode=None):
    """Winner Finder — rank the latest extension import STRICTLY by the high-demand
    + low-competition sweet spot (the opportunity gap), so the fastest 'what should
    I make this week' answer is the top row. Fast lane: pure local scoring, no live
    MCP pull, no waiting."""
    from src import shortlister_integration as si
    from src import opportunity_score as osc
    res = si.score_latest(source=None, mode=mode)
    if not res.get("ok"):
        return ("# Winner Finder\n\n> **No import yet.** On a YTrends or Etsy search "
                "page, use the **YTrends Exporter** toolbar and click **Send to "
                "agent**, then reload this page.")
    ranked = []
    proven_any = False
    for s in res["results"]:
        proven = _proven_orders(s.get("keyword", ""))
        gap = osc.opportunity_gap(s.get("sub_scores", {}), proven)
        if gap is not None:
            if proven > 0:
                proven_any = True
            ranked.append((gap, proven, s))
    ranked.sort(key=lambda x: -x[0])
    label = MODE_LABEL.get(mode, mode)
    total = res.get("rows_in_import")
    scope = f"{len(ranked)} scored" + (f" of {total} captured" if total else "")
    L = [f"# Winner Finder — {res.get('view', 'latest import')}", "",
         f"_Ranked strictly by the **high-demand × low-competition** sweet spot "
         f"({scope}, {label}). Winner = geometric mean of demand & low-saturation, so "
         "a niche must be strong on BOTH to rank. Demand bar longer = better; "
         "Saturation bar shorter = better._", ""]
    if proven_any:
        L += ["_✔ = you've sold this before — the learning loop lifts its winner "
              "score so proven niches rise automatically._", ""]
    if "amazon" in str(res.get("view", "")).lower():
        L += ["> 🅰️ **Amazon reference import.** These keywords + demand come from "
              "Amazon (Xray/Cerebro), not Etsy — treat them as a corroborating "
              "reference and re-check the winners with a real Etsy/YTrends export "
              "before building. Amazon demand ≠ Etsy demand.", ""]
    _gt = "&mode=" + mode if mode else ""
    L += [f"_Cross-check the top picks on [Google Trends](/score-import?gt=1{_gt}). "
          "Verdicts advisory — trademark + human review still required._", ""]
    if not ranked:
        L += ["_Nothing in this import had BOTH a demand and a competition signal, so "
              "no winner can be called honestly. Capture a YTrends/Etsy view that "
              "shows views + competition, or [enrich from the MCP]"
              "(/score-import?enrich=1) to fill the blanks._"]
        return "\n".join(L)
    L += ["| # | Keyword | Winner | Demand | Saturation | Verdict | Next move |",
          "|---|---|---|---|---|---|---|"]
    for i, (gap, proven, s) in enumerate(ranked[:20], 1):
        sub = s.get("sub_scores", {})
        demand = sub.get("market_potential")
        comp = sub.get("competition_health")
        sat = (100 - comp) if isinstance(comp, (int, float)) else None
        kw = _clean(s["keyword"]) + (" +" if s.get("enriched") else "")
        if proven > 0:
            kw += f" ✔{proven}"
        nxt = _SHORTLIST_NEXT.get(s["verdict"], "Review")
        L.append(f"| {i} | {kw} | **{gap}** | `{_barcell(demand)}` "
                 f"| `{_barcell(sat)}` | {s['verdict']} | {nxt} |")
    top_kw = ranked[0][2]["keyword"]
    L += ["", f"## ◎ Sharpest pick: **{_clean(top_kw)}** — winner {ranked[0][0]}",
          f"**▶ [Build the full Launch Kit](/launch-kit?q={_uq(top_kw)})** — verdict, "
          "edge, listing, photos & ads on one page.", "",
          f"Or one tool at a time: [Listing draft](/draft-listing?q={_uq(top_kw)}) · "
          f"[Photo prompts](/photo-brief?q={_uq(top_kw)}) · "
          f"[Ads plan](/ads-plan?q={_uq(top_kw)}) · "
          f"[Beat competitors](/edge?q={_uq(top_kw)})"]
    return "\n".join(L)


_MKT_ICON = {"GO": "\U0001F7E2", "CONDITIONAL": "\U0001F535",
             "WATCH": "\U0001F7E1", "SKIP": "⛔"}
_ACTION_ICON = {"BUILD_NOW": "\U0001F680", "CONFIRM_FIRST": "\U0001F50D",
                "REVIEW": "\U0001F6A9", "WATCH": "\U0001F7E1", "SKIP": "⛔",
                "BLOCKED": "\U0001F6AB"}


def _inbox_do(r):
    """The 1-click link for a row, routed by its FINAL ACTION (not the score)."""
    q = _uq(r["keyword"])
    route = r.get("route")
    if route == "build":
        return f"[\U0001F680 Build](/launch-kit?q={q})"
    if route == "pattern":
        return f"[\U0001F52C Pattern Miner](/pattern-miner?q={q})"
    if route == "review":
        return f"[\U0001F6A9 Review](/should-sell?q={q})"
    if route == "analyze":
        return f"[\U0001F50D Confirm](/should-sell?q={q})"
    if route == "watch":
        return f"[\U0001F441 Check](/should-sell?q={q})"
    return "~~skip~~"


def _inbox_row(i, r):
    """One ranked table row (shared by the FOCUS table and the full list)."""
    kw = _clean(r["keyword"])
    a_icon = _ACTION_ICON.get(r["action"], "")
    action = f"{a_icon} {r['action'].replace('_', ' ').title()}"
    mkt = (f"{_MKT_ICON.get(r['verdict'], '')} {r['verdict']} "
           f"({r['score']})" if r["score"] is not None else
           f"{_MKT_ICON.get(r['verdict'], '')} {r['verdict']}")
    fit = r.get("fit_label") or "—"
    pr = r.get("proof")
    tier = r.get("proof_tier", 9)
    if pr and tier == 0:
        proof_cell = f"\U0001F3C6 {pr['evidence']}"
    elif pr and tier == 1:
        proof_cell = f"\U0001F4AA {pr['evidence']}"   # strong seller / fuzzy-proven
    elif pr and tier == 2:
        proof_cell = f"\U0001F7E2 {pr['evidence']}"
    else:
        proof_cell = "—"
    comp = int(r["comp"]) if r["comp"] is not None else "—"
    conv = f"{r['conv']*100:.1f}%" if r["conv"] is not None else "—"
    mom = int(r["momentum"]) if r["momentum"] is not None else "—"
    return (f"| {i} | {kw} | {proof_cell} | {fit} | {action} | {mkt} | {comp} "
            f"| {conv} | {mom} | {_inbox_do(r)} |")


_INBOX_HDR = ["| # | Keyword | Etsy proof | Product-fit | Final action | Market | Comp. | Conv. | Mom. | Do |",
              "|---|---|---|---|---|---|---|---|---|---|"]


def inbox(mode=None, q="", show_archived=False):
    """Opportunity Inbox — your real keyword data through the LAYERED ranking engine.

    Each keyword passes a risk / product-fit GATE, then the composite Market-Signal
    score, and ends on a FINAL ACTION (Build now / Confirm first / Review / Watch /
    Skip / Blocked). The market score is real market data + our chosen weights (an
    explainable model, not the whole decision) — the gate keeps broad seeds, themes
    without a product, shop names, and policy/trademark terms out of 'Build'.
    Pass q to FOCUS: the rows related to that keyword rank first."""
    from src import opportunity_inbox as oi
    q = (q or "").strip()
    data = oi.build_inbox(mode, q=q or None, show_archived=show_archived)
    rows = data["rows"]
    c = data["counts"]
    label = MODE_LABEL.get(mode, mode) if mode else "all modes"
    L = [f"# \U0001F4E5 Opportunity Inbox — ranked worklist ({label})", ""]
    if not rows:
        L += ["> **No keyword data yet.** Feed keywords from the YTrends MCP "
              "(auto) or drop a YTrends keyword CSV on the home page, then reload."]
        return "\n".join(L)
    proof_line = ""
    if data.get("has_proof"):
        proof_line = (f"\U0001F3C6 **{c.get('proven', 0)}** proven · "
                      f"\U0001F7E2 **{c.get('selling', 0)}** selling (real Etsy sales) · ")
    L += [f"_**{c['total']}** keywords ranked — {proof_line}"
          f"\U0001F680 **{c['build']}** build now · "
          f"\U0001F50D **{c['confirm']}** confirm first · "
          f"\U0001F6A9 **{c['review']}** review · "
          f"\U0001F7E1 **{c['watch']}** watch · "
          f"⛔ **{c['skip']}** skip · \U0001F6AB **{c['blocked']}** blocked. "
          "Sorted by **Etsy proof → final action → market signal** (the layered "
          "engine). Real sales rank above a good-looking market score._", ""]
    # lifecycle + enrichment queue lines (V32): stale rows out, leads visible
    if c.get("archived"):
        L += [f"_\U0001F5C4 **{c['archived']}** stale WATCH rows archived (no "
              "proof + no data refresh in the expiry window) — they stay "
              "searchable in Focus and via `?show=all`._", ""]
    if c.get("needs_enrichment"):
        L += [f"_\U0001F50C **{c['needs_enrichment']}** capture-lane leads still "
              "have NO market data — use the **Enrich leads via MCP** button "
              "above to fill them (honest-nulls until then)._", ""]
    # honest provenance: exactly which data sources fed THIS ranking
    src = data.get("sources") or {}
    if src:
        lane_bit = ""
        if src.get("pinterest_leads") or src.get("supplier_leads"):
            lane_bit = (f" · \U0001F4CC **{src.get('pinterest_leads', 0)}** Pinterest "
                        f"leads + \U0001F3ED **{src.get('supplier_leads', 0)}** supplier "
                        f"leads ({src.get('lane_new', 0)} entered the rank as new "
                        "candidates)")
        L += [f"_\U0001F4E1 Data in this rank: **{src.get('master_rows', 0)}** master "
              f"keyword rows (YTrends MCP + extension imports + "
              f"**{src.get('keyword_lab', 0)}** from Keyword Lab) · "
              f"**{src.get('proof_listings', 0)}** real-sales proof listings "
              f"(Alura/EverBee exports + your Etsy captures){lane_bit}._", ""]
    # ------- FOCUS: the typed keyword drives the view (keyword-aware inbox) ---
    if data.get("focus_q"):
        fr = data.get("focus") or []
        fq = _clean(data["focus_q"])
        uq = _uq(data["focus_q"])
        L += [f"## \U0001F3AF Focus: “{fq}” — {len(fr)} related keyword(s) in the rank", ""]
        # inline pattern snapshot (review consensus: the research loop should
        # live on ONE page - rank, pattern and expand without stage-hopping)
        try:
            from src import pattern_miner as _pm
            _pat = _pm.mine(data["focus_q"])
            _mt, _sc = _pat.get("matched") or 0, _pat.get("scanned") or 0
            if _mt:
                _tw = ", ".join(f"{w} {p}%" for w, p in
                                (_pat.get("top_words") or [])[:4])
                _gap = (_pat.get("gaps") or [""])[0]
                L += [f"_\U0001F52C Pattern snapshot: matched **{_mt}** of "
                      f"{_sc} captured listings · top title words: {_tw}"
                      + (f" · gap: {_gap}" if _gap else "") + "_", ""]
        except Exception:  # noqa: BLE001 - snapshot must never break the inbox
            pass
        if fr:
            L += list(_INBOX_HDR)
            for i, r in enumerate(fr, 1):
                L.append(_inbox_row(i, r))
            L += ["", f"**Next step for this niche:** "
                  f"[\U0001F52C Mine the winning pattern](/pattern-miner?q={uq}) · "
                  f"[\U0001F4A1 Generate new keywords](/keyword-lab?q={uq}) · "
                  f"[\U0001F680 Build the Launch Kit](/launch-kit?q={uq})", ""]
        else:
            L += [f"> No ranked keyword matches “{fq}” yet. "
                  f"**[\U0001F52C Run the Pattern Miner](/pattern-miner?q={uq})** on "
                  "your captures, then **[\U0001F4A1 Keyword Lab]"
                  f"(/keyword-lab?q={uq})** → “Add to Inbox” to bring this niche "
                  "into the rank with real long-tail candidates.", ""]
        L += ["---", "", "### Full ranking (all keywords)", ""]
    if not data.get("has_proof"):
        L += ["> \U0001F4A1 _No Etsy Proof export loaded yet. Drop an **Alura / "
              "EverBee product-research CSV** (real sold + revenue + listing age) to "
              "switch on the proof tier that ranks *already-selling* niches on top._",
              ""]
    L += list(_INBOX_HDR)
    for i, r in enumerate(rows, 1):
        L.append(_inbox_row(i, r))
    top = next((r for r in rows if r["action"] in ("BUILD_NOW", "CONFIRM_FIRST")),
               None)
    if top:
        act_word = top["action"].replace("_", " ").title()
        mkt_txt = (f"{top['verdict']} ({top['score']})" if top["score"] is not None
                   else top["verdict"])
        L += ["", f"## ◎ Start here: **{_clean(top['keyword'])}** — "
              f"{_ACTION_ICON.get(top['action'], '')} {act_word}",
              f"_{top['action_reason']}. Market signal {mkt_txt} · "
              f"{top['evidence']}._", ""]
        if top["route"] == "build":
            L.append(f"**▶ [Build the full Launch Kit](/launch-kit?q="
                     f"{_uq(top['keyword'])})** — verdict, competitor edge, listing, "
                     "all image prompts & ads on one page.")
        elif top["route"] == "pattern":
            L.append(f"**▶ [Run the Pattern Miner](/pattern-miner?q={_uq(top['keyword'])})** "
                     "first — it's a broad/theme term, so learn what the winners share "
                     "and pick the angle before building.")
        else:
            L.append(f"**▶ [Confirm it first](/should-sell?q={_uq(top['keyword'])})** "
                     "before committing to a build.")
    # "Next 20 to investigate": the most promising WATCH rows (momentum x
    # conversion sub-rank) so a 1,000-row honest WATCH pool stays actionable.
    next20 = [r for r in rows if r["action"] == "WATCH"][:20]
    if next20:
        L += ["", "## \U0001F50E Next 20 to investigate (top WATCH by "
              "momentum × conversion)", ""]
        line = " · ".join(
            f"[{_clean(r['keyword'])}](/should-sell?q={_uq(r['keyword'])})"
            for r in next20)
        L += [line, ""]
    L += ["", "_**Layered ranking:** risk / product-fit gate → Etsy proof → market "
          "signal (demand · competition · conversion · momentum, an explainable "
          "model of real market data + our chosen weights) → final action. "
          "Conversion is one of the strongest buyer-quality signals after query "
          "match, not the only one. **Long-tail rule:** short-tail keywords "
          "(≤ 2 words) never show Build now — they're saturated, price-war "
          "territory; expand to a 3–5 word buyer-intent angle first (only real "
          "Etsy sales proof overrides this). Trademark / policy / broad-seed "
          "terms are gated before scoring; human review still required._"]
    return "\n".join(L)


def _bar_pct(p):
    """0-100 -> a 10-char unicode bar for at-a-glance rates."""
    if not isinstance(p, (int, float)):
        return "—"
    f = max(0, min(10, int(round(p / 10.0))))
    return "█" * f + "░" * (10 - f)


def pattern_miner(kw="", mode=None):
    """Pattern Miner — analyse the top Etsy listings for a keyword and show WHY the
    winners win: shared title words, leading (first-40) words, structure, price band,
    marketplace signals, exploitable gaps, and a keyword seed for the Keyword Lab."""
    from src import pattern_miner as pm
    r = pm.mine(kw or None)
    L = ["# \U0001F52C Pattern Miner — how the winners win", ""]
    if not r["have"]:
        if kw and r.get("scanned"):
            L += [f"> **No captured listings match “{_clean(kw)}”** "
                  f"(scanned {r['scanned']} listings from your recent captures). "
                  "Capture an **Etsy search for this keyword** with the extension "
                  "(Send to agent), then mine again — the miner only analyses "
                  "listings that actually belong to the niche you asked about."]
        else:
            L += ["> **No Etsy listings to mine yet.** Capture an Etsy search / "
                  "YTrends Spy / ytuong-Hot page with the extension, or drop the "
                  "CSV/JSON on the home page — then mine."]
        return "\n".join(L)
    st = r["structure"]
    sig = r["signals"]
    if r.get("query"):
        scope = (f"_Mined the **{r['matched']} listings matching "
                 f"“{_clean(r['query'])}”** (of {r['scanned']} captured, "
                 f"across **{r['n_shops']} shops**).")
    else:
        scope = (f"_Mined **{r['n']} listings** across **{r['n_shops']} shops** "
                 "from your recent captures (no keyword given — type one above to "
                 "focus a niche).")
    L += [scope + " This is the shared pattern of the listings currently ranking "
          "— copy what they all do, then beat them on the gaps below._", ""]
    # winning vocabulary
    L += ["## \U0001F3F7 Winning title words (share of listings using each)"]
    for w, pct in r["top_words"][:10]:
        L.append(f"- **{w}** · `{_bar_pct(pct)}` {pct}%")
    if r["leading"]:
        lead = ", ".join(f"{w} ({pct}%)" for w, pct in r["leading"][:6])
        L += ["", f"**Front-load these (first 40 chars):** {lead}"]
    if r["phrases"]:
        L += ["", "**Repeated phrases:** "
              + ", ".join(f"“{p}” ×{c}" for p, c in r["phrases"][:6])]
    # structure + price + signals
    L += ["", "## \U0001F9F1 Winning structure",
          f"- Personalization in title: **{st['personalization']}%**  ·  "
          f"names a product: **{st['has_product']}%**  ·  gift framing: **{st['gift']}%**",
          f"- Title length: **~{st['avg_words']} words / {st['avg_chars']} chars**"]
    if r["price"]:
        p = r["price"]
        L.append(f"- Price band: **${p['low']}–${p['high']}** (median **${p['median']}**, "
                 f"{p['note']})")
    L += ["", "## \U0001F4CA Marketplace signals",
          f"- Running ads: **{sig['ad']}%**  ·  star-sellers: **{sig['star']}%**  ·  "
          f"free shipping: **{sig['freeship']}%**  ·  top-shop hold: "
          f"**{r.get('shop_concentration', 0)}%**"]
    # the openings
    L += ["", "## \U0001F94A Exploitable gaps — your opening"]
    for g in r["gaps"]:
        L.append(f"- {g}")
    # next step -> keyword lab
    seed = ", ".join(r["seed_words"][:8])
    L += ["", "## \U0001F3AF Your better angle & next step",
          f"Match the winning pattern (personalized + {r['seed_words'][0] if r['seed_words'] else 'subject'} "
          f"+ product + gift), then win on the gap above. **Seed words:** {seed}.",
          "",
          f"**▶ [Generate new keywords in the Keyword Lab](/keyword-lab?q={_uq(r['keyword'] or kw)})** "
          "— turns this pattern into fresh buyer-specific keywords, re-ranked in the Inbox.",
          "",
          "_Real photo still required for embroidery (hero + macro stitch + measurement). "
          "Trademark-check every phrase before building._"]
    return "\n".join(L)


def keyword_lab(kw="", mode=None):
    """Keyword Lab — generate a NEW keyword batch FROM the Pattern Miner output, each
    linked back to the Inbox for re-ranking through the layered engine."""
    from src import keyword_lab as kl
    r = kl.generate(kw or None)
    pat = r["pattern"]
    L = ["# \U0001F4A1 Keyword Lab — new keywords from the winning pattern", ""]
    if not r["candidates"]:
        L += ["> **Run the Pattern Miner first.** Drop an Etsy Spy CSV for a keyword, "
              "then come back — the Lab expands the *proven* pattern into fresh "
              "buyer-specific keywords instead of guessing."]
        return "\n".join(L)
    L += [f"_Expanded from the **{_clean(pat.get('keyword') or kw)}** pattern "
          f"(subject **{r['subject']}**, product **{r['product']}**). These follow "
          "what already wins, aimed at nearby buyers — build the strongest after they "
          "re-rank._", "",
          "| # | New keyword | Angle | Re-rank |",
          "|---|---|---|---|"]
    for i, c in enumerate(r["candidates"], 1):
        L.append(f"| {i} | **{c['keyword']}** | {c['angle']} | "
                 f"[\U0001F501 Score it](/should-sell?q={_uq(c['keyword'])}) |")
    L += ["", "_Each keyword loops back through the layered engine (risk gate → market "
          "signal → final action). Score them, then build the winners. Trademark-check "
          "every phrase first._"]
    return "\n".join(L)


def _competitor_listings(kw, limit=15):
    """Best-effort competitor listing rows for a keyword. Prefers the latest
    extension import when it looks like a listings export (fast, rich HeyEtsy
    fields); falls back to the live hot-listings surface. Never raises."""
    try:
        from src import shortlister_integration as si
        from src import ytx_import as yi
        payload = si.load_latest_import()
        if payload:
            headers = [str(h).lower() for h in (payload.get("headers") or [])]
            rows = payload.get("rows") or []

            def col(*names):
                for i, h in enumerate(headers):
                    if any(n in h for n in names):
                        return i
                return None

            ti = col("title")
            if ti is not None and rows:
                pi, sdi = col("price"), col("sold")
                fi, vi = col("favorite", "fav"), col("view")
                tgi, di = col("tag"), col("discount")

                def cell(r, idx):
                    return r[idx] if (idx is not None and idx < len(r)) else None

                out = []
                for r in rows:
                    title = (cell(r, ti) or "").strip()
                    if not title:
                        continue
                    out.append({
                        "title": title,
                        "price": yi.parse_number(cell(r, pi)),
                        "total_sold": yi.parse_number(cell(r, sdi)),
                        "favorites": yi.parse_number(cell(r, fi)),
                        "views": yi.parse_number(cell(r, vi)),
                        "he_tags": cell(r, tgi),
                        "he_discount_pct": yi.parse_number(cell(r, di)),
                    })
                toks = [t for t in kw.lower().split() if len(t) > 2]
                rel = ([o for o in out if any(t in o["title"].lower() for t in toks)]
                       if toks else out)
                if len(rel) >= 4:
                    return rel[:40]
                if len(out) >= 4:
                    return out[:40]
    except (SystemExit, Exception):  # noqa: BLE001
        pass
    try:
        return mcp.hot_listings(keyword=kw, limit=limit) or []
    except (SystemExit, Exception):  # noqa: BLE001
        return []


def edge_finder(kw, mode=None):
    """Competitor Edge Finder (#4) — MEASURE how to beat the listings already
    ranking for a keyword, ranked by the biggest exploitable gap. Built from real
    competitor listings + the niche competition snapshot; signals with no data are
    listed honestly as manual checks, never given a fake score."""
    kw = (kw or "").strip()
    mode = _mode_for(kw, mode)
    from src import edge as edge_engine
    listings = _competitor_listings(kw)
    comp = {}
    try:
        comp = mcp.analyze_competition(kw) or {}
    except (SystemExit, Exception):  # noqa: BLE001
        comp = {}
    edges = edge_engine.measure_edges(listings, comp)
    measured = [e for e in edges if e["measured"]]
    manual = [e for e in edges if not e["measured"]]
    label = MODE_LABEL.get(mode, mode)

    src = (f"{len(listings)} competitor listing(s)"
           + (" + niche snapshot" if comp else "")) if listings else "niche snapshot only"
    L = [f"# Beat the competition — {kw}", "",
         f"_{label} · ranked by the biggest **measured** gap in the listings "
         f"already ranking. Source: {src}. Bar = size of the gap._", ""]
    if not listings:
        L += ["> No competitor listings were available (import an Etsy search with "
              "the extension for the richest read, or the live source was "
              "unreachable). Showing the manual-check gaps below.", ""]
    if measured:
        L += ["## Exploitable gaps — measured, biggest first", "",
              "| # | Gap | Size | What to do | Evidence |",
              "|---|---|---|---|---|"]
        for i, e in enumerate(measured, 1):
            L.append(f"| {i} | **{e['category']}** | `{_barcell(e['magnitude'])}` "
                     f"{e['magnitude']}% | {e['action']} | {e['evidence']} |")
        L += ["", f"**Sharpest edge:** {measured[0]['headline']} — "
              f"{measured[0]['action']}", ""]
    if manual:
        L += ["## Check by eye — not in the data, worth 2 minutes", ""]
        for e in manual:
            L += [f"- **{e['category']}** — {e['headline']}. {e['action']} "
                  f"_({e['evidence']})_"]
    L += ["", f"Build with it: [Listing draft](/draft-listing?q={_uq(kw)}) · "
          f"[Photo prompts](/photo-brief?q={_uq(kw)}) · "
          f"[Ads plan](/ads-plan?q={_uq(kw)})"]
    return "\n".join(L)


# ---- Launch Kit: the whole pipeline for one winner on a single page ----------
def _shift_headings(md_text, by=2):
    """Push every ATX heading down `by` levels so a reused view's headings nest
    UNDER the Launch Kit's own section headers (capped at level 6)."""
    out = []
    for ln in (md_text or "").split("\n"):
        i = 0
        while i < len(ln) and ln[i] == "#":
            i += 1
        if 0 < i <= 6 and i < len(ln) and ln[i] == " ":
            out.append("#" * min(6, i + by) + ln[i:])
        else:
            out.append(ln)
    return "\n".join(out)


def _kit_verdict(kw, mode):
    """Compact verdict + winner-score row for one keyword, enriched from the MCP
    when it's reachable. Returns markdown lines; never raises."""
    from src import shortlister_integration as si
    from src import opportunity_score as osc
    risk, reason = "OK", ""
    try:
        risk, reason = tm_check(kw.lower())
    except (SystemExit, Exception):  # noqa: BLE001
        pass
    d = {"tag": kw}
    try:
        si._enrich_row(d, mode)
    except (SystemExit, Exception):  # noqa: BLE001
        pass
    try:
        s = osc.score(d, keyword=kw, mode=mode)
    except (SystemExit, Exception):  # noqa: BLE001
        return [f"- **Trademark:** {risk}" + (f" — {reason}" if reason else "")]
    sub = s.get("sub_scores", {})
    proven = _proven_orders(kw)
    gap = osc.opportunity_gap(sub, proven)

    def cell(k):
        v = sub.get(k)
        return round(v) if isinstance(v, (int, float)) else "—"

    overall = (s["overall_score"] if s.get("core_complete")
               and s["overall_score"] is not None else "—")
    winner_cell = (f"**{gap if gap is not None else '—'}**"
                   + (f" ✔{proven}" if proven > 0 else ""))
    L = ["| Winner | Score | Verdict | Demand | Competition | Trademark |",
         "|---|---|---|---|---|---|",
         f"| {winner_cell} | {overall} | **{s['verdict']}** "
         f"| {cell('market_potential')} | {cell('competition_health')} "
         f"| {risk} |"]
    if proven > 0:
        L += ["", f"> ✔ **Proven for us:** {proven} order(s) logged in this niche — "
              "the learning loop has already lifted its winner score."]
    if risk == "HIGH":
        L += ["", f"> ⚠️ **Trademark HIGH on '{kw}'** — {reason}. Change the wording "
              "before building."]
    elif s["verdict"] == "SKIP":
        L += ["", "> ⚠️ This scored **SKIP** — the kit is below, but the data says "
              "sharpen the angle (narrower buyer / occasion) before you build."]
    return L


def launch_kit(kw, mode=None):
    """LAUNCH KIT — everything to launch one winner on a single page: verdict +
    winner score, the MEASURED way to beat competitors, the listing draft, the full
    photo-prompt set, the Etsy Ads plan, and a seller action checklist. Draft only —
    human review + real photos + trademark check before anything is published."""
    kw = (kw or "").strip()
    mode = _mode_for(kw, mode)
    label = MODE_LABEL.get(mode, mode)
    L = [f"# Launch Kit — {kw}", "",
         f"_Everything to launch this {label} winner on one page. **Draft only** — "
         "review it, add your real photos, and verify the trademark before "
         "publishing. Nothing here touches your Etsy account._", "",
         "**In this kit:** ① Verdict → ② Beat competitors → ③ Listing → ④ Photos → "
         "⑤ Ads → ⑥ Launch checklist", "",
         "## ① Verdict & winner score", ""]
    L += _kit_verdict(kw, mode)

    def section(title, fn):
        L.append("")
        L.append(title)
        try:
            L.append(_shift_headings(fn(), by=2))
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            L.append(f"_This section couldn't build right now ({str(exc)[:80]}). "
                     "Open its own tool and retry._")

    section("## ② Beat the competition", lambda: edge_finder(kw, mode))
    section("## ③ Listing draft", lambda: draft_listing(kw))
    section("## ④ Photo prompt set", lambda: photo_prompts(kw, mode))
    section("## ⑤ Etsy Ads plan", lambda: ads_plan(kw, mode))

    L += ["", "## ⑥ Seller launch checklist", "",
          "1. **Verdict** — trademark not HIGH, winner score healthy, demand + low "
          "competition confirmed (cross-check Google Trends).",
          "2. **Design** — make it stitch-safe (≤6 colors, bold, readable); order a "
          "REAL sew-out / print proof before scaling.",
          "3. **Listing** — paste the title (keyword in the first 40 chars), 13 tags, "
          "description + personalization; run the Listing Analyzer ([/grade](/grade)).",
          "4. **Profit gate** — confirm ≥35–40% net margin at your price "
          "([/profit](/profit)).",
          "5. **Photos** — shoot the REAL-PHOTO slots (hero + macro), generate the "
          "graphic slots, load image #1 as the thumbnail; add a video.",
          "6. **Edge** — apply the top 2 measured competitor gaps above before you "
          "publish.",
          "7. **Publish** — manually, inside Etsy; publish 3–5 variations of the "
          "concept, not one.",
          "8. **Ads** — start Etsy Ads at $1–3/day per the plan; read after 2 weeks, "
          "kill losers, scale the winner into 10–20 variations.",
          f"9. **Close the loop** — when it sells, "
          f"[log the sale here](/feedback?keyword={_uq(kw)}&product_mode={mode}"
          f"&title={_uq(kw.title())}) (pre-filled). Every logged order teaches the "
          "tool, so this niche and its tags rank higher in your Winner Finder "
          "automatically.",
          "",
          "_Assembled from live data where reachable; missing signals are left blank, "
          "never invented. Logged sales feed the private learning loop that sharpens "
          "future winner scores._"]
    return "\n".join(L)


# ---- Supplier Trend Finder (reverse signal: supplier heat -> demand lead) -----
def _etsy_comp_map():
    """{keyword_lower: competition_health 0-100} from the latest ETSY import, for
    cross-checking supplier leads against real Etsy saturation. Best-effort."""
    out = {}
    try:
        from src import shortlister_integration as si
        from src import opportunity_score as osc
        payload = si.load_latest_import()
        if not payload:
            return out
        headers = payload.get("headers") or []
        for row in (payload.get("rows") or []):
            d = si.map_row_to_scorer(headers, row, payload.get("view") or "")
            tag = (d.get("tag") or "").strip().lower()
            if not tag:
                continue
            c = osc._competition(d)
            if isinstance(c, (int, float)):
                out[tag] = c
    except (SystemExit, Exception):  # noqa: BLE001
        pass
    return out


def _etsy_status(keyword, comp_map):
    """Cross-check one lead vs the Etsy import -> (label, comp_health). Matches
    exact, else an Etsy keyword that contains all of the lead's words."""
    if not comp_map:
        return "", None
    kw = (keyword or "").lower()
    comp = comp_map.get(kw)
    if comp is None:
        toks = set(kw.split())
        for ek, ec in comp_map.items():
            if toks and toks <= set(ek.split()):
                comp = ec
                break
    if comp is None:
        return "", None
    if comp >= 65:
        return "🟢 OPEN", comp
    if comp >= 45:
        return "🟡 MEDIUM", comp
    return "🔴 CROWDED", comp


# Per-source copy so the same lead engine reads right for supplier vs Pinterest.
_TREND_SRC = {
    "supplier": {
        "title": "Supplier Trend Finder", "noun": "products",
        "demand_col": "Supplier demand", "count_col": "Suppliers", "traction_col": "Sold",
        "reorder": True,
        "empty": ("**No supplier import yet.** On the homepage drop box, choose "
                  "**Supplier export** and drop an Alibaba / AliExpress / 1688 export."),
        "lead": ("Reverse signal: what factories are pushing = what buyers and other "
                 "sellers are chasing"),
        "heat": "Supplier heat"},
    "pinterest": {
        "title": "Pinterest Trend Finder", "noun": "pins",
        "demand_col": "Pinterest demand", "count_col": "Pins", "traction_col": "Saves",
        "reorder": False,
        "empty": ("**No Pinterest import yet.** On the homepage drop box, choose "
                  "**Pinterest** and drop a pin export (title, saves, board)."),
        "lead": ("Leading signal: Pinterest is where gift/decor buyers plan weeks "
                 "ahead — high saves = rising demand"),
        "heat": "Pinterest heat"},
    "etsy": {
        "title": "Etsy Spy — keyword leads", "noun": "listings",
        "demand_col": "Demand", "count_col": "Listings", "traction_col": "Sold",
        "reorder": False,
        "empty": ("**No Etsy listings import yet.** On the homepage drop box, drop an "
                  "Etsy listings / spy export (title + sold/views + tags). A YTrends "
                  "**keyword** export goes to the Winner Finder instead."),
        "lead": ("What's already selling on Etsy: keywords that recur across ranking "
                 "listings = proven demand (mind the saturation — many listings also "
                 "means more competition)"),
        "heat": "Listing recurrence"},
}


def trend_leads(mode=None, source="supplier"):
    """Turn a manually exported SUPPLIER (Alibaba/AliExpress/1688) or PINTEREST table
    into ranked KEYWORD LEADS (demand sensing from the supply/interest side), then
    cross-check each against the latest Etsy import so the hot + Etsy-open leads
    float to the top. A lead is a demand LEAD, not proof — validate on Etsy."""
    from src import supplier_trend as st
    cfg = _TREND_SRC.get(source, _TREND_SRC["supplier"])
    res = st.analyze_latest(mode, source=source)
    if not res.get("ok"):
        return f"# {cfg['title']}\n\n> {cfg['empty']}"
    leads = res["leads"]
    label = MODE_LABEL.get(mode, mode)
    comp_map = _etsy_comp_map()
    L = [f"# {cfg['title']} — {res.get('view', source + ' import')}", "",
         f"_{cfg['lead']}. {len(leads)} keyword lead(s) from "
         f"{res.get('rows_in_import', 0)} {cfg['noun']} ({label}). Ranked by demand; "
         "the **★ gold** is hot **and** Etsy-open._", "",
         f"> {cfg['heat']} is a demand **lead, not proof.** The Etsy column "
         "cross-checks your latest Etsy import — a blank means the keyword isn't in "
         "it yet, so validate before building. Confidence (●) reflects how clean the "
         "keyword extraction was.", ""]
    if not comp_map:
        L += ["_Tip: import an Etsy/YTrends export too and the **Etsy** column lights "
              "up — that's how a lead becomes a confirmed hot × Etsy-open pick._", ""]
    if not leads:
        L += ["_No launchable keyword leads could be extracted (titles too "
              "brand-stuffed, or these aren't product rows)._"]
        return "\n".join(L)
    reo_h = " Reorder |" if cfg["reorder"] else ""
    reo_sep = "---|" if cfg["reorder"] else ""
    L += [f"| # | Keyword lead | {cfg['demand_col']} | {cfg['count_col']} "
          f"| {cfg['traction_col']} |{reo_h} Conf | Etsy | Build |",
          f"|---|---|---|---|---|{reo_sep}---|---|---|"]
    gold = []
    for i, ld in enumerate(leads, 1):
        sd = ld["supplier_demand"]
        bar = _barcell(sd) if sd is not None else "—"
        sold = (int(ld["sold_median"]) if isinstance(ld["sold_median"], (int, float))
                else "—")
        est, _ec = _etsy_status(ld["keyword"], comp_map)
        is_gold = est.endswith("OPEN") and (sd or 0) >= 55
        mark = "★ " if is_gold else ""
        if is_gold:
            gold.append(ld["keyword"])
        conf = {"high": "●●●", "med": "●●○", "low": "●○○"}.get(ld["confidence"], "")
        kwq = _uq(ld["keyword"])
        build = f"[Kit](/launch-kit?q={kwq}) · [Etsy](/edge?q={kwq})"
        reo_c = ""
        if cfg["reorder"]:
            reo = (f'{round(ld["reorder_pct"])}%'
                   if isinstance(ld["reorder_pct"], (int, float)) else "—")
            reo_c = f" {reo} |"
        L.append(f"| {i} | {mark}{_clean(ld['keyword'])} "
                 f"| `{bar}` {sd if sd is not None else ''} | {ld['supplier_count']} "
                 f"| {sold} |{reo_c} {conf} | {est or '—'} | {build} |")
    if gold:
        top = gold[0]
        L += ["", f"## ★ Top find: **{_clean(top)}** — hot **and** Etsy-open",
              f"Move first: [Build the Launch Kit](/launch-kit?q={_uq(top)}) · "
              f"[Beat competitors](/edge?q={_uq(top)})"]
    else:
        L += ["", "_No hot × Etsy-open pick yet. Either import an Etsy export to "
              "cross-check, or the hot leads are already crowded on Etsy — niche them "
              "down before building._"]
    return "\n".join(L)


def supplier_trends(mode=None):
    return trend_leads(mode, "supplier")


def pinterest_trends(mode=None):
    return trend_leads(mode, "pinterest")


def etsy_spy(mode=None):
    return trend_leads(mode, "etsy")
