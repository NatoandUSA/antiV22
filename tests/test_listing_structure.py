"""V37.5 — Etsy listing STRUCTURE lane: capture the winners' real tags /
personalization / variations / price and feed Pattern Miner + Re-rank."""
from src import feed_evidence_router as fer

# The extension's Etsy listing-detail (v3.6.3) header set.
DETAIL_HDR = ["listing_id", "title", "shop_name", "shop_url", "price", "currency",
              "rating", "review_count", "shop_sales", "shop_rating", "main_image_url",
              "image_urls", "description", "personalization_text", "variations_options",
              "shipping_returns_policies", "badges", "category_breadcrumb",
              "listing_rating", "listing_review_count", "shop_review_count",
              "buyers_recommend_pct", "rating_distribution_json", "etsy_url",
              "source_page_type", "keyword_context", "proof_scope_hint",
              "evidence_route_hint", "data_use_hint", "image_count",
              "review_summary_scope", "listing_tags", "jsonld_rating",
              "jsonld_review_count", "jsonld_price", "jsonld_availability"]


def _row(**kw):
    r = [""] * len(DETAIL_HDR)
    for k, v in kw.items():
        r[DETAIL_HDR.index(k)] = v
    return r


def test_detector_distinguishes_lanes():
    assert fer.looks_like_etsy_listing_structure(DETAIL_HDR)
    # HeyEtsy detail (has a sales estimate) is NOT structure
    assert not fer.looks_like_etsy_listing_structure(
        ["listing_id", "title", "he_sold", "estimated_revenue", "description"])
    # a reviews export is NOT structure
    assert not fer.looks_like_etsy_listing_structure(
        ["listing_id", "title", "review_text", "rating", "description"])
    # a search-results capture (has he_sold) is NOT structure
    assert not fer.looks_like_etsy_listing_structure(
        ["listing_id", "title", "he_sold", "he_tags"])


def test_save_structure_and_tags_become_candidates(sandbox):
    row = _row(listing_id="123",
               title="Personalized Nurse Sweatshirt Embroidered", shop_name="ShopA",
               price="39.99", image_count="7", personalization_text="Enter name",
               variations_options="Color: Black | Size: M",
               description="A cozy personalized nurse sweatshirt.",
               listing_tags="nurse sweatshirt; rn sweatshirt; personalized nurse gift; embroidered nurse")
    s = fer.save_listing_structure(DETAIL_HDR, [row], source_hint="etsy-listing")
    assert s and s["listing_id"] == "123"
    assert "nurse sweatshirt" in s["tags"] and s["has_personalization"] is True
    assert s["variations"] and s["price_usd"] == 39.99
    # round-trips
    assert fer.load_structure("123")["title"].startswith("Personalized")
    # real tags became re-rankable candidates via listing_keyword_map
    km = fer.load_keyword_map("123")
    assert km and any("nurse" in c["keyword"] for c in km["candidates"])
    assert fer.candidates_for_rerank("123")   # primary candidates exist


def test_structure_for_keyword_aggregates_winners(sandbox):
    for i, shop in enumerate(["ShopA", "ShopB"]):
        fer.save_listing_structure(DETAIL_HDR, [_row(
            listing_id=str(100 + i),
            title="Personalized Nurse Sweatshirt Embroidered", shop_name=shop,
            price="39", image_count="8", personalization_text="name",
            variations_options="Color: Black | Size: L",
            listing_tags="nurse sweatshirt; rn gift; embroidered nurse")])
    r = fer.structure_for_keyword("personalized nurse sweatshirt embroidered")
    assert r["has_structure"] and r["listings"] == 2
    assert r["personalization_rate"] == 100
    assert any(t == "nurse sweatshirt" for t, _ in r["top_tags"])
    assert r["variation_opportunities"]
    assert r["affects_l2_market_signal"] is False


def test_pattern_miner_attaches_structure(sandbox):
    fer.save_listing_structure(DETAIL_HDR, [_row(
        listing_id="55", title="Personalized Nurse Sweatshirt Embroidered",
        shop_name="ShopA", price="39", personalization_text="name",
        listing_tags="nurse sweatshirt; rn gift")])
    from src import pattern_miner as pm
    res = pm.mine("personalized nurse sweatshirt embroidered")
    assert "listing_structure" in res
    assert res["listing_structure"]["has_structure"] is True
    assert res["listing_structure"]["listings"] >= 1


def test_jsonld_fallback_used_when_dom_scrape_blank(sandbox):
    """v3.6.3 sends jsonld_rating/jsonld_review_count/jsonld_availability
    specifically because they survive when Etsy's CSS/class names change and
    the DOM-scraped listing_rating/listing_review_count come back blank. The
    normalizer must actually fall through to them when the DOM value is
    empty, not just when the DOM column is entirely absent."""
    row = _row(listing_id="777", title="Personalized Nurse Sweatshirt Embroidered",
               shop_name="ShopA", price="39.99",
               listing_tags="nurse sweatshirt",
               # DOM scrape came back empty (CSS changed) ...
               listing_rating="", listing_review_count="",
               # ... but the JSON-LD structured data still had it.
               jsonld_rating="4.8", jsonld_review_count="612",
               jsonld_availability="InStock")
    s = fer.save_listing_structure(DETAIL_HDR, [row], source_hint="etsy-listing")
    assert s["rating"] == 4.8
    assert s["review_count"] == 612
    assert s["availability"] == "InStock"
