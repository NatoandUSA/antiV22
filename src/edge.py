"""Competitive Edge engine (V17).

Every seller can buy the same keyword data. This module answers the question
that actually produces sales: HOW do we beat the listings already ranking?

It reads the competitor audit + package + market data and produces concrete,
evidence-backed tactics across the 11 edge categories, each with an owner.
Where the evidence needs a human eye (photo quality), it says exactly what
to check instead of pretending.
"""


def build_edge_plan(audit, packages, best, harvest_niches=None):
    tactics = []

    def add(cat, action, evidence, owner):
        tactics.append({"category": cat, "action": action,
                        "evidence": evidence, "owner": owner})

    prices = [a["price"] for a in audit if a.get("price")]
    videos = [(a.get("has_video") or "").strip().lower() for a in audit]
    photos = [a.get("photo_count") for a in audit
              if str(a.get("photo_count") or "").strip().isdigit()]
    pers = [(a.get("personalization_options") or "").strip().lower()
            for a in audit]
    proc = [(a.get("processing_time") or "").strip() for a in audit]
    intents = {i for x in (best["keywords"] if best else []) for i in x["intents"]}
    pm = best.get("profit") if best else None

    # 1. Better first image
    add("First image",
        "Design the main photo to read at THUMBNAIL size: product large, "
        "personalization name visible ('Emma'), clean bright background, "
        "one focal point. Test 2 main-image variants from day 4.",
        ("Manual check: open each competitor link and score their first "
         "image 1-10 in competitor_audit.csv - beat the weakest.")
        if not photos else
        f"Competitors average {sum(photos)//len(photos)} photos - visual "
        "bar is measurable.", "Designer")

    # 2. Better mockup
    add("Mockup",
        "Use lifestyle mockups (product in real use: concert outfit, "
        "packed travel bag) instead of flat product-only shots most POD "
        "sellers use.", "Standard POD mockups dominate this niche - "
        "lifestyle context is an instant visual difference.", "Designer")

    # 3. Better personalization
    if any(p in ("", "no", "none") for p in pers) or not pers:
        add("Personalization",
            "Offer name/initials personalization AND show 3+ font choices "
            "in photo #7; many ranking listings offer none or one style.",
            ("Audit shows competitors with empty/none personalization "
             "fields." if pers else
             "Fill personalization_options in the audit to confirm the gap."),
            "Seller + Designer")

    # 4. Better positioning / niche angle
    if intents:
        angle = "gift-occasion" if "gift" in intents or "event" in intents \
            else "daily-utility"
        add("Niche angle",
            f"Position as a {angle} product in title line 1 and photo #6 "
            f"(gift-ready mockup), not just a generic item. Detected buyer "
            f"intents: {', '.join(sorted(intents))}.",
            "Intent labels derived from the cluster's actual search terms.",
            "Seller")

    # 5. Better bundle/gift offer
    if "event" in intents or "gift" in intents:
        add("Bundle offer",
            "Add a visible 'sets of 4+ get 10% off' line (description top) "
            "and a flat-lay photo of 5 personalized units - bridesmaid/"
            "team buyers purchase in multiples.",
            "Event/gift intent present in cluster keywords; multi-unit "
            "orders raise AOV without raising traffic.", "Seller")

    # 6. Better pricing strategy
    if prices and pm:
        lo, hi = min(prices), max(prices)
        add("Pricing",
            f"Enter at ${pm['sale_price']} with free US shipping baked in "
            f"(competitors span ${lo}-${hi}); never be the cheapest - "
            f"cheapest signals low quality in personalized goods.",
            f"Live competitor price spread ${lo}-${hi}; your floor for $6 "
            f"profit is ${pm['price_for_6_profit']}.", "Manager")

    # 7. Better SEO
    if packages:
        add("SEO",
            "Use all 13 tags (many competitors leave tags empty), front-"
            "load the exact primary keyword in the title, and refresh the "
            "2 weakest tags weekly from 'py main.py grow' harvest results.",
            "Tag sets in packages are built from live co-occurrence data, "
            "not guesses.", "Seller")

    # 8. Better customer trust
    add("Trust",
        "Complete shop About + policies + FAQ before day 1; answer "
        "messages within 2 hours during US daytime; state 'we reply fast' "
        "in every description.",
        "New shops convert on trust signals, not reviews they don't have "
        "yet.", "Seller")

    # 9. Better shipping/processing clarity
    if any(not p for p in proc) or not proc:
        add("Shipping clarity",
            "State exact processing + delivery window in the FIRST "
            "description line and photo #9; buyers abandon listings with "
            "vague shipping.",
            "Competitor processing_time fields are empty in the audit - "
            "confirm manually; vagueness is common and beatable.",
            "Seller")

    # 10. Better video
    if not videos or all(v in ("", "no") for v in videos):
        add("Video",
            "Add the 5-15s video from the listing package to every "
            "listing - Etsy boosts listings with video and most POD "
            "competitors skip it.",
            "No confirmed competitor videos in the audit yet.", "Designer")

    # 11. Better product line expansion
    exp = ", ".join(harvest_niches[:4]) if harvest_niches else \
        "run 'py main.py grow' to find adjacent variants"
    add("Product line",
        f"After first sale, expand the winning design across adjacent "
        f"variants the data already found: {exp}.",
        "Adjacent niches harvested from live co-occurrence data.",
        "Manager")

    return tactics


