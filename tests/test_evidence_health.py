"""Evidence Health panel — what the Pattern Miner analysis rests on.

The panel exists because "Mined the 385 listings matching X (of 385 captured,
across 227 shops)" hid two different questions: how many listings survived the
niche matcher, and how thin the deep-evidence lanes underneath it really were
(six opened listings out of 385, spoken about as a measured rate).
"""
import json

import pytest

from src import evidence_health as eh
from src import niche_match as nm

QUERY = "personalized embroidery halloween shirt"

REAL = [
    "Personalized Halloween Embroidered Sweatshirt, Ghost Dog Crewneck",
    "Embroidered Ghost Dog Sweatshirt Halloween",
    "Custom Embroidered Halloween Shirt",
    "Personalized Boo Embroidered Shirt Halloween",
]
CONTAMINANTS = [
    "Personalized Teacher Shirt, Comfort Colors Back to School Tee",
    "Teacher Appreciation Shirt Personalized Name Gift",
    "Personalized Dog Mom Shirt Custom Name",
    "Personalized Bride Shirt, Fiancee Gift, Engagement Tee",
]


@pytest.fixture
def captures(tmp_path, monkeypatch):
    """A capture pool holding BOTH niches, the way the real one does."""
    from src import pattern_miner as pm
    d = tmp_path / "etsy_search"
    d.mkdir()
    rows = [[t, "19.99", f"Shop{i % 3}", "", "", ""]
            for i, t in enumerate(REAL + CONTAMINANTS)]
    (d / "capture.json").write_text(json.dumps({
        "view": "etsy mixed capture",
        "headers": ["title", "price", "shop", "star", "ad", "free shipping"],
        "rows": rows}), encoding="utf-8")
    monkeypatch.setattr(pm, "_SEARCH_DIR", d)
    monkeypatch.setattr(pm, "_IMPORT_DIR", tmp_path / "nope")
    monkeypatch.setattr(pm, "_from_db", lambda kw: [])
    monkeypatch.setattr(pm, "MASTER", tmp_path / "nomaster.csv")
    return pm


@pytest.fixture
def thin_detail(monkeypatch):
    """The real shape: a handful of opened listings behind a big SERP set."""
    from src import feed_evidence_router as fer
    monkeypatch.setattr(fer, "structure_for_keyword", lambda kw, **k: {
        "has_structure": True, "listings": 1, "avg_image_count": 20.0,
        "top_tags": [("bride shirt", 2)]})
    monkeypatch.setattr(fer, "evidence_for_keyword", lambda kw, **k: {
        "has_evidence": True, "listings": [{"id": "1"}],
        "note": "listing evidence is capped; single-listing = CONFIRM_FIRST max."})


# --- 1. captured vs matched vs rejected ---------------------------------------
def test_it_shows_captured_matched_and_rejected(captures):
    rep = eh.report(QUERY, "embroidery")
    assert rep["captured"] == len(REAL) + len(CONTAMINANTS)
    assert rep["matched"] == len(REAL)
    assert rep["rejected"] == len(CONTAMINANTS)
    assert rep["match_rate"] == 50
    assert rep["rejects_observable"] is True


def test_staff_can_see_why_the_captured_set_shrank(captures):
    """The whole point: 8 captured became 4, and the panel says which reason."""
    rep = eh.report(QUERY, "embroidery")
    assert rep["reasons"]["rejected_missing_theme"] == len(CONTAMINANTS)
    assert sum(rep["reasons"].values()) == rep["captured"]


def test_unique_shops_counts_matched_listings_only(captures):
    rep = eh.report(QUERY, "embroidery")
    assert 0 < rep["shops"] <= len(REAL)


# --- 2. the contaminants are visibly rejected ---------------------------------
def test_the_mixed_fixture_rejects_teacher_bride_and_dog_mom(captures):
    from src import pattern_miner as pm
    a = pm.audit(QUERY)
    kept = [r["title"] for r in a["matched_rows"]]
    for bad in CONTAMINANTS:
        assert bad not in kept
    for good in REAL:
        assert good in kept


# --- 3. the mined summary is clean --------------------------------------------
def test_top_words_has_no_teacher_or_school(captures):
    res = captures.mine(QUERY)
    words = {w for w, _p in res["top_words"]}
    assert "teacher" not in words and "school" not in words


# --- 4. reasons come from why(), not a private copy ---------------------------
def test_the_panel_uses_the_matchers_own_reasons(captures):
    rep = eh.report(QUERY, "embroidery")
    vocab = set()
    for t in REAL + CONTAMINANTS:
        vocab.add(nm.why(t, QUERY)[1])
    # every reason the panel reports is one why() can produce
    assert set(rep["reasons"]) <= vocab | {"serp_view"}
    assert "rejected_missing_theme" in rep["reasons"]


def test_the_panel_cannot_disagree_with_the_batch_it_describes(captures):
    """Panel and miner must read the same filtering, or the panel lies."""
    rep = eh.report(QUERY, "embroidery")
    _kw, batch, matched, _scanned = captures.load_batch(QUERY)
    assert rep["matched"] == matched == len(batch)


# --- 5. missing fields say so ---------------------------------------------
def test_uncaptured_fields_are_named_never_blank_or_invented(captures):
    rep = eh.report(QUERY, "embroidery")
    nc = rep["not_captured"]
    for f in ("views", "favorites", "conversion", "revenue", "shop_country"):
        assert nc[f] == "Not captured in SERP data", f
    for f in ("shop_rating", "review_count", "image_count", "listing_age"):
        assert "HeyEtsy" in nc[f], f
    html = eh.render_html(rep)
    assert "Not captured in SERP data" in html
    # and never rendered as a zero, which would read as a measurement
    assert ">views<" not in html or "0" not in nc["views"]


