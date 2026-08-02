"""Composite Opportunity Score - honest-nulls + verdict integrity tests."""
from src import opportunity_score as osc


def _strong():
    return {"tag": "nurse graduation gift", "momentum_score": 80,
            "avg_conversion_rate": 0.05, "demand": 85,
            "competition_level": "low", "opportunity_score": 86}


def test_strong_row_scores_go():
    s = osc.score(_strong())
    assert s["overall_score"] is not None
    assert s["verdict"] in ("GO", "CONDITIONAL")


def test_empty_row_is_watch_not_fabricated():
    # no market/competition/opportunity data at all -> cannot be a confident GO
    s = osc.score({"tag": "something"})
    assert s["verdict"] == "WATCH"
    assert s["sub_scores"]["market_potential"] is None
    assert s["sub_scores"]["competition_health"] is None
    assert s["sub_scores"]["opportunity_signal"] is None
    assert "market_potential" in s["missing"]


def test_missing_core_caps_at_watch_even_with_good_feasibility():
    # strong feasibility but NO market/competition/opportunity signals
    s = osc.score({"tag": "custom dog mom mug"})
    assert s["verdict"] == "WATCH"


def test_high_trademark_is_skip():
    s = osc.score(_strong(), keyword="disney nurse shirt")
    assert s["ip_risk"] == "high"
    assert s["verdict"] == "SKIP"


def test_missing_component_does_not_zero_the_score():
    # only velocity + conversion + competition present; demand + opportunity absent.
    partial = {"tag": "x", "momentum_score": 90, "avg_conversion_rate": 0.05,
               "competition_level": "low"}
    s = osc.score(partial)
    # market computed from the 2 present sub-signals, competition present -> a real
    # number, not dragged to ~0 by treating missing pieces as zero.
    assert s["sub_scores"]["market_potential"] is not None
    assert s["sub_scores"]["market_potential"] > 50
    assert s["sub_scores"]["opportunity_signal"] is None  # honest null
    # V30.1: core = Market + Competition only. A missing O renormalises away and
    # must NOT cap the verdict at WATCH (external-review consensus fix).
    assert s["core_complete"] is True
    assert s["verdict"] in ("GO", "CONDITIONAL", "WATCH")
    assert s["overall_score"] is not None


def test_competition_level_strings_map():
    assert osc._competition({"competition_level": "low"}) > \
        osc._competition({"competition_level": "high"})


def test_weights_load_falls_back_without_config():
    w = osc.load_weights("no_such_preset")
    assert abs((w.market + w.competition + w.opportunity + w.private
                + w.feasibility) - 1.0) < 0.001


def test_cell_format():
    c = osc.cell(_strong())
    assert c.split()[-1] in ("GO", "CONDITIONAL", "WATCH", "SKIP")


# --- product_fit.producibility (the gap that was half-wired) ------------------
from src import product_fit as pf


def test_producibility_print_is_neutral():
    r = pf.producibility("watercolor galaxy portrait", "pod")
    assert r["label"] == "PRINTS_FINE" and r["score"] == 100


def test_producibility_flags_unstitchable_embroidery():
    r = pf.producibility("watercolor galaxy portrait", "embroidery")
    assert r["label"] == "STITCH_RISK"
    assert r["score"] < 50


def test_producibility_rewards_stitch_safe_embroidery():
    r = pf.producibility("bold monogram initial", "embroidery")
    assert r["label"] == "STITCH_SAFE"
    assert r["score"] >= 75


def test_feasibility_blend_now_active_for_embroidery():
    # a photo-real embroidery concept must score LOWER feasibility than a clean one
    hard = osc._feasibility("watercolor galaxy portrait embroidery", "embroidery")[0]
    easy = osc._feasibility("bold monogram embroidery", "embroidery")[0]
    assert hard < easy


# --- V37.6: the three fixes that made the GO band reachable again -------------

def test_demand_reads_the_niche_total_not_per_listing_revenue():
    """The demand curve is calibrated for the NICHE TOTAL. avg_revenue has been
    strictly per-listing since V37.5, so feeding it raw put every row ~57 demand
    points low and no keyword in the base could reach GO."""
    per_listing = osc._demand_from({"avg_revenue": 2188.0})
    niche = osc._demand_from({"avg_revenue": 2188.0, "niche_revenue": 65638.0})
    assert niche > per_listing + 30      # measured gap at the median is ~57
    # explicit demand still wins over both
    assert osc._demand_from({"demand": 85, "niche_revenue": 10.0}) == 85


def test_no_market_score_is_reported_without_core_data():
    """561 rows carrying no market data at all were scoring 76-87 - on
    competition-from-listing-count plus the deterministic feasibility read - and
    sorting ABOVE every measured row. A verdict cap alone didn't stop that."""
    s = osc.score({"tag": "custom dog mom mug"})
    assert s["core_complete"] is False
    assert s["overall_score"] is None
    assert s["verdict"] == "WATCH"


def test_evidence_weight_reports_how_much_was_measured():
    full = osc.score(_strong())
    thin = osc.score({"tag": "x", "momentum_score": 90, "competition_level": "low"})
    assert full["evidence_weight"] > thin["evidence_weight"]
    assert 0.0 < thin["evidence_weight"] <= 1.0


def test_feasibility_is_not_capped_by_a_fabricated_seasonality():
    """There is no per-keyword seasonality source, so the leg was a hardcoded 60
    that cost every row 14 points and capped F at 79.25 - pulling every composite
    toward 79. Removing it must widen the spread in BOTH directions."""
    good = osc._feasibility("custom crew t-shirt", "pod")[0]
    junk = osc._feasibility("mercury retrograde spell", "pod")[0]
    assert good > 79.25          # a real product is no longer stuck under the cap
    assert junk < good - 20      # and an unmakeable term still falls well below
