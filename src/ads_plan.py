"""Etsy Ads - MANUAL starter plan generator.

This is the honest, Etsy-accurate version - NOT an Amazon PPC clone. Etsy Ads is
one campaign with ONE daily budget; you do NOT bid per keyword and there are no
exact / phrase / broad match types. Etsy decides placement and matches shoppers
to your listing using its TAGS, TITLE and attributes. So the only real levers a
seller controls are:

    1. which listings are switched ON in the campaign,
    2. the daily budget,
    3. how well the listing's TAGS + TITLE cover buyer-intent search phrases
       (that is literally what Etsy matches on),
    4. reading the stats after ~2 weeks and killing the losers.

This module turns a keyword + its economics into a ready-to-apply plan around
those four levers, with a breakeven ACOS/ROAS computed from the REAL Etsy fee
model (src/profit.py). Nothing here touches the seller's Etsy account - it just
tells the human exactly what to set inside Etsy's own Ads dashboard.

HONEST-NULLS: if we don't know the price or product cost we do NOT invent a
breakeven number - we hand back the formula and say "fill this in", same as the
rest of the project.
"""

# Etsy's minimum campaign budget is $1.00/day. A brand-new listing needs a few
# clicks/day to gather signal without burning cash while it has no reviews yet.
MIN_DAILY = 1.0
START_DAILY = 3.0          # enough clicks to read in 2 weeks, small enough to be safe
TEST_DAYS = 14             # Etsy attributes a sale up to 30 days, but 14 days of
                           # spend is enough to see which listings never convert.

# Rough Etsy search conversion band (order / visit) for a decent listing. Used
# only to sanity-check "how many clicks per sale" when the row has no real CR.
ASSUMED_CR = 0.02          # 2% - conservative; real CR replaces this when known


def _num(v):
    try:
        f = float(v)
        return f if f == f else None      # drop NaN
    except (TypeError, ValueError):
        return None


def _economics(price, product_cost, shipping_cost=0.0):
    """Real per-sale P&L via the project's Etsy fee model -> the ad math.

    Returns None if price or cost is unknown (honest-null). Breakeven ACOS is the
    share of revenue you can spend on ads before the sale stops making money;
    breakeven ROAS is its inverse (revenue per $1 of ad spend to break even)."""
    price = _num(price)
    pc = _num(product_cost)
    if price is None or pc is None or price <= 0:
        return None
    sc = _num(shipping_cost) or 0.0
    try:
        from src import profit
        # Profit BEFORE any ad spend. We do NOT flag offsite_ad here: offsite ads
        # are a separate mandatory fee, handled as its own note below, not part of
        # the Etsy Ads (onsite) breakeven.
        row = profit.compute(price, pc, sc, offsite_ad=False)
        net = row["net_profit"]
    except Exception:  # noqa: BLE001 - fall back to a plain margin if profit.py moves
        net = price - pc - sc
    if net <= 0:
        return {"price": round(price, 2), "net_profit": round(net, 2),
                "margin_pct": round(net / price * 100, 1),
                "breakeven_acos_pct": 0.0, "breakeven_roas": None,
                "target_acos_pct": 0.0, "unprofitable": True}
    be_acos = net / price * 100.0            # % of revenue that is pure profit
    tgt_acos = be_acos * 0.6                  # keep ~40% of the margin as profit
    return {"price": round(price, 2),
            "net_profit": round(net, 2),
            "margin_pct": round(net / price * 100, 1),
            "breakeven_acos_pct": round(be_acos, 1),
            "breakeven_roas": round(100.0 / be_acos, 2) if be_acos else None,
            "target_acos_pct": round(tgt_acos, 1),
            "target_roas": round(100.0 / tgt_acos, 2) if tgt_acos else None,
            "unprofitable": False}


# Buyer-intent categories Etsy Ads should be able to match on. If a listing's
# tags miss one of these, it can't show for that kind of shopper search.
_INTENT = [
    ("personalization", ("personalized", "custom", "monogram", "name", "customized")),
    ("gift intent", ("gift", "gift for", "present")),
    ("buyer / recipient", ("for her", "for him", "for mom", "for dad", "for men",
                           "for women", "for nurse", "for teacher", "for")),
    ("occasion", ("birthday", "christmas", "anniversary", "graduation",
                  "mothers day", "fathers day", "valentine", "wedding")),
    ("product type", ("shirt", "sweatshirt", "hoodie", "tote", "mug", "hat",
                      "cap", "blanket", "tumbler", "sign", "necklace")),
]


def _tag_gaps(tags):
    """Which buyer-intent categories the current tag set does NOT cover yet -
    these are the phrases Etsy Ads currently can't match you on."""
    joined = " ".join((t or "").lower() for t in (tags or []))
    gaps = []
    for label, needles in _INTENT:
        if not any(n in joined for n in needles):
            gaps.append(label)
    return gaps


