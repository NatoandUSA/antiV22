"""V37.5 Phase B — loop-verified exact-keyword proof (behind a default-OFF flag).

Full path: capture (Phase A lane) -> exact_proof_from_loop -> build_proof merge ->
proof_for (match='exact') -> decide(). Frozen decide() is NOT modified.

engine_config reads config/engine.json by an ABSOLUTE path off its module location,
so tests point that path at the sandbox via monkeypatch before writing the flag.
"""
import json
from pathlib import Path

from src import feed_evidence_router as fer
from src import etsy_proof as ep
from src import ranking_engine as reng
from src import engine_config as ec


HDR = ["listing_id", "title", "shop", "he_sold", "price", "tags", "promoted"]


def _cfg(monkeypatch, **kw):
    """Write config/engine.json into the sandbox and make engine_config read it."""
    p = Path("config/engine.json").resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(kw))
    monkeypatch.setattr(ec, "_PATH", p)
    ec._cache = None
    ec._cache_mtime = None


def _multishop_rows():
    # 3 exact selling across 3 shops (245 lifetime sold => PROVEN) + noise
    return [
        ["101", "Personalized Birthday Age Shirt for Kids", "ShopA", "120", "19", "birthday shirt", ""],
        ["102", "Custom Personalized Birthday Age Shirt", "ShopB", "80", "21", "birthday", ""],
        ["103", "Personalized Birthday Age Shirt Gift", "ShopC", "45", "18", "kids", ""],
        ["104", "Birthday Shirt", "ShopD", "999", "15", "birthday", ""],           # group-only
        ["105", "Personalized Birthday Age Shirt", "ShopE", "300", "20", "", "promoted"],  # ad
        ["106", "Personalized Birthday Age Shirt", "ShopF", "0", "20", "", ""],     # unsold
    ]


def _decide(kw, market="WATCH"):
    pm = ep.build_proof()
    p = ep.proof_for(kw, pm)
    return reng.decide(kw, market, proof=p), p


def test_flag_off_zero_effect(sandbox, monkeypatch):
    _cfg(monkeypatch, exact_loop_proof_enabled=False)
    fer.record_focus_evidence("personalized birthday age shirt", HDR, _multishop_rows())
    d, p = _decide("personalized birthday age shirt")
    assert p is None                       # lane ignored while flag off
    assert d["action"] == "WATCH"


def test_exact_multishop_selling_builds(sandbox, monkeypatch):
    _cfg(monkeypatch, exact_loop_proof_enabled=True)
    fer.record_focus_evidence("personalized birthday age shirt", HDR, _multishop_rows())
    d, p = _decide("personalized birthday age shirt")
    assert p is not None and p["match"] == "exact" and p["source"] == "loop"
    assert p["verdict"] == "PROVEN_WINNER" and p["shops"] == 3
    assert d["action"] == "BUILD_NOW" and d["proof_tier"] == 0


def test_exact_proof_promotes_long_tail(sandbox, monkeypatch):
    _cfg(monkeypatch, exact_loop_proof_enabled=True)
    fer.record_focus_evidence("personalized birthday age shirt", HDR, _multishop_rows())
    d, _ = _decide("personalized birthday age shirt")
    assert d["action"] == "BUILD_NOW"


def test_single_shop_caps_confirm_first(sandbox, monkeypatch):
    _cfg(monkeypatch, exact_loop_proof_enabled=True)
    rows = [
        ["201", "Personalized Nurse Sweatshirt Embroidered", "OneShop", "300", "39", "nurse", ""],
        ["202", "Personalized Nurse Sweatshirt Embroidered Gift", "OneShop", "80", "39", "nurse", ""],
        ["203", "Personalized Nurse Sweatshirt Embroidered Cute", "OneShop", "60", "39", "nurse", ""],
        ["204", "Nurse Shirt", "ShopX", "500", "20", "nurse", ""],       # group-only
        ["205", "Personalized Nurse Sweatshirt Embroidered", "OneShop", "40", "39", "nurse", ""],
    ]
    fer.record_focus_evidence("personalized nurse sweatshirt embroidered", HDR, rows)
    d, p = _decide("personalized nurse sweatshirt embroidered")
    assert p is not None and p["proof_scope"] == "EXACT_SINGLE_SHOP"
    assert p["verdict"] == "SELLING"
    assert d["action"] == "CONFIRM_FIRST"


