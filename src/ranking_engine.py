"""Layered Opportunity Ranking Engine (V29).

The composite Market-Signal score is NOT the master judge. Every keyword passes a
layered decision, and the Inbox shows the FINAL ACTION, not a bare number:

  L0  Risk / Product-fit GATE  (runs BEFORE the score; can BLOCK or CAP)
  L1  Etsy Proof               (real sold/revenue/shop-spread — when available)   [future]
  L2  Market Signal            (the composite: demand/competition/conversion/momentum)
  L3  Can We Win               (supplier/profit/image/offer gaps)                 [future]
  L4  Final Action             BUILD_NOW / CONFIRM_FIRST / REVIEW / WATCH / SKIP / BLOCKED

L1 and L3 need per-listing sales + supplier/profit data that the current exports
don't reliably carry, so they light up as that data arrives; today the engine runs
L0 (product_fit + trademark) over L2 (opportunity_score) and ends on L4. This keeps
broad seeds, themes-without-a-product, shop names, policy/spiritual, and trademark
terms from being promoted to "Build" on the strength of a market score alone.
"""
import re

from src.product_fit import (classify, LAUNCHABLE, GENERIC, POD_NOUNS, EMB_SIGNS,
                             JEWELRY_NOUNS, ACRYLIC_NOUNS)

# Audience/recipient words that describe WHO, not a design theme. A term made only
# of [generic]+[product]+[audience] (e.g. "custom shirt kids") is a bare product
# category with no design angle -> it must go through the Pattern Miner to find an
# angle before Launch Kit, even though it names a real product.
_AUDIENCE = {"kids", "kid", "child", "children", "toddler", "baby", "men", "man",
             "women", "woman", "boys", "boy", "girls", "girl", "mom", "mum", "dad",
             "him", "her", "family", "couple", "couples", "teen", "teens", "adult",
             "unisex", "ladies", "guys", "grandma", "grandpa", "nana", "papa"}
_PRODUCT_NOUNS = POD_NOUNS | JEWELRY_NOUNS | ACRYLIC_NOUNS | EMB_SIGNS


def _has_design_angle(keyword):
    """True if the keyword carries a distinctive design/theme token (a niche, motif,
    occasion, or subject) beyond generic words, the product noun, and audience."""
    words = set(re.findall(r"[a-z0-9]+", (keyword or "").lower()))
    words |= {w[:-1] for w in list(words) if w.endswith("s") and len(w) > 3}
    theme = words - GENERIC - _AUDIENCE - _PRODUCT_NOUNS
    return bool(theme)

# Final actions, ordered by how actionable they are (higher = closer to build).
BUILD_NOW, CONFIRM_FIRST, REVIEW, WATCH, SKIP, BLOCKED = (
    "BUILD_NOW", "CONFIRM_FIRST", "REVIEW", "WATCH", "SKIP", "BLOCKED")
_PRI = {BLOCKED: 0, SKIP: 1, WATCH: 2, REVIEW: 3, CONFIRM_FIRST: 4, BUILD_NOW: 5}

# L0 gate: product-fit status -> (hard-or-cap action, reason, route hint).
# HARD actions (BLOCKED/SKIP) end it. CAP actions bound the market action from above.
_GATE = {
    "TRADEMARK_RISK":         (BLOCKED, "trademark / brand term - do not build", "blocked"),
    "POLICY_RISK":            (REVIEW,  "policy / spiritual niche - manager review before any build", "review"),
    "SHOP_NAME_LIKELY":       (SKIP,    "looks like a shop / brand name, not a product", "skip"),
    "NON_PRODUCT":            (SKIP,    "not a makeable product", "skip"),
    "DIGITAL_FIT":            (SKIP,    "digital-only - not your physical POD / embroidery line", "skip"),
    "LOW_BUYER_INTENT":       (WATCH,   "curiosity / low buyer intent - unlikely to convert", "watch"),
    "AMBIGUOUS_PHRASE":       (WATCH,   "meaning / intent unclear - needs a clearer angle", "watch"),
    "BROAD_SEED_ONLY":        (CONFIRM_FIRST, "broad seed - run Pattern Miner / pick a niche angle before Launch Kit", "pattern"),
    "THEME_FIT_NEEDS_PRODUCT": (CONFIRM_FIRST, "theme with no product - choose a product angle (shirt / sweatshirt / mug / tote) first", "pattern"),
}

# L2 market-signal verdict -> the action it would justify on its own.
_MARKET_ACTION = {"GO": BUILD_NOW, "CONDITIONAL": CONFIRM_FIRST,
                  "WATCH": WATCH, "SKIP": SKIP}

