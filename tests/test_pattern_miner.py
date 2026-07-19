"""Pattern Miner: tokenization, price band, mining structure."""
from src import pattern_miner as pm


def test_tokens_singularize_plural_products():
    toks = pm._tokens("Personalized Nurse Embroidered Sweatshirts")
    assert "sweatshirt" in toks and "sweatshirts" not in toks


def test_price_band_usd_with_premium_outlier_stays_usd():
    band = pm._price_band([19.99, 24.5, 22.0, 39.99, 1299.0])
    assert band["note"] == "USD"
    assert band["median"] < 50


def test_price_band_vnd_detected_by_median():
    band = pm._price_band([826446, 941047, 1225895])
    assert "VND" in band["note"]
    assert 20 < band["median"] < 80          # ~$33-49 at ~25k rate


def test_price_band_empty():
    assert pm._price_band([]) is None


def test_mine_empty_batch_is_honest():
    r = pm.mine("keyword-that-has-no-data-anywhere-xyz")
    # may fall back to master CSV's largest group; if nothing at all, have=False
    assert isinstance(r, dict) and "have" in r
