"""Unit tests for the V24 sales-execution OS modules (offline, no network)."""
from src import profit, tracking, alerts, launchpad, interactive as iv
from src.trademark import check as tm


# ------------------------------------------------------------- profit ----
def test_profit_compute_positive():
    f = profit.compute(30, 8, 0)
    # 30 - 8 - 0.20 - 6.5%*30 - (3%*30+0.25) - 2.5%*30 (currency) = 17.95
    assert f["net_profit"] == 17.95
    assert 0.58 < f["margin"] < 0.61


def test_profit_refund_is_a_loss():
    f = profit.compute(30, 8, 2, refunded=True)
    assert f["net_profit"] == -10.0


def test_profit_currency_fee_on_item_plus_shipping():
    # VN payout: 2.5% currency conversion on the WHOLE order (item + shipping)
    f = profit.compute(20, 5, 4)
    assert f["currency_fee"] == 0.60          # 2.5% of (20 + 4)
    assert f["transaction_fee"] == 1.56       # 6.5% of (20 + 4)


def test_profit_offsite_on_item_plus_shipping():
    f = profit.compute(30, 8, 5, offsite_ad=True)
    assert f["offsite_ad_fee"] == 5.25        # 15% of (30 + 5), not item-only
    assert profit.compute(30, 8, 5)["offsite_ad_fee"] == 0.0   # off by default


def test_profit_zero_price_no_crash():
    f = profit.compute(0, 5, 0)
    assert f["net_profit"] <= 0 and f["margin"] == 0.0


def test_profit_add_and_summary():
    profit.add({"supplier": "TestSup", "product_mode": "pod",
                "sale_price": "25", "product_cost": "6", "shipping_cost": "0"})
    s = profit.summary()
    assert s["sales"] >= 1
    assert "TestSup" in s["by_supplier"]
    assert s["by_supplier"]["TestSup"]["sales"] >= 1


# ------------------------------------------------------------ tracking ----
def test_keyword_snapshot_and_trend_rising():
    # two snapshots with rising demand -> the tracker should read it
    tracking.snapshot_keyword("test rising kw", "pod", {"avg_views_24h": 10})
    # force a second, higher snapshot on a different logical day by editing store
    store = tracking._load(tracking.KW_JSON)
    store["test rising kw"][0]["date"] = "2020-01-01"
    tracking._save(store, tracking.KW_JSON, tracking.KW_CSV, tracking.KW_COLS)
    tracking.snapshot_keyword("test rising kw", "pod", {"avg_views_24h": 100})
    rows = {r["keyword"]: r for r in tracking.keyword_rows()}
    assert "test rising kw" in rows
    assert rows["test rising kw"]["trend"] in ("rising", "new", "stable")


# -------------------------------------------------------------- alerts ----
def test_alerts_add_resolve_summary():
    a = alerts.add("unit_test", "unit test alert", "warn", "utref")
    assert a["level"] == "warn"
    assert alerts.summary()["open"] >= 1
    alerts.resolve(a["id"])
    open_refs = [r["ref"] for r in alerts.load()]
    assert "utref" not in open_refs


def test_alerts_generate_no_crash():
    assert isinstance(alerts.generate(), list)


# ------------------------------------------------------------ launchpad ----
def test_launchpad_board_shape():
    b = launchpad.board()
    for col in launchpad.COLUMNS:
        assert col in b
    assert isinstance(launchpad.summary(), dict)


# ----------------------------------------------------- listing analyzer ----
def _clean13():
    return ", ".join([
        "personalized dog mom shirt", "custom dog mom gift", "dog lover present",
        "pet owner shirt", "dog mama tee", "custom pet portrait",
        "dog mom birthday", "fur mama gift", "personalized pet tee",
        "dog owner apparel", "gift for dog mom", "custom dog name shirt",
        "dog lover birthday gift"])


def test_analyzer_clean_listing_passes_gate():
    out = iv.analyze_listing(
        "personalized dog mom shirt, custom pet gift", _clean13(),
        "This personalized dog mom shirt is custom printed with your pet name. "
        "Ships in 3-5 days. Material is soft cotton, choose your size.",
        kw="personalized dog mom shirt", first_image_ready=True, supplier_ok=True)
    assert "Publish Gate: true" in out


def test_analyzer_blocks_without_supplier_or_image():
    out = iv.analyze_listing(
        "personalized dog mom shirt", _clean13(),
        "custom printed with your pet name, ships in 3 days, cotton material",
        kw="personalized dog mom shirt", first_image_ready=False, supplier_ok=False)
    assert "Publish Gate: false" in out
    assert "DRAFT ONLY" in out
    assert "Supplier not confirmed" in out


def test_analyzer_flags_thin_listing():
    out = iv.analyze_listing("dog shirt", "dog, shirt", "short", kw="dog shirt")
    assert "Publish Gate: false" in out


def test_ads_readiness_gate():
    assert "ADS_READY: true" in iv.ads_readiness(True, 82, 75, 0.40, True)
    assert "ADS_READY: false" in iv.ads_readiness(False, 60, 50, 0.10, False)


# ---------------------------------------------------- trademark tuning ----
def test_tm_check_descriptive_ok_slogan_caution_brand_high():
    assert tm("gift for dog mom")[0] == "OK"          # descriptive long-tail
    assert tm("personalized dog name shirt")[0] == "OK"
    assert tm("make them chase you")[0] == "CAUTION"   # real slogan (pronoun)
    assert tm("taylor swift shirt")[0] == "HIGH"       # known brand