# Default route (link target) for an action when the gate doesn't override it.
_ROUTE = {BUILD_NOW: "build", CONFIRM_FIRST: "analyze", REVIEW: "review",
          WATCH: "analyze", SKIP: "skip", BLOCKED: "blocked"}


def decide(keyword, market_verdict, mode=None, fit=None, proof=None):
    """Full layered decision: L0 gate -> L1 Etsy proof -> L2 market -> L4 action.

    `proof` (optional) is an etsy_proof record with real sales evidence. When present
    and the term isn't hard-gated (trademark/shop-name/policy), real Etsy sales OVERRIDE
    the market signal - a niche that is actually selling ranks above one that only looks
    good on paper. Returns the base fields plus proof_tier (0 proven, 1 selling, 9 none)
    and proof (echoed for the view)."""
    base = _base_decide(keyword, market_verdict, mode, fit)
    base["proof_tier"] = 9
    base["proof"] = None
    if not proof:
        return base
    base["proof"] = proof
    # Hard gates still win: a trademark/shop-name/policy term stays blocked/skipped/
    # under review even if it's selling - selling a trademarked item is still risky.
    if base["action"] in (BLOCKED, SKIP, REVIEW):
        return base
    v = proof.get("verdict")
    ev = proof.get("evidence", "")
    match = proof.get("match", "exact")
    conf = proof.get("match_confidence", 1.0)
    from src.engine_config import get as _cfg
    high_conf = match == "exact" or (conf or 0) >= _cfg("proof_match_high_conf")
    if v == "PROVEN_WINNER" and high_conf:
        base.update({"action": BUILD_NOW, "route": "build", "proof_tier": 0,
                     "priority": _PRI[BUILD_NOW],
                     "reason": f"PROVEN on Etsy - real sales, spread across shops "
                     f"({ev})"})
    elif v == "PROVEN_WINNER":
        # medium-confidence fuzzy match: strong evidence but the keyword<->proof
        # link needs a human eye before it can promote to BUILD (review consensus).
        # RAISE-only (audit fix): weaker actions come UP to CONFIRM_FIRST with the
        # confirm-the-match reason; a merit-earned BUILD_NOW keeps its action AND
        # its market reason (proof note appended) - no more 'Build now' rows
        # captioned "confirm the match first".
        if _PRI[base["action"]] < _PRI[CONFIRM_FIRST]:
            base.update({"action": CONFIRM_FIRST, "route": "analyze",
                         "priority": _PRI[CONFIRM_FIRST],
                         "reason": (f"PROVEN evidence via fuzzy match (confidence "
                                    f"{conf}) - confirm the match, then build ({ev})")})
        else:
            base["reason"] += (f" + possible Etsy proof via fuzzy match "
                               f"(confidence {conf}, {ev}) - verify the match")
        base["proof_tier"] = 1
    elif v == "STRONG_SELLER":
        if _PRI[base["action"]] < _PRI[CONFIRM_FIRST]:
            base.update({"action": CONFIRM_FIRST, "route": "analyze",
                         "priority": _PRI[CONFIRM_FIRST]})
        base["proof_tier"] = 1
        base["reason"] = f"strong seller on Etsy ({ev}) - {base['reason']}"
    elif v == "SELLING":
        # already selling -> at least confirm-first; keep build if the base earned it
        if _PRI[base["action"]] < _PRI[CONFIRM_FIRST]:
            base.update({"action": CONFIRM_FIRST, "route": "analyze",
                         "priority": _PRI[CONFIRM_FIRST]})
        base["proof_tier"] = 2
        base["reason"] = f"already selling on Etsy ({ev}) - {base['reason']}"
    return base


