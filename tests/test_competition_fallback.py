"""The competition fallback used when a row has no competition_level label.

The old fallback was (listing_count / seller_count) * 8. Calibrated against 150
live YTrends keywords that DO carry a label, listings-per-seller turned out to be
nearly constant across the labels - median 1.43 (low) / 1.85 (medium) / 1.99
(high) - so it barely discriminated, and the ranges invert: 'low' keywords reach
4.38 while every 'high' keyword sits near 2.0. Mean absolute error vs the label's
own intensity was 69 for high and 72 for very_high.

Listing count separates the labels cleanly and log-linearly (median 38 / 374 /
1088), which is the relationship encoded below. MAE 5.2 overall on the same set.
Anchors in these tests are those live medians.
"""
from src import opportunity_score as osc


def _health(listings, **kw):
    row = {"listing_count": listings}
    row.update(kw)
    return osc._competition(row)


# ---- anchored on the live medians for each YTrends label --------------------
def test_matches_the_label_it_replaces():
    # median listings per label -> the intensity COMP_INTENSITY assigns that label
    for listings, label in ((38, "low"), (374, "medium"), (1088, "high")):
        expected = 100.0 - osc.COMP_INTENSITY[label]
        assert abs(_health(listings) - expected) <= 12, (listings, label)


def test_saturated_market_is_not_read_as_favourable():
    # real research_keyword('personalized gift'): 45,487 listings / 15,669 sellers.
    # The old ratio formula scored this 76.8 = "Favourable low-competition
    # landscape". It is the most saturated keyword in the sample.
    assert _health(45487, seller_count=15669) <= 10


def test_more_listings_is_never_better():
    healths = [_health(n) for n in (10, 38, 150, 374, 1088, 5000, 45487)]
    assert healths == sorted(healths, reverse=True), healths


def test_ratio_no_longer_inverts_the_ranking():
    # a 'low' keyword at the observed ratio extreme (107 listings / 24.4 sellers
    # = 4.38) must still score healthier than a 'high' one at ratio ~2.0
    low_kw = _health(107, seller_count=24)
    high_kw = _health(1088, seller_count=547)
    assert low_kw > high_kw


def test_label_still_wins_over_the_fallback():
    # the fallback must only fill in when there is no label to trust
    row = {"listing_count": 45487, "competition_level": "low"}
    assert osc._competition(row) == 100.0 - osc.COMP_INTENSITY["low"]


def test_listings_alone_is_enough_now():
    # the old formula needed BOTH listings and sellers, so a row with only a
    # listing count got no competition signal at all and was capped at WATCH
    assert _health(38) is not None
    assert osc._competition({}) is None            # still honest with no data