def test_absent_capture_dates_render_as_not_captured(captures, monkeypatch):
    rep = eh.report(QUERY, "embroidery")
    rep["newest"] = rep["oldest"] = None
    assert "not captured" in eh.render_html(rep)


# --- 6. low detail coverage ---------------------------------------------------
@pytest.fixture
def big_captures(tmp_path, monkeypatch):
    """The real ratio: a large SERP set behind a handful of opened listings.
    6 of 385 is 1.6% — the 4-row fixture above is 25% and correctly does NOT
    warn, so the warning has to be tested at a realistic shape."""
    from src import pattern_miner as pm
    d = tmp_path / "etsy_search"
    d.mkdir()
    rows = [[f"Personalized Halloween Embroidered Shirt Design {i}",
             "19.99", f"Shop{i % 30}", "", "", ""] for i in range(60)]
    (d / "big.json").write_text(json.dumps({
        "view": "etsy big capture",
        "headers": ["title", "price", "shop", "star", "ad", "free shipping"],
        "rows": rows}), encoding="utf-8")
    monkeypatch.setattr(pm, "_SEARCH_DIR", d)
    monkeypatch.setattr(pm, "_IMPORT_DIR", tmp_path / "nope")
    monkeypatch.setattr(pm, "_from_db", lambda kw: [])
    monkeypatch.setattr(pm, "MASTER", tmp_path / "nomaster.csv")
    return pm


def test_low_detail_coverage_warns(big_captures, thin_detail):
    rep = eh.report(QUERY, "embroidery")
    assert rep["matched"] == 60 and rep["opened"] == 1
    kinds = {k for k, _t in rep["warnings"]}
    assert "detail" in kinds, rep["warnings"]
    text = " ".join(t for _k, t in rep["warnings"])
    assert "opened listing" in text


def test_healthy_detail_coverage_does_not_warn(captures, thin_detail):
    """1 opened behind 4 matched is 25% — not low. A warning that fires on good
    coverage teaches staff to ignore the panel."""
    rep = eh.report(QUERY, "embroidery")
    assert "detail" not in {k for k, _t in rep["warnings"]}


def test_the_single_listing_cap_is_stated(captures, thin_detail):
    rep = eh.report(QUERY, "embroidery")
    text = " ".join(t for _k, t in rep["warnings"])
    assert "CONFIRM_FIRST" in text


# --- 7. reviews never move the market score -----------------------------------
def test_review_evidence_warning_says_it_does_not_change_market_score(
        captures, thin_detail):
    rep = eh.report(QUERY, "embroidery")
    text = " ".join(t for _k, t in rep["warnings"])
    assert "does not change the market score" in text
    assert "does not automatically change market score" in rep["why_it_matters"]


def test_the_panel_separates_the_source_layers(captures, thin_detail):
    html = eh.render_html(eh.report(QUERY, "embroidery"))
    assert "SERP capture layer" in html
    assert "Opened listing / HeyEtsy / review layers" in html


# --- strength labels ----------------------------------------------------------
def test_strength_label_is_one_of_the_agreed_five(captures):
    assert eh.report(QUERY, "embroidery")["strength"] in {
        eh.STRONG, eh.DIRECTIONAL, eh.WEAK_DETAIL, eh.MIXED, eh.LOW}


def test_a_tiny_sample_is_not_called_a_strong_broad_sample(captures):
    """4 matched listings is directional at best."""
    assert eh.report(QUERY, "embroidery")["strength"] != eh.STRONG


def test_a_two_theme_keyword_raises_the_mixed_cluster_warning(captures):
    rep = eh.report("halloween teacher shirt", "pod")
    assert {k for k, _t in rep["warnings"]} & {"mixed"} or rep["matched"] == 0


def test_no_keyword_renders_nothing_rather_than_an_empty_panel():
    assert eh.render_html(eh.report("", None)) == ""
    assert eh.report(None)["strength"] == eh.LOW


# --- 8/9. guardrails ----------------------------------------------------------
def test_no_frozen_files_changed():
    from tests.test_feasibility_gate import FROZEN_BASELINE
    import hashlib
    from pathlib import Path
    for name, want in FROZEN_BASELINE.items():
        raw = Path(f"src/{name}.py").read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == want, name


def test_publish_automation_remains_false():
    from src.team_ops import PUBLISH_AUTOMATION
    assert PUBLISH_AUTOMATION is False


def test_the_panel_imports_no_frozen_module():
    import ast
    from pathlib import Path
    tree = ast.parse(Path("src/evidence_health.py").read_text(encoding="utf-8"))
    frozen = {"ranking_engine", "opportunity_score", "product_fit", "etsy_proof",
              "opportunity_inbox"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[-1] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported |= {a.name.split(".")[-1] for a in node.names}
            imported |= {(node.module or "").split(".")[-1]}
    assert not (imported & frozen), sorted(imported & frozen)


def test_the_panel_changes_no_score_or_action(captures):
    """Display only. Mining the same keyword with and without the panel must
    produce an identical result dict."""
    before = captures.mine(QUERY)
    eh.report(QUERY, "embroidery")
    after = captures.mine(QUERY)
    assert before == after
