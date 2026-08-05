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
    """The fixture pool carries only title/price/shop, so the rich fields are
    genuinely absent and must SAY so rather than render empty."""
    rep = eh.report(QUERY, "embroidery")
    f = rep["fields"]
    for name in ("views", "favorites", "conversion", "revenue", "shop_country"):
        assert f[name] == eh.ABSENT_SERP, name
    for name in ("shop_rating", "image_count"):
        assert "HeyEtsy" in f[name], name
    assert eh.ABSENT_SERP in eh.render_html(rep)


def test_field_availability_is_measured_not_assumed():
    """The PC pool is nearly empty; the VPS carries 109 headers including
    views_24h, he_revenue_usd, country, reviews and age_days. Hardcoding the
    local schema would tell staff a field is unavailable when the server has it
    — a false negative that stops them looking for real data.
    """
    vps_headers = {"title", "price", "shop", "views_24h", "sold_24h",
                   "he_favorites", "conversion_pct", "he_revenue_usd",
                   "country", "reviews", "age_days", "he_tags", "listing_id",
                   "url"}
    got = eh.field_availability(vps_headers)
    for name in ("views", "favorites", "conversion", "revenue", "shop_country",
                 "review_count", "listing_age", "listing_id", "listing_url",
                 "tags", "sold"):
        assert got[name] is True, f"{name} IS captured on the VPS"
    # genuinely absent everywhere in the SERP layer
    assert got["shop_rating"] == eh.ABSENT_DEEP
    assert got["image_count"] == eh.ABSENT_DEEP
    # and an empty pool reports everything absent, never True
    empty = eh.field_availability(set())
    assert not any(v is True for v in empty.values())


def test_capture_fields_reads_the_real_headers(captures):
    got = captures.capture_fields()
    assert {"title", "price", "shop"} <= got
    assert "views_24h" not in got          # not in this fixture pool


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


# --- the DB fast path ---------------------------------------------------------
@pytest.fixture
def db_source(tmp_path, monkeypatch):
    """No raw captures, a populated index — the VPS shape."""
    from src import pattern_miner as pm
    monkeypatch.setattr(pm, "_SEARCH_DIR", tmp_path / "none")
    monkeypatch.setattr(pm, "_IMPORT_DIR", tmp_path / "none2")
    monkeypatch.setattr(pm, "MASTER", tmp_path / "nomaster.csv")
    monkeypatch.setattr(pm, "_from_db", lambda kw: [
        {"title": t, "price": 19.99, "shop": f"Shop{i}", "star": False,
         "ad": False, "freeship": False, "tags": "", "view": kw}
        for i, t in enumerate(REAL)])
    return pm


def _db_report(monkeypatch, version):
    from src import data_store as ds
    monkeypatch.setattr(ds, "matcher_version", lambda: version)
    return eh.report(QUERY, "embroidery")


def test_db_source_reports_rejected_as_not_available(db_source, monkeypatch):
    rep = _db_report(monkeypatch, 2)
    assert rep["source"] == "db"
    assert rep["rejects_observable"] is False
    assert "n/a" in eh.render_html(rep)


def test_db_source_never_prints_a_fake_zero_rejected(db_source, monkeypatch):
    """A 0 would read as 'nothing was off-niche', which the index cannot know."""
    rep = _db_report(monkeypatch, 2)
    html = eh.render_html(rep)
    i = html.find("Rejected")
    assert i > 0
    cell = html[i:i + 220]
    assert ">0<" not in cell, cell


def test_db_source_shows_the_prefiltered_warning(db_source, monkeypatch):
    rep = _db_report(monkeypatch, 2)
    text = " ".join(t for _k, t in rep["warnings"])
    assert "DB pre-filtered source" in text
    assert "rejected rows are not observable" in text
    assert "Rebuild the index after matcher changes" in text


def test_an_index_built_under_an_older_matcher_warns_stale(db_source,
                                                           monkeypatch):
    rep = _db_report(monkeypatch, 1)          # built under the old rule
    assert rep["index_stale"] is True
    text = " ".join(t for _k, t in rep["warnings"])
    assert "Index may be stale" in text and "rebuild required" in text.lower()
    # and it can never be called a strong sample
    assert rep["strength"] == eh.LOW


def test_an_unstamped_index_counts_as_stale(db_source, monkeypatch):
    """PRAGMA user_version defaults to 0 — every index built before the rule was
    versioned reports 0 and must be treated as stale."""
    for missing in (0, None):
        rep = _db_report(monkeypatch, missing)
        assert rep["index_stale"] is True, missing


def test_a_current_index_does_not_warn_stale(db_source, monkeypatch):
    from src import niche_match as nm
    rep = _db_report(monkeypatch, nm.MATCHER_VERSION)
    assert rep["index_stale"] is False
    assert "Index may be stale" not in " ".join(t for _k, t in rep["warnings"])


def test_raw_captures_are_preferred_over_the_prefiltered_index(captures,
                                                               monkeypatch):
    """The index cannot show rejections, so when raw captures exist for this
    keyword the audit must read those instead."""
    monkeypatch.setattr(captures, "_from_db", lambda kw: [
        {"title": "Whatever From The Index", "price": 1.0, "shop": "X",
         "star": False, "ad": False, "freeship": False, "tags": "", "view": kw}])
    rep = eh.report(QUERY, "embroidery")
    assert rep["source"] == "captures"
    assert rep["rejects_observable"] is True
    assert rep["rejected"] == len(CONTAMINANTS)


def test_the_index_path_still_applies_the_niche_filter(monkeypatch):
    """Even on the fast path, Phase 0 must apply — otherwise a populated index
    silently bypasses the whole fix. Exercises the REAL _from_db, so no fixture
    that stubs it may be used here."""
    from src import pattern_miner as pm
    from src import data_store as ds
    monkeypatch.setattr(ds, "listings_for_keyword", lambda kw: [
        {"title": t, "price_usd": 1.0, "shop": "S", "is_star": 0, "is_ad": 0,
         "free_ship": 0, "tags": "", "source_keyword": "mixed capture"}
        for t in REAL + CONTAMINANTS])
    got = [r["title"] for r in pm._from_db(QUERY)]
    assert got, "the fixture returned nothing — the test proves nothing"
    for bad in CONTAMINANTS:
        assert bad not in got, bad
    for good in REAL:
        assert good in got


def test_data_store_search_selection_uses_the_shared_rule():
    """_kw_match was a FOURTH copy of the old shared-token rule, so a populated
    index bypassed Phase 0 entirely — load_batch tries it first."""
    from src import data_store as ds
    qt = ds._toks(QUERY)
    assert ds._kw_match(qt, "personalized halloween shirt", QUERY) is True
    assert ds._kw_match(qt, "personalized teacher shirt", QUERY) is False
    assert ds._kw_match(qt, "personalized dog mom shirt", QUERY) is False


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
