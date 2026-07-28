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


def test_query_tokens_excluded_from_top_words(tmp_path, monkeypatch):
    # V37.4: the query's own words must not dominate the "winning words" output.
    import json
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "data/imports/etsy_spy"
    d.mkdir(parents=True)
    (d / "cap.json").write_text(json.dumps({
        "view": "etsy",
        "headers": ["title", "price", "shop", "search", "url"],
        "rows": [
            ["Personalized Nurse Sweatshirt RN Gift Crewneck", "39", "A", "nurse sweatshirt", "u1"],
            ["Custom Nurse Sweatshirt Nursing School ER Gift", "41", "B", "nurse sweatshirt", "u2"],
            ["Registered Nurse Sweatshirt Personalized Week", "38", "C", "nurse sweatshirt", "u3"],
        ]}), encoding="utf-8")
    r = pm.mine("nurse sweatshirt")
    words = [w for w, _ in r["top_words"]]
    assert "nurse" not in words and "sweatshirt" not in words   # query tokens gone
    assert any(w in words for w in ("crewneck", "rn", "nursing", "registered"))
