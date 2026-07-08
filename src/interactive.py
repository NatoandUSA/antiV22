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


def calendar(mode=None):
    """Upcoming holiday/e-com calendar + live rising keywords + launch-by dates
    and product ideas. Delegates to src.seasonal."""
    from src import seasonal
    return seasonal.calendar_plan(mode)


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


def spy(kw, mode=None):
    """Competitor intelligence for a keyword — MODE-AWARE. Who wins, who dominates,
    who just launched, whether we can make it in this mode, and the gaps. Learning
    only: study structure, never copy."""
    kw = kw.strip()
    m = (mode or "").lower()
    if m not in ("pod", "embroidery", "both"):
        m = "embroidery" if matches_mode(kw.lower(), "embroidery") else "pod"
    label = {"pod": "Print on Demand", "embroidery": "Embroidery",
             "both": "POD vs Embroidery"}[m]
    L = [f"# 🕵️ Spy — {kw} · {label}", "",
         "_Competitor intelligence for **learning only**. Study structure + the "
         "gaps — never copy artwork, titles, descriptions, or photos._", ""]

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
