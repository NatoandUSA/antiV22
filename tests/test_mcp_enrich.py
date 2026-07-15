"""MCP hybrid-enrich: fill gaps, but never invent signal.

The load-bearing test here is the insufficient_data gate. The live MCP server
answers for keywords it knows nothing about with opportunity_score=100 +
competition_level='low' + total_listings=0, which the scorer would read as a
maximum opportunity signal on a best-case market = a false GO on a keyword with
no listings at all. Both payloads below are real shapes captured from the server.
"""
from src import mcp_enrich as me
from src import opportunity_score as osc

# real research_keyword('personalized gift').stats - genuine market data
RICH = {"total_listings": 45487, "total_sellers": 15669, "avg_price": 34.7,
        "avg_conversion_rate": 0.0214, "avg_views_24h": 2.78, "avg_revenue": 681.09,
        "competition_level": "very_high", "opportunity_score": 52.1,
        "opportunity_grade": "D", "recommended_action": "competitive"}

# real research_keyword('monogrammed makeup bag').stats - server has NO data,
# yet still reports a perfect opportunity_score and 'low' competition
EMPTY = {"total_listings": 0, "total_sellers": 0, "avg_price": None,
         "avg_conversion_rate": None, "avg_revenue": None,
         "competition_level": "low", "opportunity_score": 100,
         "opportunity_grade": "N", "recommended_action": "insufficient_data"}


def test_trustworthy_gate():
    assert me.is_trustworthy(RICH) is True
    assert me.is_trustworthy(EMPTY) is False
    assert me.is_trustworthy({}) is False
    assert me.is_trustworthy(None) is False


def test_insufficient_data_never_injects_a_signal():
    d = {"tag": "monogrammed makeup bag", "momentum_score": 76}
    out, note = me.enrich_row(d, EMPTY)
    assert note["enriched"] is False
    assert note["reason"] == "insufficient_data"
    # the poisoned 100 / 'low' must NOT have reached the row
    assert "opportunity_score" not in out
    assert out.get("competition_level") is None
    assert out.get("listing_count") is None


def test_insufficient_data_cannot_produce_a_false_go():
    # momentum 92 is chosen deliberately: with the poisoned opportunity_score=100
    # injected, this row scores 80.8 = GO on a keyword with ZERO listings. That is
    # the exact profile of a hot new trending term, so a weaker momentum here would
    # let this test pass even with the gate removed.
    base = {"tag": "monogrammed makeup bag", "momentum_score": 92,
            "competition_level": "low"}
    naive = dict(base)
    for src, dest in me.FIELD_MAP.items():          # simulate an ungated enrich
        if EMPTY.get(src) is not None:
            naive[dest] = EMPTY[src]
    assert osc.score(naive, keyword=naive["tag"])["verdict"] == "GO"   # the danger

    gated = dict(base)
    me.enrich_row(gated, EMPTY)
    s = osc.score(gated, keyword=gated["tag"])
    assert s["verdict"] == "WATCH"                  # honest: no data, no verdict
    assert s["sub_scores"]["opportunity_signal"] is None


def test_enrich_fills_only_blanks_and_keeps_extension_truth():
    d = {"tag": "personalized gift", "momentum_score": 60, "avg_price": 19.99}
    out, note = me.enrich_row(d, RICH)
    assert note["enriched"] is True
    assert out["listing_count"] == 45487          # blank -> filled from MCP
    assert out["avg_conversion_rate"] == 0.0214
    assert out["avg_price"] == 19.99              # extension value NOT overwritten
    assert "avg_price" not in note["filled"]


def test_views_are_never_enriched():
    # stats.avg_views_24h is per-LISTING (2.78); the scorer's views_24h is a
    # per-keyword TOTAL. Mapping them is ~1000x wrong, so views stay missing.
    d = {"tag": "personalized gift"}
    out, _ = me.enrich_row(d, RICH)
    assert out.get("views_24h") is None
    assert "views_24h" not in me.FIELD_MAP.values()


def test_very_high_competition_maps_and_is_not_read_as_favourable():
    d = {"tag": "personalized gift"}
    me.enrich_row(d, RICH)
    assert d["competition_level"] == "very high"          # underscore normalised
    assert osc.COMP_INTENSITY[d["competition_level"]] == 95
    # a 45k-listing keyword must not score as a healthy, open market
    assert osc._competition(d) < 20
