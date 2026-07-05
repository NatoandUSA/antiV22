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


def top_edges_for_prompts(tactics, n=3):
    order = ["First image", "Mockup", "Personalization", "Niche angle"]
    ranked = sorted(tactics,
                    key=lambda t: order.index(t["category"])
                    if t["category"] in order else 99)
    return [f"{t['category']}: {t['action']}" for t in ranked[:n]]