def test_group_only_pull_no_exact_proof(sandbox, monkeypatch):
    _cfg(monkeypatch, exact_loop_proof_enabled=True)
    rows = [["301", "Birthday Shirt", "ShopA", "700", "15", "birthday", ""],
            ["302", "Cute Birthday Shirt", "ShopB", "400", "16", "birthday", ""],
            ["303", "Funny Birthday Shirt", "ShopC", "300", "16", "birthday", ""],
            ["304", "Birthday Shirt Gift", "ShopD", "200", "16", "birthday", ""],
            ["305", "Soft Birthday Shirt", "ShopE", "150", "16", "birthday", ""]]
    fer.record_focus_evidence("personalized birthday age shirt", HDR, rows)
    d, p = _decide("personalized birthday age shirt")
    assert p is None                       # nothing matched the EXACT keyword
    assert d["action"] == "WATCH"


def test_ads_and_unsold_excluded(sandbox, monkeypatch):
    _cfg(monkeypatch, exact_loop_proof_enabled=True)
    rows = [
        ["401", "Personalized Teacher Tote Bag", "A", "0", "20", "teacher", ""],       # unsold
        ["402", "Personalized Teacher Tote Bag", "B", "500", "20", "teacher", "promoted"],  # ad
        ["403", "Personalized Teacher Tote Bag", "C", "500", "20", "teacher", "promoted"],  # ad
        ["404", "Teacher Bag", "D", "999", "20", "teacher", ""],                        # group
        ["405", "Teacher Bag Cute", "E", "999", "20", "teacher", ""],                   # group
    ]
    fer.record_focus_evidence("personalized teacher tote bag", HDR, rows)
    _, p = _decide("personalized teacher tote bag")
    assert p is None                       # 0 exact+selling+organic listings


def test_stale_pull_downgrades_to_confirm(sandbox, monkeypatch):
    _cfg(monkeypatch, exact_loop_proof_enabled=True, exact_proof_expire_days=45)
    fer.record_focus_evidence("personalized birthday age shirt", HDR, _multishop_rows())
    slug = fer._kw_slug(fer._canon_kw("personalized birthday age shirt"))
    fp = Path("data/imports/etsy_exact_proof") / f"{slug}.json"
    obj = json.loads(fp.read_text())
    obj["collected_at"] = "2020-01-01"
    fp.write_text(json.dumps(obj))
    d, p = _decide("personalized birthday age shirt")
    assert p is not None and p["stale"] is True
    assert p["verdict"] == "SELLING" and d["action"] == "CONFIRM_FIRST"


def test_hard_gate_beats_loop_proof(sandbox, monkeypatch):
    _cfg(monkeypatch, exact_loop_proof_enabled=True)
    rows = [["501", "Disney Princess Shirt Personalized", "A", "300", "20", "disney", ""],
            ["502", "Disney Princess Shirt Personalized Gift", "B", "200", "20", "disney", ""],
            ["503", "Disney Princess Shirt Personalized Cute", "C", "100", "20", "disney", ""],
            ["504", "Disney Princess Shirt", "D", "500", "20", "disney", ""],
            ["505", "Disney Princess Shirt Personalized", "E", "90", "20", "disney", ""]]
    fer.record_focus_evidence("disney princess shirt personalized", HDR, rows)
    d, _ = _decide("disney princess shirt personalized")
    assert d["action"] in ("BLOCKED", "SKIP")   # hard gate wins over any proof
