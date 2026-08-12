"""Patch 4 Stage 2 -- actionability overlay (shadow mode).

Pure, deterministic function: no DB writes, no API calls, no ranking
mutation. Sits OUTSIDE frozen L0-L4 (product_fit / ranking_engine /
opportunity_score / etsy_proof / opportunity_inbox) and only reads their
output. `engine_final_action` is never edited -- this proposes a second,
advisory `execution_action` for the operator to compare against it.

Two-axis model (owner-approved after the Phase B read-only audit found a 49%
disagreement rate between engine action and true specificity):
  - market_angle_specificity: does the phrase carry a strong buyer angle
    (profession/role, occasion, use-case) or a validated COMBINATION of two
    distinct medium-strength signals (audience, personalization, motif,
    generic-gift)? A single medium signal, a bare product noun, or a weak
    modifier (funny/cute/vintage/...) is NOT enough alone.
  - product_specificity is tracked for the reason codes but does not by
    itself upgrade a row -- see recommended_v1_rule in the authorizing doc.

BROAD_PARENT -> propose MINE_NICHE (run Pattern Miner / Keyword Lab for a
    real child niche before Launch Kit -- never fabricate one).
AMBIGUOUS_REVIEW -> propose REVIEW_ACTIONABILITY. Reuses product_fit's own
    AMBIGUOUS_PHRASE status (L0's "meaning/intent unclear") rather than a new
    fuzzy rule, so a confidently-classified theme like "quarter zip"
    (THEME_FIT_NEEDS_PRODUCT, not AMBIGUOUS_PHRASE) still resolves to
    BROAD_PARENT/MINE_NICHE, not REVIEW.
SPECIFIC_ACTIONABLE -> execution_action mirrors engine_final_action, except a
    BUILD_NOW resting on market score alone (no EXACT proof) is capped to
    CONFIRM_FIRST for this v1 -- proof plumbing is unverified/near-empty
    right now (2 canonical phrases total, matching nothing in the current
    top-200 slice), so the overlay stays conservative until that's proven
    out live.
BLOCKED/SKIP -> untouched, never computed on, never upgraded.
"""
import re

from src import execution_action_vocab as vocab
from src import product_fit as pf

BUILD_NOW, CONFIRM_FIRST, REVIEW_ACTIONABILITY, MINE_NICHE = (
    "BUILD_NOW", "CONFIRM_FIRST", "REVIEW_ACTIONABILITY", "MINE_NICHE")

_MEDIUM_CATEGORIES = ("audience", "personalization", "motif", "gift")
_MEDIUM_SIGNAL_KEY = {
    "audience": "generic_audience_signal",
    "personalization": "personalization_signal",
    "motif": "interest_or_motif_signal",
    "gift": "generic_gift_signal",
}


def _tokens(kwl):
    return re.findall(r"[a-z0-9]+", kwl)


def _phrase_present(token_list, phrase):
    """True if phrase's words appear as a CONTIGUOUS token sequence -- not a
    raw substring, so 'carry on' does not false-hit inside 'carry onward'."""
    ptoks = phrase.split()
    n = len(ptoks)
    if n == 1:
        return ptoks[0] in token_list
    for i in range(len(token_list) - n + 1):
        if token_list[i:i + n] == ptoks:
            return True
    return False


def _hit_category(token_list, vocab_set):
    return sorted({v for v in vocab_set if _phrase_present(token_list, v)})


def _signals(keyword):
    kwl = (keyword or "").strip().lower()
    toks = _tokens(kwl)

    role = _hit_category(toks, vocab.STRONG_PROFESSION_ROLE)
    occasion = _hit_category(toks, vocab.OCCASION)
    use_case = _hit_category(toks, vocab.USE_CASE)
    audience = _hit_category(toks, vocab.GENERIC_AUDIENCE)
    personalization = _hit_category(toks, vocab.PERSONALIZATION)
    motif = _hit_category(toks, vocab.MOTIF)
    gift = _hit_category(toks, vocab.GENERIC_GIFT)
    weak_mod = _hit_category(toks, vocab.WEAK_GENERIC_MODIFIERS)
    subtype = sorted({s for fam_vocab in vocab.SUBTYPE_BY_FAMILY.values()
                       for s in _hit_category(toks, fam_vocab)})

    return {
        "recipient_or_profession_signal": role,
        "occasion_signal": occasion,
        "use_case_signal": use_case,
        "generic_audience_signal": audience,
        "personalization_signal": personalization,
        "interest_or_motif_signal": motif,
        "generic_gift_signal": gift,
        "specific_product_subtype_signal": subtype,
        "weak_generic_modifiers": weak_mod,
    }


