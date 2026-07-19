"""Layered ranking engine (L0 gate -> L1 proof -> L2 market -> L4 action) tests."""
from src import ranking_engine as re_eng


def test_trademark_is_blocked_even_with_go():
    r = re_eng.decide("disney nurse shirt", "GO")
    assert r["action"] == "BLOCKED"


def test_policy_risk_caps_at_review():
    r = re_eng.decide("spirit guide", "GO")
    assert r["action"] in ("REVIEW", "WATCH")   # policy gate, never BUILD
    assert r["action"] != "BUILD_NOW"


def test_bare_category_routes_to_pattern_miner():
    r = re_eng.decide("custom shirt kids", "GO")
    assert r["action"] == "CONFIRM_FIRST"
    assert r["route"] == "pattern"


def test_short_tail_two_words_never_builds_on_heuristics():
    r = re_eng.decide("summer pouch", "GO")
    assert r["action"] == "CONFIRM_FIRST"
    assert "short-tail" in r["reason"]


def test_three_words_is_borderline_not_build():
    # owner's rule: long-tail = MORE than 3 words; 3-word terms are borderline
    r = re_eng.decide("patriotic soft tee", "GO")
    assert r["action"] == "CONFIRM_FIRST"
    assert "borderline" in r["reason"]


def test_four_plus_words_with_angle_can_build():
    r = re_eng.decide("personalized dinosaur birthday shirt kids", "GO")
    assert r["action"] == "BUILD_NOW"
    assert "long-tail" in r["reason"]


def test_exact_proven_proof_overrides_short_tail():
    proof = {"verdict": "PROVEN_WINNER", "evidence": "1400 sold",
             "match": "exact", "match_confidence": 1.0}
    r = re_eng.decide("summer pouch", "GO", proof=proof)
    assert r["action"] == "BUILD_NOW"
    assert r["proof_tier"] == 0


def test_medium_confidence_fuzzy_proof_cannot_grant_build():
    # medium-confidence fuzzy proof must NOT unlock the PROVEN->BUILD override
    # (a short-tail term stays capped at CONFIRM_FIRST)...
    proof = {"verdict": "PROVEN_WINNER", "evidence": "1400 sold",
             "match": "fuzzy", "match_confidence": 0.4}
    r = re_eng.decide("summer pouch", "GO", proof=proof)
    assert r["action"] == "CONFIRM_FIRST"
    assert r["proof_tier"] == 1
    # ...but proof never DEMOTES an action earned on market merit (raise-only).
    r2 = re_eng.decide("personalized dinosaur birthday shirt kids", "GO",
                       proof=proof)
    assert r2["action"] == "BUILD_NOW"


def test_strong_seller_forces_at_least_confirm():
    proof = {"verdict": "STRONG_SELLER", "evidence": "25 sold - 2 shops",
             "match": "exact", "match_confidence": 1.0}
    r = re_eng.decide("personalized dinosaur birthday shirt kids", "WATCH",
                      proof=proof)
    assert r["action"] == "CONFIRM_FIRST"


def test_hard_gate_beats_proof():
    proof = {"verdict": "PROVEN_WINNER", "evidence": "9999 sold",
             "match": "exact", "match_confidence": 1.0}
    r = re_eng.decide("disney nurse shirt", "GO", proof=proof)
    assert r["action"] == "BLOCKED"   # selling a trademarked item is still blocked
