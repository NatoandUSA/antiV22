"""Etsy Proof lane (L1): parsing, aggregation, verdicts, fuzzy-match guard."""
from pathlib import Path

from src import etsy_proof as ep

HDR_FULL = ["Title", "Shop", "Price", "Age", "Reviews", "Sales", "Revenue"]
HDR_NOSHOP = ["Title", "Price", "Age", "Reviews", "Sales", "Revenue"]


def _proof(hdr, data):
    """Build proof from ONLY this fixture: the capture lane (data/imports/
    etsy_spy) also feeds build_proof now, so isolate it during the test."""
    ep.save_export(hdr, data, None, "test")
    saved = ep.CAPTURE_DIR
    ep.CAPTURE_DIR = Path("data/imports/_no_such_dir_for_tests")
    try:
        return ep.build_proof()
    finally:
        ep.CAPTURE_DIR = saved


def test_num_parsing_handles_currency_k_and_locked():
    assert ep._num("1.2k") == 1200
    assert ep._num("$3,600,000") == 3600000
    assert ep._num("locked") is None
    assert ep._num("") is None


def test_age_parsing_formats():
    assert ep._age_months("3y 4m") == 40
    assert ep._age_months("140 Mo.") == 140
    assert ep._age_months("18 months") == 18
    assert ep._age_months("") is None


def test_proven_needs_real_shop_spread():
    # No shop column -> spread unknown -> can NEVER be PROVEN, and the evidence
    # must say "listing(s)", not fabricated "shop(s)".
    pm = _proof(HDR_NOSHOP, [
        ["Custom Nurse Embroidered Sweatshirt", "39", "8m", "120", "200", "8000"],
        ["Nurse RN Embroidered Sweatshirt", "42", "5m", "64", "300", "12600"]])
    p = ep.proof_for("nurse embroidered sweatshirt", pm)
    assert p is not None
    assert p["verdict"] != "PROVEN_WINNER"
    assert "listing(s)" in p["evidence"]


def test_proven_with_shops_and_strong_seller_tier():
    pm = _proof(HDR_FULL, [
        ["Custom Nurse Embroidered Sweatshirt", "A", "39", "8m", "120", "200", "8000"],
        ["Nurse RN Embroidered Sweatshirt", "B", "42", "5m", "64", "300", "12600"],
        ["Dog Mom Embroidered Sweatshirt", "C", "40", "6m", "30", "25", "1000"],
        ["Dog Mom Custom Embroidered Sweatshirt", "D", "41", "7m", "20", "10", "400"]])
    nurse = ep.proof_for("nurse embroidered sweatshirt", pm)
    assert nurse["verdict"] == "PROVEN_WINNER"       # 500 sold across 2 shops
    dog = ep.proof_for("dog mom embroidered sweatshirt", pm)
    assert dog["verdict"] == "STRONG_SELLER"          # 35 sold across 2 shops


def test_fuzzy_guard_generic_cannot_hijack_niche():
    pm = _proof(HDR_FULL, [
        ["Custom Nurse Embroidered Sweatshirt", "A", "39", "8m", "120", "200", "8000"],
        ["Nurse RN Embroidered Sweatshirt", "B", "42", "5m", "64", "300", "12600"]])
    assert ep.proof_for("embroidered sweatshirt", pm) is None      # no subject
    assert ep.proof_for("custom sweatshirt", pm) is None           # generic only
    assert ep.proof_for("teacher embroidered sweatshirt", pm) is None  # wrong niche


def test_fuzzy_match_carries_confidence():
    pm = _proof(HDR_FULL, [
        ["Custom Nurse Embroidered Sweatshirt", "A", "39", "8m", "120", "200", "8000"],
        ["Nurse RN Embroidered Sweatshirt", "B", "42", "5m", "64", "300", "12600"]])
    p = ep.proof_for("personalized nurse sweatshirt", pm)
    assert p is not None
    assert p["match"] in ("exact", "fuzzy")
    assert 0 < p["match_confidence"] <= 1.0


def test_renormalization_without_shop_and_age():
    # only Title+Sales+Revenue: spread + young must be EXCLUDED (renormalised),
    # not paid out as a uniform bonus.
    pm = _proof(["Title", "Sales", "Revenue"], [
        ["Custom Nurse Embroidered Sweatshirt", "200", "8000"],
        ["Dog Mom Embroidered Sweatshirt", "10", "400"]])
    scores = sorted(p["score"] for p in pm.values())
    # the weaker niche must not be floated by absent-component bonuses
    assert scores[0] < 60
