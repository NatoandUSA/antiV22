"""Product-fit filter + seasonal launch-status tests (offline)."""
from datetime import date

from src.product_fit import classify
from src import seasonal


def test_shop_handle_hidden():
    c = classify("haticemediumstudio")
    assert c["status"] == "SHOP_NAME_LIKELY" and not c["launchable"]


def test_policy_niche_hidden():
    for k in ("best job spell", "real money spell", "love reading psychic",
              "contact spell"):
        c = classify(k)
        assert c["status"] == "POLICY_RISK" and not c["launchable"]


def test_trademark_brand_hidden():
    assert classify("fathers day pokemon")["status"] == "TRADEMARK_RISK"
    assert not classify("taylor swift hoodie")["launchable"]


def test_digital_only_hidden():
    c = classify("svg bundle")
    assert c["status"] == "DIGITAL_FIT" and not c["launchable"]


def test_broad_seed_hidden():
    assert classify("gift for her")["status"] == "BROAD_SEED_ONLY"
    assert not classify("gift for her")["launchable"]


def test_real_products_launchable():
    assert classify("usa raccoon shirt")["launchable"]
    assert classify("chenille name bag")["status"] == "EMBROIDERY_FIT"
    assert classify("custom name necklace")["status"] == "JEWELRY_FIT"
    assert classify("indoor decals")["launchable"]        # plural noun handled


def test_mode_mismatch_not_launchable():
    # an embroidery term is NOT a POD launch opportunity
    assert not classify("chenille name bag", mode="pod")["launchable"]


def test_calendar_launch_status_labels():
    hols = seasonal.upcoming_holidays(today=date(2026, 7, 8), horizon_days=366, mode="pod")
    statuses = [h["launch_status"] for h in hols]
    # Back to School (Aug 18) launch-by ~Jul 4 -> past the ideal on Jul 8
    assert "LATE_TEST_ONLY" in statuses
    assert any(s in ("PREP_EARLY", "NEXT_YEAR_PREP", "PREP_NOW") for s in statuses)
    assert all("launch_status" in h for h in hols)


def test_calendar_range_narrows():
    yr = len(seasonal.upcoming_holidays(today=date(2026, 7, 8), horizon_days=366))
    mo = len(seasonal.upcoming_holidays(today=date(2026, 7, 8), horizon_days=30))
    assert yr > mo
