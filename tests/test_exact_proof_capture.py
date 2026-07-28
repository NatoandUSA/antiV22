"""V37.5 Phase A — exact-keyword loop-evidence capture lane (capture only).

These verify the capture is honest and that it has ZERO ranking effect: it writes
to its own data/imports/etsy_exact_proof lane and never touches build_proof.
"""
import json
from pathlib import Path

from src import feed_evidence_router as fer
from src import engine_config as ec


HEADERS = ["listing_id", "title", "shop", "he_sold", "price", "tags", "promoted"]


def _flag_off(monkeypatch):
    """Pin exact_loop_proof_enabled OFF for this test, regardless of the committed
    config default (engine_config reads config/engine.json by absolute path)."""
    p = Path("config/engine.json").resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"exact_loop_proof_enabled": False}))
    monkeypatch.setattr(ec, "_PATH", p)
    ec._cache = None
    ec._cache_mtime = None


def _rows():
    # 3 exact-matching selling listings across 3 shops + 1 group-only + 1 ad + 1 unsold
    return [
        ["101", "Personalized Birthday Age Shirt for Kids", "ShopA", "120", "19.99", "birthday shirt", ""],
        ["102", "Custom Personalized Birthday Age Shirt", "ShopB", "80", "21.00", "birthday", ""],
        ["103", "Personalized Birthday Age Shirt Gift", "ShopC", "45", "18.50", "kids birthday", ""],
        ["104", "Birthday Shirt", "ShopD", "999", "15.00", "birthday", ""],          # group-only (no 'personalized'/'age')
        ["105", "Personalized Birthday Age Shirt", "ShopE", "300", "20.00", "", "promoted"],  # exact but an AD
        ["106", "Personalized Birthday Age Shirt", "ShopF", "0", "20.00", "", ""],    # exact but NOT selling
    ]


def test_capture_records_exact_and_flags_correctly(sandbox):
    fer.record_focus_evidence("personalized birthday age shirt", HEADERS, _rows(),
                              source_hint="etsy-search")
    ev = fer.load_focus_evidence("personalized birthday age shirt")
    assert ev is not None
    by_id = {l["listing_id"]: l for l in ev["listings"]}
    assert by_id["101"]["exact_match"] and by_id["101"]["selling"]
    assert by_id["104"]["exact_match"] is False        # group-only, missing tokens
    assert by_id["105"]["is_ad"] is True               # ad detected
    assert by_id["106"]["selling"] is False            # zero sold


def test_summary_meets_bar_multishop(sandbox):
    fer.record_focus_evidence("personalized birthday age shirt", HEADERS, _rows())
    s = fer.focus_evidence_summary("personalized birthday age shirt")
    # 101/102/103 qualify (exact + selling + organic) across 3 shops; 104 group-only,
    # 105 ad, 106 unsold are all excluded.
    assert s["exact_selling_listings"] == 3
    assert s["distinct_shops"] == 3
    assert s["meets_exact_bar"] is True
    assert s["would_be_scope"] == "EXACT_MULTISHOP"
    assert s["affects_rank"] is False


def test_single_shop_does_not_meet_bar(sandbox):
    rows = [
        ["201", "Personalized Nurse Sweatshirt Embroidered", "OneShop", "500", "39", "nurse", ""],
        ["202", "Personalized Nurse Sweatshirt Embroidered Gift", "OneShop", "60", "39", "nurse", ""],
    ]
    hdr = ["listing_id", "title", "shop", "he_sold", "price", "tags", "promoted"]
    fer.record_focus_evidence("personalized nurse sweatshirt embroidered", hdr, rows)
    s = fer.focus_evidence_summary("personalized nurse sweatshirt embroidered")
    assert s["distinct_shops"] == 1
    assert s["meets_exact_bar"] is False
    assert s["would_be_scope"] == "EXACT_SINGLE_SHOP"


def test_group_only_pull_scores_group_scope(sandbox):
    rows = [["301", "Birthday Shirt", "ShopA", "700", "15", "birthday", ""],
            ["302", "Cute Birthday Shirt", "ShopB", "400", "16", "birthday", ""]]
    hdr = ["listing_id", "title", "shop", "he_sold", "price", "tags", "promoted"]
    fer.record_focus_evidence("personalized birthday age shirt", hdr, rows)
    s = fer.focus_evidence_summary("personalized birthday age shirt")
    assert s["exact_selling_listings"] == 0
    assert s["would_be_scope"] == "GROUP_ONLY"


def test_capture_has_zero_ranking_effect_when_phase_b_off(sandbox, monkeypatch):
    # With Phase B OFF, the capture lane is NOT a proof source: build_proof must be
    # identical before and after a capture. (With the flag ON — the committed
    # default — the capture DOES feed ranking; that path is covered in
    # test_exact_proof_loop.py.)
    _flag_off(monkeypatch)
    from src import etsy_proof as ep
    before = ep.build_proof()
    fer.record_focus_evidence("personalized birthday age shirt", HEADERS, _rows())
    after = ep.build_proof()
    assert before == after
