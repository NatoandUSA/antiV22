"""listing_factory must never invent tags, price, or supplier facts it
doesn't have evidence for -- see current_code_issues_to_fix in the
2026-08-16 workflow-reset handoff. These tests lock in the honest-gap
behavior instead of the old fabrication."""
import pytest
from src import listing_factory as lf


def _no_tm_risk(monkeypatch):
    monkeypatch.setattr(lf, "tm_check", lambda kw: ("OK", ""))


def test_no_tag_padding_when_evidence_is_thin(monkeypatch):
    """Old code padded short tag lists with 'custom <word>'/'<word> gift'.
    New code leaves the list short -- the gap is surfaced, not invented."""
    _no_tm_risk(monkeypatch)
    monkeypatch.setattr(lf, "suggestions", lambda kw: [])
    monkeypatch.setattr(lf, "top_listings", lambda kw: [])
    p = lf.build_listing("grandpa golf shirt")
    assert len(p["tags"]) < 13
    assert not any(t.startswith("custom ") or t.endswith(" gift") for t in p["tags"])


def test_no_synthetic_price_without_evidence_or_costs(monkeypatch):
    """No competitor price and no supplier cost data -> DATA UNAVAILABLE
    (None), never the old $20-assumed-price fallback."""
    _no_tm_risk(monkeypatch)
    monkeypatch.setattr(lf, "suggestions", lambda kw: [])
    monkeypatch.setattr(lf, "top_listings", lambda kw: [])
    monkeypatch.setattr(lf, "load_costs", lambda: {})
    p = lf.build_listing("grandpa golf shirt")
    assert p["price"] is None
    assert p["margin"] is None


def test_real_cost_data_still_prices_without_competitor_evidence(monkeypatch):
    """No competitor price, but real supplier cost data for the cluster ->
    a real cost-plus-margin price, not DATA UNAVAILABLE and not $20-based."""
    _no_tm_risk(monkeypatch)
    monkeypatch.setattr(lf, "suggestions", lambda kw: [])
    monkeypatch.setattr(lf, "top_listings", lambda kw: [])
    monkeypatch.setattr(lf, "cluster_of", lambda kw: "bag")
    monkeypatch.setattr(lf, "load_costs", lambda: {"bag": (5.0, 4.0, "AcmeSupply")})
    p = lf.build_listing("bridesmaid bag")
    assert p["price"] is not None
    assert p["margin"] == 6.0
    assert p["supplier"] == "AcmeSupply"


def test_competitor_price_path_unchanged(monkeypatch):
    """Regression check: real competitor price evidence still drives price
    the same way it did before (avg * 1.15), untouched by this fix."""
    _no_tm_risk(monkeypatch)
    monkeypatch.setattr(lf, "suggestions", lambda kw: [])
    monkeypatch.setattr(
        lf, "top_listings",
        lambda kw: [{"title": "bridesmaid bag", "price_usd": 20.0,
                     "listing_id": "1", "total_sold": 10}],
    )
    monkeypatch.setattr(lf, "load_costs", lambda: {})
    p = lf.build_listing("bridesmaid bag")
    assert p["avg_price"] == 20.0
    assert p["price"] == round(20.0 * 1.15, 2)


@pytest.fixture
def _pack_text(tmp_path, monkeypatch):
    def _make(p):
        monkeypatch.chdir(tmp_path)
        path = lf.write_pack(p)
        return path.read_text(encoding="utf-8")
    return _make


def test_description_never_blocked_and_owner_check_shown(monkeypatch, _pack_text):
    _no_tm_risk(monkeypatch)
    monkeypatch.setattr(lf, "suggestions", lambda kw: [])
    monkeypatch.setattr(lf, "top_listings", lambda kw: [])
    monkeypatch.setattr(lf, "load_costs", lambda: {})
    monkeypatch.setattr("src.supplier_pull.best_record_for", lambda kw: None)

    p = lf.build_listing("grandpa golf shirt")
    text = _pack_text(p)

    assert "LISTING COPY BLOCKED" not in text
    assert "DESCRIPTION (dan vao o Description)" in text
    assert "made to order just for you" in text
    assert "OWNER CHECK - them DETAILS" in text
    assert "material, size, processing time" in text


def test_description_appends_real_details_when_supplier_data_exists(monkeypatch, _pack_text):
    _no_tm_risk(monkeypatch)
    monkeypatch.setattr(lf, "suggestions", lambda kw: [])
    monkeypatch.setattr(lf, "top_listings", lambda kw: [])
    monkeypatch.setattr(lf, "load_costs", lambda: {})
    monkeypatch.setattr(
        "src.supplier_pull.best_record_for",
        lambda kw: [{"material": "100% Cotton", "available_sizes": "S-XL",
                     "processing_time": "2-3 days"}],
    )

    p = lf.build_listing("grandpa golf shirt")
    text = _pack_text(p)

    assert "OWNER CHECK - them DETAILS" not in text
    assert "THEM VAO CUOI DESCRIPTION" in text
    assert "100% Cotton" in text
    assert "2-3 days" in text


def test_no_price_renders_data_unavailable_not_dollar_none(monkeypatch, _pack_text):
    _no_tm_risk(monkeypatch)
    monkeypatch.setattr(lf, "suggestions", lambda kw: [])
    monkeypatch.setattr(lf, "top_listings", lambda kw: [])
    monkeypatch.setattr(lf, "load_costs", lambda: {})
    monkeypatch.setattr("src.supplier_pull.best_record_for", lambda kw: None)

    p = lf.build_listing("grandpa golf shirt")
    text = _pack_text(p)

    assert "$None" not in text
    assert "DATA UNAVAILABLE - OWNER CHECK" in text
