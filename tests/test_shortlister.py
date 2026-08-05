"""Shortlister integration + K/M parse fix (from the YTrends bundle feedback)."""
import json
import os

from src import ytx_import as yi
from src import shortlister_integration as si


def test_parse_number_k_m_b_suffix():
    # the real sample abbreviates big counts; these used to parse ~1000x too small
    assert yi.parse_number("1.8K") == 1800.0
    assert yi.parse_number("3.4K") == 3400.0
    assert yi.parse_number("1.2M") == 1_200_000.0
    assert yi.parse_number("2B") == 2_000_000_000.0
    assert yi.parse_number("$5,900.25") == 5900.25   # unaffected
    assert yi.parse_number("760") == 760.0


SAMPLE = {
    "view": "hidden-gems",
    "captured_at": "2026-07-15T08:48:14+00:00",
    "headers": ["Rank", "Keyword", "Views 24h", "Revenue", "Avg Price",
                "Conversion Rate", "Listings", "Sellers", "Category"],
    "rows": [
        ["1", "personalized travel pouch", "1,240", "$3,420.50", "$24.99",
         "5.1%", "128", "82", "Bags & Pouches"],
        ["3", "custom bridesmaid makeup bag", "1.8K", "$5,900.25", "$22.50",
         "6.2%", "175", "97", "Wedding Gifts"],
        ["5", "haticemediumstudio", "999", "$1,000", "$12.00", "2.2%", "5", "1",
         "Shop Name Likely"],
        ["7", "gift for her", "3.4K", "$8,000", "$28.00", "3.0%", "50000",
         "12000", "Broad Gift"],
    ],
}


def test_map_row_does_not_set_raw_demand():
    d = si.map_row_to_scorer(SAMPLE["headers"], SAMPLE["rows"][0], "hidden-gems")
    # views_24h carries the raw count; there must be NO raw "demand" key (that slot
    # is a 0-100 score and a raw count there blows Market past 100)
    assert d["views_24h"] == 1240.0
    assert "demand" not in d
    assert d.get("is_hidden_gem") is True          # view-implied opportunity signal


def test_score_latest_is_sane_and_filters_junk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yi.ingest(SAMPLE)                              # writes the raw file score_latest reads
    res = si.score_latest()
    assert res["ok"]
    kws = {r["keyword"] for r in res["results"]}
    # real products kept, junk (shop handle, broad seed) dropped
    assert "personalized travel pouch" in kws
    assert "custom bridesmaid makeup bag" in kws
    assert "haticemediumstudio" not in kws
    assert "gift for her" not in kws
    # every composite score is within 0-100 (the raw-demand bug produced >2000)
    for r in res["results"]:
        assert r["overall_score"] is None or 0 <= r["overall_score"] <= 100


# ---------------------------------------------------------------------------
# Enrich must never fabricate a measurement (honest-nulls).
#
# Measured against the live MCP: it answers a keyword it has no data on with
# listing_count 0 / seller_count 0 rather than an error. The old put() accepted
# that zero AND reported success, so a winner-derived candidate was written to
# keyword_data.csv claiming "0 listings on Etsy" - and opportunity_score reads a
# 0-listing niche as the most wide-open market there is (90.0, vs 75.2 for a
# genuinely open 38-listing niche). That is a fabricated competitive advantage.
# ---------------------------------------------------------------------------
class _ZeroMCP:
    """An MCP that 'knows' the keyword but has no numbers for it."""
    @staticmethod
    def research_keyword(_kw):
        return {"stats": {"listing_count": 0, "seller_count": 0,
                          "avg_conversion_rate": 0, "avg_price": 0}}

    @staticmethod
    def trending_keywords(**_kw):
        return []

    @staticmethod
    def scout_opportunities(**_kw):
        return []


def test_enrich_never_writes_a_zero_measurement(monkeypatch):
    import src
    monkeypatch.setattr(src, "ytrends_mcp", _ZeroMCP, raising=False)
    d = {"tag": "personalized name tote handbag"}
    assert si._enrich_row(d) is False          # nothing real was added
    # and above all: no fabricated zeros left behind for the scorer / the CSV
    assert "listing_count" not in d
    assert "seller_count" not in d
    assert "avg_conversion_rate" not in d


def test_enrich_never_overwrites_a_real_captured_zero(monkeypatch):
    import src

    class _RealMCP(_ZeroMCP):
        @staticmethod
        def research_keyword(_kw):
            return {"stats": {"listing_count": 900, "seller_count": 40}}

    monkeypatch.setattr(src, "ytrends_mcp", _RealMCP, raising=False)
    d = {"tag": "kw", "listing_count": 0.0}    # the capture really measured zero
    si._enrich_row(d)
    assert d["listing_count"] == 0.0           # a measured 0 is a value, not a gap
    assert d["seller_count"] == 40.0           # the genuinely blank field is filled


def test_a_zero_listing_count_is_not_an_open_market():
    """Pins WHY the above matters: the scorer rewards a fabricated 0 the most."""
    from src import opportunity_score as osc
    assert osc._competition({"listing_count": 0.0}) == 90.0   # fabricated "open"
    assert osc._competition({"listing_count": 38}) < 90.0     # a REALLY open niche
    assert osc._competition({}) is None                       # honest unknown


def test_enrich_fills_the_demand_leg_so_candidates_can_leave_watch(monkeypatch):
    """research_keyword has always returned total_revenue / avg_revenue /
    avg_views_24h and _enrich_row read none of them. opportunity_score needs
    revenue or views for market_potential, so without them EVERY Keyword Lab and
    winner-derived candidate was core_missing -> score None -> WATCH, by
    construction. Verified live on 'custom crew t-shirt'."""
    import src
    from src import opportunity_score as osc

    class _RichMCP(_ZeroMCP):
        @staticmethod
        def research_keyword(_kw):
            return {"stats": {"total_listings": 31, "total_sellers": 24,
                              "avg_conversion_rate": 0.0507, "median_price": 19.9,
                              "total_revenue": 65694.58, "avg_revenue": 2119.18,
                              "avg_views_24h": 18.58}}

    monkeypatch.setattr(src, "ytrends_mcp", _RichMCP, raising=False)
    d = {"tag": "custom crew t-shirt"}
    assert si._enrich_row(d) is True
    assert d["niche_revenue"] == 65694.58      # the TOTAL, what the curve wants
    assert d["revenue"] == 2119.18             # per-listing average, kept apart
    assert d["views_24h"] == 18.58
    s = osc.score(d, keyword="custom crew t-shirt")
    assert s["demand_grounded"] is True        # was False -> forced WATCH
    assert s["overall_score"] is not None


def test_a_competition_label_with_no_counts_behind_it_is_ignored(monkeypatch):
    """Live: a keyword the server has no data on still comes back
    competition_level 'low' — the most favourable read there is (health 75)."""
    import src

    class _ShrugMCP(_ZeroMCP):
        @staticmethod
        def research_keyword(_kw):
            return {"stats": {"total_listings": 0, "total_sellers": 0,
                              "avg_revenue": None, "competition_level": "low"}}

    monkeypatch.setattr(src, "ytrends_mcp", _ShrugMCP, raising=False)
    d = {"tag": "personalized tote for granddaughter"}
    assert si._enrich_row(d) is False
    assert d == {"tag": "personalized tote for granddaughter"}   # nothing invented