def _base_decide(keyword, market_verdict, mode=None, fit=None):
    """L0 gate + L2 market verdict -> a base Final Action (no proof).

    Returns {action, reason, route, fit_status, fit_label, launchable, priority}."""
    fit = fit or classify(keyword or "", mode)
    status = fit.get("status", "")
    launchable = status in LAUNCHABLE
    market_action = _MARKET_ACTION.get(market_verdict, WATCH)

    gate = _GATE.get(status)
    if gate:
        gate_action, gate_reason, gate_route = gate
        if gate_action in (BLOCKED, SKIP):                 # hard stop
            return _out(gate_action, gate_reason, gate_route, fit, launchable)
        # cap: the market action can't exceed the gate's ceiling
        if _PRI[gate_action] <= _PRI[market_action]:       # cap binds
            return _out(gate_action, gate_reason, gate_route, fit, launchable)
        # market signal is weaker than the cap -> market decides, gate note kept
        return _out(market_action, _market_reason(market_verdict, gate_reason),
                    _ROUTE[market_action], fit, launchable)

    # no gate, but a bare product category with no design angle (e.g. "custom shirt
    # kids") -> don't send it straight to Launch Kit: cap at CONFIRM_FIRST and route
    # it through the Pattern Miner to find the winning angle first.
    if launchable and not _has_design_angle(keyword):
        capped = market_action if _PRI[market_action] <= _PRI[CONFIRM_FIRST] else CONFIRM_FIRST
        if capped in (SKIP, WATCH):     # weak market -> let it fall, no false promotion
            return _out(capped, _market_reason(market_verdict), _ROUTE[capped],
                        fit, launchable)
        return _out(CONFIRM_FIRST,
                    "bare product category, no design angle - run Pattern Miner to "
                    "find the winning angle before Launch Kit", "pattern",
                    fit, launchable)

    # LONG-TAIL RULE (owner: "long-tail always converts better; MORE than 3 words";
    # matches eRank/seller consensus; thresholds configurable in config/engine.json):
    # - <= short_tail_max_words (2): saturated price-war territory -> Pattern Miner.
    # - exactly 3 words: BORDERLINE - still not enough specificity for a blind
    #   build; confirm/expand to a 4-5 word buyer-intent angle first.
    # - >= long_tail_min_words (4): true long-tail, heuristic BUILD allowed.
    # Real Etsy PROOF still overrides later in decide() - evidence beats heuristics.
    from src.engine_config import get as _cfg
    n_words = _word_count(keyword)
    lt_min = int(_cfg("long_tail_min_words"))
    st_max = int(_cfg("short_tail_max_words"))
    if launchable and market_action == BUILD_NOW and n_words < lt_min:
        if n_words <= st_max:
            return _out(CONFIRM_FIRST,
                        f"short-tail keyword ({n_words} words) - saturated + "
                        "price-war territory; expand to a 4-5 word long-tail angle "
                        "(Pattern Miner / Keyword Lab) before building", "pattern",
                        fit, launchable)
        return _out(CONFIRM_FIRST,
                    f"borderline long-tail ({n_words} words) - strong signal, but "
                    f"expand to a {lt_min}+ word buyer-intent angle (or bring real "
                    "sales proof) before building", "pattern", fit, launchable)

    # no gate -> a launchable product WITH a design angle: the market signal decides
    reason = _market_reason(market_verdict)
    if launchable and n_words >= lt_min and market_action in (BUILD_NOW, CONFIRM_FIRST):
        reason += (f" - long-tail ({n_words} words): higher buyer intent, "
                   "lower competition")
    return _out(market_action, reason, _ROUTE[market_action], fit, launchable)


def _market_reason(verdict, gate_note=None):
    base = {
        "GO": "strong market signal on a makeable product",
        "CONDITIONAL": "decent market signal - confirm the angle before building",
        "WATCH": "weak market signal - monitor, don't build yet",
        "SKIP": "market signal too weak - saturated or thin",
    }.get(verdict, "insufficient signal")
    return f"{base} (note: {gate_note})" if gate_note else base


def _word_count(keyword):
    return len(re.findall(r"[a-z0-9]+", (keyword or "").lower()))


def _out(action, reason, route, fit, launchable):
    return {"action": action, "reason": reason, "route": route,
            "fit_status": fit.get("status", ""), "fit_label": _label(fit),
            "launchable": launchable, "priority": _PRI[action]}


# Short human labels for the product-fit status column.
_LABELS = {
    "POD_FIT": "POD product", "EMBROIDERY_FIT": "Embroidery", "JEWELRY_FIT": "Jewelry",
    "ACRYLIC_FIT": "Acrylic", "THEME_FIT_READY": "Theme (ready)",
    "THEME_FIT_NEEDS_PRODUCT": "Theme - needs product", "BROAD_SEED_ONLY": "Broad seed",
    "AMBIGUOUS_PHRASE": "Unclear", "LOW_BUYER_INTENT": "Low intent",
    "DIGITAL_FIT": "Digital-only", "SHOP_NAME_LIKELY": "Shop name",
    "POLICY_RISK": "Policy risk", "TRADEMARK_RISK": "Trademark", "NON_PRODUCT": "Not a product",
}


def _label(fit):
    return _LABELS.get(fit.get("status", ""), fit.get("status", "").replace("_", " ").title())


# Display metadata for the Final Action (icon + colour hint for the view).
ACTION_META = {
    BUILD_NOW:     ("\U0001F680", "Build now"),
    CONFIRM_FIRST: ("\U0001F50D", "Confirm first"),
    REVIEW:        ("\U0001F6A9", "Manager review"),
    WATCH:         ("\U0001F7E1", "Watch"),
    SKIP:          ("⛔", "Skip"),
    BLOCKED:       ("\U0001F6AB", "Blocked"),
}