# --------------------------------------------------------------------------
# MEASURED edge engine (roadmap #9): instead of the same static tactics for
# every niche, MEASURE each weakness from the real competitor listings and rank
# the biggest exploitable gap first. Signals with no data are reported honestly
# as "manual check" (never given a fake magnitude), so the ranking is only ever
# built on numbers we actually have.
# --------------------------------------------------------------------------

_PERS_TOKENS = ("personal", "custom", "monogram", "name", "initial", "your ")


def _lst_num(v):
    try:
        f = float(str(v).replace(",", "").replace("$", "").replace("%", "").strip())
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _lget(row, *keys):
    """Tolerant getter across the field names the different sources use
    (extension/HeyEtsy he_*, MCP hot_listings, manual audit)."""
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return None


def _tag_count(row):
    t = _lget(row, "tags", "he_tags", "tag_list")
    if isinstance(t, (list, tuple)):
        return len([x for x in t if str(x).strip()])
    if isinstance(t, str) and t.strip():
        return len([x for x in t.split(",") if x.strip()])
    return None


def measure_edges(listings, comp=None):
    """Rank how to beat the listings already ranking for a niche, by MEASURING
    each gap from the real competitor rows (+ an optional niche competition
    snapshot). Returns a list of edges sorted biggest-measured-gap first, each:
    {category, magnitude (0-100 or None), measured (bool), headline, action,
     evidence, owner}. `comp` is the analyze_competition dict (saturation,
     new_entrant_rate, avg_listing_age_days) if available."""
    rows = [r for r in (listings or []) if isinstance(r, dict)]
    edges = []

    def add(cat, mag, measured, headline, action, evidence, owner):
        edges.append({"category": cat, "magnitude": mag, "measured": measured,
                      "headline": headline, "action": action,
                      "evidence": evidence, "owner": owner})

    titles = [(str(_lget(r, "title", "he_title") or "")).strip() for r in rows]
    titles = [t for t in titles if t]

    # 1) PERSONALIZATION gap - measurable straight from the titles.
    if titles:
        no_pers = [t for t in titles
                   if not any(tok in t.lower() for tok in _PERS_TOKENS)]
        pct = round(len(no_pers) / len(titles) * 100)
        add("Personalization", pct, True,
            f"{pct}% of the top listings don't signal personalization in the title",
            "Offer name/initials/monogram and put it in the FIRST 40 chars of the "
            "title + show 3 font choices in an image. This is the fastest gap to own.",
            f"{len(no_pers)} of {len(titles)} ranking titles have no personalization "
            "token.", "Seller + Designer")

    # 2) TITLE / SEO gap - short or generic titles = weak relevancy to beat.
    if titles:
        weak = [t for t in titles if len(t.split()) < 6]
        pct = round(len(weak) / len(titles) * 100)
        if pct:
            add("Title / SEO", pct, True,
                f"{pct}% of rivals use short/generic titles (<6 words)",
                "Write full, keyword-front-loaded long-tail titles (buyer + occasion "
                "+ product). Etsy relevancy is the #1 rank signal in 2026.",
                f"{len(weak)} of {len(titles)} titles are under 6 words.", "Seller")

    # 3) TAG coverage gap - only when the source carries tag data.
    tag_counts = [c for c in (_tag_count(r) for r in rows) if isinstance(c, int)]
    if tag_counts:
        weak_tags = [c for c in tag_counts if c < 13]
        pct = round(len(weak_tags) / len(tag_counts) * 100)
        if pct:
            add("Tag coverage", pct, True,
                f"{pct}% of rivals don't use all 13 tags",
                "Fill all 13 tags with multi-word buyer-intent phrases - each empty "
                "slot is a search you can win uncontested.",
                f"{len(weak_tags)} of {len(tag_counts)} listings use <13 tags "
                f"(avg {round(sum(tag_counts)/len(tag_counts),1)}).", "Seller")

    # 4) TRACTION concentration - a top-heavy niche with a weak tail is beatable.
    sold = [s for s in (_lst_num(_lget(r, "total_sold", "he_sold", "sold"))
                        for r in rows) if s is not None]
    if len(sold) >= 4:
        srt = sorted(sold, reverse=True)
        top = sum(srt[:max(1, len(srt) // 5)])          # top ~20%
        total = sum(srt) or 1
        share = round(top / total * 100)
        tail = len([s for s in sold if s <= (srt[0] * 0.1)])
        if share >= 55:
            add("Weak tail", share, True,
                f"Top listings hold {share}% of sales - the rest are soft",
                "You don't need to beat the #1 - target the long tail of low-sold "
                "listings holding rank on weak photos/SEO and outrank them.",
                f"{tail} of {len(sold)} listings sit under 10% of the leader's sales.",
                "Seller")

    # 5) PRICE positioning - a wide spread means room to win on value, not price.
    prices = [p for p in (_lst_num(_lget(r, "price", "he_price"))
                          for r in rows) if p]
    if len(prices) >= 3:
        lo, hi = min(prices), max(prices)
        if hi > lo:
            spread = round((hi - lo) / hi * 100)
            add("Price / value", spread, True,
                f"Competitor prices span ${lo:.0f}-${hi:.0f}",
                "Don't race to the bottom on personalized goods - price in the upper "
                "-middle with better personalization + a bundle; cheapest reads as "
                "low quality.",
                f"Live spread ${lo:.0f}-${hi:.0f} ({spread}% range).", "Manager")

    # 6) DISCOUNT war - heavy discounting = margin-weak rivals you can out-position.
    disc = [d for d in (_lst_num(_lget(r, "he_discount_pct", "discount"))
                        for r in rows) if d is not None]
    if disc:
        heavy = [d for d in disc if d >= 20]
        pct = round(len(heavy) / len(disc) * 100)
        if pct >= 30:
            add("Anti-discount", pct, True,
                f"{pct}% of rivals lean on 20%+ discounts",
                "Compete on personalization + first image, not price. Discount-heavy "
                "rivals are margin-weak; hold price and win on perceived value.",
                f"{len(heavy)} of {len(disc)} listings run 20%+ off.", "Manager")

    # 7) NICHE saturation / room - from the competition snapshot if we have it.
    if isinstance(comp, dict) and comp:
        ner = _lst_num(comp.get("new_entrant_rate"))
        age = _lst_num(comp.get("avg_listing_age_days"))
        sat = str(comp.get("saturation") or "").lower()
        if ner is not None and ner > 0:
            mag = min(100, round(ner * 100)) if ner <= 1 else min(100, round(ner))
            add("Room to enter", mag, True,
                f"New sellers are still breaking in ({mag}% new-entrant rate)",
                "The niche still admits new shops - enter now on a narrow angle "
                "before it saturates.",
                f"New-entrant rate {mag}%"
                + (f", avg listing age {int(age)}d" if age else "")
                + (f", saturation {sat}" if sat else "") + ".", "Seller")

    edges.sort(key=lambda e: (0 if e["measured"] else 1, -(e["magnitude"] or 0)))

    # 8) Signals that genuinely need a human eye - reported honestly, never faked,
    # and always last so they never outrank a measured gap.
    add("Video", None, False,
        "Most POD/embroidery rivals skip video - a near-universal free gap",
        "Add a 5-15s video to every listing; Etsy boosts listings that have one.",
        "Not in the data feed - glance at the top 5 listings to confirm (most "
        "won't have a video).", "Designer")
    add("First image", None, False,
        "The single biggest CTR lever - judge it by eye",
        "Open the top 5 listings; score each first image 1-10. Beat the weakest "
        "with a bolder hero: big subject, visible name, clean bright background.",
        "Image quality isn't in any data feed - a 2-minute manual scan.", "Designer")

    return edges


def top_edges_for_prompts(tactics, n=3):
    order = ["First image", "Mockup", "Personalization", "Niche angle"]
    ranked = sorted(tactics,
                    key=lambda t: order.index(t["category"])
                    if t["category"] in order else 99)
    return [f"{t['category']}: {t['action']}" for t in ranked[:n]]