def build(keyword, tags=None, price=None, product_cost=None, shipping_cost=0.0,
          mode="embroidery", conversion_rate=None):
    """Return a structured Etsy Ads manual starter plan (a dict the view renders).

    keyword        - the main keyword / niche the campaign is for
    tags           - the listing's current 13 tags (drives the coverage check)
    price          - intended sale price (USD)
    product_cost   - your supplier/base cost per unit (USD)
    shipping_cost  - your shipping cost per unit (USD), if any
    mode           - 'embroidery' | 'pod' (labels only)
    conversion_rate- real order/visit rate if known (e.g. 0.02), else assumed
    """
    kw = (keyword or "your keyword").strip()
    tags = [t for t in (tags or []) if t]
    econ = _economics(price, product_cost, shipping_cost)
    cr = _num(conversion_rate) or ASSUMED_CR

    # Max cost-per-click you can average and still hit the target ACOS:
    #   target_ad_$_per_sale = price * target_acos ; clicks_per_sale = 1/CR
    #   max_avg_cpc = target_ad_$_per_sale / clicks_per_sale
    max_cpc = None
    clicks_per_sale = round(1.0 / cr) if cr else None
    if econ and not econ.get("unprofitable") and clicks_per_sale:
        tgt_spend = econ["price"] * econ["target_acos_pct"] / 100.0
        max_cpc = round(tgt_spend / clicks_per_sale, 2)

    gaps = _tag_gaps(tags)

    read_kill = [
        f"Give it {TEST_DAYS} days before judging any listing - Etsy needs clicks "
        "to gather data, and a new listing has no reviews working for it yet.",
        "KILL a listing in the campaign if it spent the price of ~2 units in ads "
        "with 0 sales - the ad works, the listing doesn't convert (fix photos / "
        "price / title, then re-add it).",
        "KEEP + nudge budget up (max +$1/day/week) on any listing whose ACOS is "
        + (f"under ~{econ['breakeven_acos_pct']}% (breakeven)."
           if econ and not econ.get("unprofitable")
           else "clearly below your breakeven once you know your margin."),
        "Pause the whole campaign if 2 weeks of spend produced no profitable "
        "listing - the money is better spent improving the listings first.",
        "Never raise the daily budget to 'buy' more sales from a listing that is "
        "losing money per order - you only scale winners.",
    ]

    checklist = [
        "In Etsy Shop Manager -> Marketing -> Etsy Ads, start ONE campaign at "
        f"${START_DAILY:.0f}/day (Etsy minimum is ${MIN_DAILY:.0f}).",
        "Turn ON only your best 3-5 listings for this niche - not everything. A "
        "wide budget spread across weak listings just burns cash.",
        "Make sure each advertised listing uses all 13 tags and a keyword-front "
        "title - that TAG/TITLE text is exactly what Etsy Ads matches shoppers on "
        "(there is no separate keyword bidding on Etsy).",
        "Fill every listing photo slot and add a video - Etsy favours complete, "
        "high-quality listings in ad placement, and it lifts conversion.",
        f"Let it run {TEST_DAYS} days WITHOUT fiddling, then open Etsy Ads stats "
        "and apply the read/kill rules below.",
    ]

    notes = [
        "Etsy Ads (onsite) is separate from OFFSITE ADS: offsite is a mandatory "
        "12-15% fee Etsy charges only when a sale came from its external ads, and "
        "you cannot opt out under $10k/yr in sales. Price with that in mind; it is "
        "not part of this onsite campaign's math.",
        "You control budget + which listings are on - Etsy controls placement. "
        "Treat tags/title as your real 'targeting'.",
    ]
    if econ is None:
        notes.insert(0, "No price/cost on file yet, so the breakeven is a formula, "
                     "not a number: breakeven ACOS = net profit per sale / sale "
                     "price. Fill in your price and supplier cost to get the real "
                     "figure and a max average CPC.")
    elif econ.get("unprofitable"):
        notes.insert(0, "At this price the sale loses money BEFORE any ad spend - "
                     "do not advertise it. Raise the price or lower the cost first.")

    return {
        "keyword": kw,
        "mode": mode,
        "economics": econ,
        "assumed_cr": None if _num(conversion_rate) else ASSUMED_CR,
        "clicks_per_sale": clicks_per_sale,
        "max_avg_cpc": max_cpc,
        "start_daily": START_DAILY,
        "min_daily": MIN_DAILY,
        "test_days": TEST_DAYS,
        "priority_tags": tags[:13],
        "tag_gaps": gaps,
        "checklist": checklist,
        "read_kill_rules": read_kill,
        "notes": notes,
    }