def _specificity(keyword, mode, fit):
    sig = _signals(keyword)
    strong_hit = bool(sig["recipient_or_profession_signal"]
                       or sig["occasion_signal"] or sig["use_case_signal"])
    medium_categories_hit = [c for c in _MEDIUM_CATEGORIES
                              if sig[_MEDIUM_SIGNAL_KEY[c]]]
    combo = len(medium_categories_hit) >= 2

    reason_codes = []
    if strong_hit:
        specificity_class = "SPECIFIC_ACTIONABLE"
        if sig["recipient_or_profession_signal"]:
            reason_codes.append("SPECIFIC_PROFESSION_ROLE")
        if sig["occasion_signal"]:
            reason_codes.append("SPECIFIC_OCCASION_EVENT")
        if sig["use_case_signal"]:
            reason_codes.append("SPECIFIC_USE_CASE")
        if sig["interest_or_motif_signal"]:
            reason_codes.append("SPECIFIC_HOBBY_INTEREST")
        if sig["personalization_signal"]:
            reason_codes.append("SPECIFIC_PERSONALIZATION_CONTEXT")
    elif combo:
        specificity_class = "SPECIFIC_ACTIONABLE"
        reason_codes.append("MEDIUM_SIGNAL_COMBO")
        if "audience" in medium_categories_hit:
            reason_codes.append("GENERIC_AUDIENCE_ONLY")
        if "personalization" in medium_categories_hit:
            reason_codes.append("SPECIFIC_PERSONALIZATION_CONTEXT")
        if "motif" in medium_categories_hit:
            reason_codes.append("SPECIFIC_HOBBY_INTEREST")
        if "gift" in medium_categories_hit:
            reason_codes.append("GENERIC_GIFT_INTENT_ONLY")
    elif fit.get("status") == "AMBIGUOUS_PHRASE":
        specificity_class = "AMBIGUOUS_REVIEW"
        reason_codes.append("AMBIGUOUS_SIGNAL")
    else:
        specificity_class = "BROAD_PARENT"
        if sig["specific_product_subtype_signal"] and not medium_categories_hit and not sig["weak_generic_modifiers"]:
            reason_codes.append("PRODUCT_SUBTYPE_ONLY")
        elif len(medium_categories_hit) == 1:
            reason_codes.append({
                "audience": "GENERIC_AUDIENCE_ONLY",
                "personalization": "PERSONALIZATION_ONLY",
                "motif": "MOTIF_ONLY",  # a broad/generic motif alone -- insufficient
                "gift": "GENERIC_GIFT_INTENT_ONLY",
            }[medium_categories_hit[0]])
        elif sig["weak_generic_modifiers"]:
            reason_codes.append("WEAK_MODIFIERS_ONLY")
        else:
            reason_codes.append("BROAD_GENERIC_PARENT")
        if sig["specific_product_subtype_signal"] and "PRODUCT_SUBTYPE_ONLY" not in reason_codes:
            reason_codes.append("PRODUCT_SUBTYPE_ONLY")

    return specificity_class, reason_codes, sig


def _proof_type(proof):
    if not proof:
        return "NONE"
    m = proof.get("match")
    if m == "exact":
        return "EXACT"
    if m in ("fuzzy", "niche"):
        return "GROUP"
    return "NONE"


def derive_execution_action(row, mode=None):
    """row needs: keyword, action (engine_final_action), proof (optional).

    Returns {execution_action, specificity_class, reason_codes, signals}.
    Never mutates row; never calls out to a DB/API; never upgrades above
    engine_final_action."""
    keyword = row.get("keyword") or ""
    engine_action = row.get("action")

    if engine_action in ("BLOCKED", "SKIP"):
        return {
            "execution_action": engine_action,
            "specificity_class": None,
            "reason_codes": ["ENGINE_ACTION_PRESERVED"],
            "signals": {},
        }

    fit = pf.classify(keyword, mode)
    specificity_class, reason_codes, sig = _specificity(keyword, mode, fit)
    proof_type = _proof_type(row.get("proof"))

    if specificity_class == "BROAD_PARENT":
        execution_action = MINE_NICHE
    elif specificity_class == "AMBIGUOUS_REVIEW":
        execution_action = REVIEW_ACTIONABILITY
    else:  # SPECIFIC_ACTIONABLE
        execution_action = engine_action
        if engine_action == BUILD_NOW:
            if proof_type == "EXACT":
                execution_action = BUILD_NOW
            elif proof_type == "GROUP":
                execution_action = CONFIRM_FIRST
                reason_codes.append("GROUP_PROOF_CAP")
            else:
                execution_action = CONFIRM_FIRST
                reason_codes.append("NO_EXACT_OR_GROUP_PROOF")

    return {
        "execution_action": execution_action,
        "specificity_class": specificity_class,
        "reason_codes": reason_codes,
        "signals": sig,
    }
