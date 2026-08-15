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
    for k in ("svg bundle", "clip art", "cut file", "digital print"):
        c = classify(k)
        assert c["status"] == "DIGITAL_FIT" and not c["launchable"]
    # Negative fixtures: physical apparel/goods with 'print' or 'file' must remain launchable physical items
    for k in ("leopard print shirt", "flower print tote bag", "nail file"):
        c = classify(k)
        assert c["status"] != "DIGITAL_FIT", f"physical item '{k}' misclassified as DIGITAL_FIT"


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


def test_theme_needs_product_is_not_launchable():
    # A design theme with no product noun and no strong buyer intent must NOT be
    # shown as launch-ready — the team has to choose a product first.
    for k in ("funny raccoon", "retro sunset", "coastal grandmother"):
        c = classify(k)
        assert c["status"] == "THEME_FIT_NEEDS_PRODUCT" and not c["launchable"], k


def test_theme_ready_with_buyer_intent_is_launchable():
    # A theme carrying clear occasion / gift-recipient intent launches as-is.
    for k in ("teacher appreciation", "nurse christmas", "50th celebrations"):
        c = classify(k)
        assert c["status"] == "THEME_FIT_READY" and c["launchable"], k


def test_low_intent_and_ambiguous_hidden():
    assert classify("cat facts")["status"] == "LOW_BUYER_INTENT"
    assert not classify("cat facts")["launchable"]
    for k in ("retro", "xy"):
        c = classify(k)
        assert c["status"] == "AMBIGUOUS_PHRASE" and not c["launchable"], k


def test_spec_product_fit_cases():
    # The exact classifications required by the V28.0 readiness spec (#4).
    expect = {
        "funny raccoon": "THEME_FIT_NEEDS_PRODUCT",
        "retro sunset shirt": "POD_FIT",
        "gift for her": "BROAD_SEED_ONLY",
        "haticemediumstudio": "SHOP_NAME_LIKELY",
        "contact spell": "POLICY_RISK",
        "fathers day pokemon": "TRADEMARK_RISK",
        "monogram tote bag": "EMBROIDERY_FIT",
    }
    for kw, status in expect.items():
        assert classify(kw)["status"] == status, kw


def test_opportunity_clusters_group_related_keywords():
    from src import clusters
    groups, singles = clusters.cluster(
        ["summer pouch", "travel pouch", "bridesmaid pouch", "vacation pouch",
         "coastal grandmother"])
    names = {c["name"] for c in groups}
    assert "pouch" in names
    biggest = max(groups, key=lambda c: c["size"])
    assert biggest["size"] == 4
    assert "coastal grandmother" in singles


def test_opportunity_cluster_enrichment_and_honesty():
    from src import clusters
    cl, singles = clusters.build_opportunity_clusters(
        ["summer pouch", "travel pouch", "bridesmaid pouch", "vacation pouch",
         "coastal grandmother"])
    assert cl, "expected at least one sellable cluster"
    c = cl[0]
    assert c["product_type"] == "pouch"
    for field in ("cluster_id", "cluster_name", "primary_keyword",
                  "related_keywords", "product_mode", "product_type",
                  "supplier_status", "verdict", "next_action", "reason_shown"):
        assert field in c, field
    assert c["next_action"] == "Assign supplier check + competitor audit"
    assert c["product_mode"] in ("pod", "embroidery")
    assert c["cluster_name"].startswith("Personalized") and "Pouch" in c["cluster_name"]
    # market scores are honestly pending — NOT fabricated
    assert c["demand_score"] is None and c["profit_score"] is None
    assert c["scores_status"].startswith("pending")
    assert "coastal grandmother" in singles


def test_clusters_group_by_product_noun_not_modifier():
    from src import clusters
    groups, singles = clusters.cluster(
        ["chenille name bag", "bridesmaid bag", "transparent bag",
         "custom name necklace", "indoor decals", "personalized decals"])
    by = {c["name"]: c for c in groups}
    # the three bags collapse into ONE "bag" idea (not split by the "name" modifier)
    assert by["bag"]["size"] == 3
    assert "chenille name bag" in by["bag"]["members"]
    # plural product noun is normalised (decals -> decal)
    assert by["decal"]["size"] == 2
    # a lone necklace is NOT dragged into a "name" cluster with the bag
    assert "custom name necklace" in singles
