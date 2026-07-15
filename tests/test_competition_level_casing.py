"""Two casing bugs that made a real competition signal silently vanish.

Both were found by asking the live servers what they actually emit:
- MCP research_keyword returns competition_level 'very_high' (underscore), but
  COMP_INTENSITY keys on 'very high', so it mapped to None and _competition fell
  through to the listings/sellers ratio - which reads a 45k-listing keyword as a
  healthy open market.
- The REST API returns lowercase 'low'/'medium'/'high', but discover.is_focus
  compared == "LOW", so that clause never fired and low_comp collapsed to the
  listing_count <= 300 fallback alone.
"""
from src import discover, opportunity_score as osc


# ---- opportunity_score._competition: underscore form must map ----------------
def test_very_high_underscore_is_not_read_as_healthy_market():
    # real research_keyword('personalized gift') shape: brutally saturated
    row = {"competition_level": "very_high", "listing_count": 45487,
           "seller_count": 15669}
    # unmapped, _competition falls back to (listings/sellers)*8 = ~23 intensity
    # and reports ~77 = "favourable low-competition landscape". It is not.
    assert osc._competition(row) < 20


def test_competition_level_forms_all_map():
    for lvl, expected in (("very_high", 5.0), ("very high", 5.0), ("VERY_HIGH", 5.0),
                          ("high", 15.0), ("low", 75.0), ("medium", 45.0)):
        assert osc._competition({"competition_level": lvl}) == expected


def test_unknown_level_still_falls_back_rather_than_crashing():
    assert osc._competition({"competition_level": "banana"}) is None
    assert osc._competition({"competition_level": "banana", "listing_count": 300,
                             "seller_count": 100}) is not None


# ---- discover.is_focus: lowercase level must count as low competition --------
def _row(**kw):
    x = {"tag": "monogrammed makeup bag", "competition_level": "low",
         "listing_count": 900, "demand_24h": 800, "conversion": 0.05,
         "momentum": 60, "avg_revenue": 0, "tm_risk": "OK", "in_my_niche": True}
    x.update(kw)
    return x


def test_lowercase_low_counts_as_low_competition():
    # the live REST API emits 'low'; == "LOW" never matched, so this keyword was
    # dropped from FOCUS purely because it has >300 listings
    assert discover.is_focus(_row(), []) is True


def test_high_competition_with_many_listings_is_not_focus():
    assert discover.is_focus(_row(competition_level="high"), []) is False


def test_low_listing_count_fallback_still_works():
    # unknown level but a tiny market is still low competition
    assert discover.is_focus(_row(competition_level=None, listing_count=120),
                             []) is True
