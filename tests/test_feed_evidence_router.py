"""Tests for the V37.4 Feed Center Evidence Router.

Standalone (stdlib + pytest). Uses tmp_path as cwd so the lanes are written under
a throwaway data/imports/. Fixtures mirror the REAL captured listing 4412078408
(TinyBarns "Personalized Name Tote Handbag") that the CEO review read.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import feed_evidence_router as fer  # noqa: E402
from src import photo_brief  # noqa: E402


# --- fixtures mirroring the real v3.4.0 exports ----------------------------
DETAIL_HEADERS = [
    "listing_id", "title", "shop", "price_raw", "estimated_sold",
    "estimated_revenue_usd", "views", "views_average", "favorites",
    "favorite_rate_pct", "conversion_pct", "listing_age_days", "shop_sales",
    "shop_reviews", "listing_review_count", "tags", "tags_count", "image_count",
    "heyetsy_url",
]
DETAIL_ROW = [
    "4412078408",
    "Personalized Name Tote Handbag: Custom Children&#39;s Gift, Baby Shower Gifts",
    "TinyBarns", "15.36 USD", "2294", "35236", "52.6K", "216", "2.5K", "4.73",
    "4",                       # conversion_pct = 4  -> rate 0.04
    "240", "56207",
    "0",                       # shop_reviews = 0  -> treated as unknown (None)
    "472",
    "Baby Gifts;Custom Name Tote Handbag;Toddlers Bag;Custom Name Bags", "13", "20",
    "https://heyetsy.com/listing/4412078408",
]

REVIEW_HEADERS = [
    "listing_id", "review_id", "rating", "review_text", "variation_json",
    "review_date", "buyer", "review_image_id", "review_photo_url",
    "feature_tags_json", "categorical_tags_json", "buyers_recommend_pct",
    "item_quality_rating", "listing_review_count",
]
_SUMMARY_FEATURE = '["Looks great","Perfect gift","Great quality","Fast shipping"]'
_SUMMARY_CAT = '[{"tag":"Appearance","frequency":252},{"tag":"Quality","frequency":119}]'


def _review_row(rid, rating, text, variation, image_id="", photo=""):
    return ["4412078408", rid, rating, text, variation, "2026-01-01", "Buyer",
            image_id, photo, _SUMMARY_FEATURE, _SUMMARY_CAT, "99", "4.9", "472"]


REVIEW_ROWS = [
    _review_row("r1", "5", "Bought for my granddaughter, she loves it!",
                '{"Color":"Pink"}', image_id="img1"),
    _review_row("r2", "5", "Perfect gift for my granddaughter's birthday",
                '{"Color":"Pink"}'),
    _review_row("r3", "4", "Nice tote but the material felt a bit thin",
                '{"Color":"Green"}'),
    _review_row("r4", "5", "Great quality, fast shipping. Niece adored it.",
                '{"Color":"White"}'),
]


@pytest.fixture(autouse=True)
def _chdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield


# --- detection --------------------------------------------------------------
def test_detail_csv_detected():
    assert fer.looks_like_heyetsy_detail(DETAIL_HEADERS) is True
    assert fer.looks_like_etsy_reviews(DETAIL_HEADERS) is False


def test_review_csv_detected():
    assert fer.looks_like_etsy_reviews(REVIEW_HEADERS) is True
    assert fer.looks_like_heyetsy_detail(REVIEW_HEADERS) is False


def test_detail_not_caught_as_keywords_or_review():
    # a plain keyword table must NOT trip either detector
    kw_headers = ["keyword", "etsy_listings", "views_24h", "avg_price"]
    assert fer.looks_like_heyetsy_detail(kw_headers) is False
    assert fer.looks_like_etsy_reviews(kw_headers) is False


# --- number / unit normalization -------------------------------------------
def test_conversion_pct_normalization():
    assert fer.normalize_conversion("4") == (4.0, 0.04)
    assert fer.normalize_conversion("4%") == (4.0, 0.04)
    raw, rate = fer.normalize_conversion("0.04")
    assert rate == 0.04
    assert fer.normalize_conversion("") == (None, None)   # honest null
    # implausible > 100 keeps raw but refuses to invent a rate
    assert fer.normalize_conversion("400")[1] is None


def test_km_parsing_and_html_unescape():
    assert fer.parse_market_number("52.6K") == 52600
    assert fer.parse_market_number("2.5K") == 2500
    assert fer.parse_market_number("$35,236") == 35236
    assert fer.parse_market_number("15.36 USD") == 15.36
    assert fer.parse_market_number("-") is None
    assert fer.clean_text("Children&#39;s Gift") == "Children's Gift"


# --- detail lane ------------------------------------------------------------
def test_detail_normalized_and_saved():
    d = fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW], source_hint="HeyEtsy_4412078408_Detail.csv")
    assert d["listing_id"] == "4412078408"
    assert d["estimated_sold"] == 2294
    assert d["estimated_revenue_usd"] == 35236
    assert d["conversion_pct_raw"] == 4.0 and d["conversion_rate"] == 0.04
    assert d["views"] == 52600
    assert d["evidence_type"] == fer.DETAIL_EVIDENCE_TYPE   # NOT "real proof"
    assert d["shop_spread"] == 1
    # BUG-004: shop_reviews 0 from detail is unknown, not authoritative
    assert d["shop_reviews"] is None
    assert "'" in d["title"]  # html entity was unescaped
    assert fer.load_detail("4412078408")["estimated_sold"] == 2294


def test_single_listing_not_proven():
    d = fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    act = fer.listing_evidence_action(d)
    assert act["max_action"] == "CONFIRM_FIRST"           # never BUILD_NOW
    # with a second shop's evidence it may rise to REVIEW, still not BUILD_NOW
    act2 = fer.listing_evidence_action(d, extra_shop_spread=1)
    assert act2["max_action"] == "REVIEW"


def test_same_shop_spread():
    # saving the same single listing twice is still one shop (spread stays 1)
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    d = fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    assert d["shop_spread"] == 1
    assert fer.listing_evidence_action(d)["max_action"] == "CONFIRM_FIRST"


# --- review lanes -----------------------------------------------------------
def test_listing_id_match():
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    res = fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    assert res["listing_id"] == "4412078408"              # detail + reviews match
    assert res["reviews"] == 4


def test_review_summary_dedup():
    fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    summary_path = Path("data/imports/etsy_review_summary/4412078408.json")
    assert summary_path.is_file()
    import json
    summ = json.loads(summary_path.read_text())
    # the listing-level summary is stored ONCE, not multiplied by 4 review rows
    assert summ["review_rows_in_file"] == 4
    assert "feature_tags_json" in summ["fields"]
    # re-importing identical summary does not re-write (same checksum)
    res2 = fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    assert res2["summary_written"] is False


def test_missing_variation_honest_null():
    rows = [_review_row("rX", "5", "Lovely gift", "")]   # no variation_json
    fer.save_reviews(REVIEW_HEADERS, rows)
    reviews = fer.load_reviews("4412078408")
    assert reviews[0]["variation_mentions"] == []        # nothing invented
    assert reviews[0]["variation_evidence_type"] is None


def test_has_review_photo_split():
    rows = [_review_row("rp", "5", "great", '{"Color":"Pink"}', image_id="img99")]
    fer.save_reviews(REVIEW_HEADERS, rows)
    r = fer.load_reviews("4412078408")[0]
    assert r["has_review_photo"] is True                 # from image_id
    assert r["review_photo_url"] is None                 # image_id != usable url


# --- review intel -----------------------------------------------------------
def test_review_intel_extracts_buyer_language():
    fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    intel = fer.review_intel("4412078408")
    recips = {r["value"] for r in intel["recipient_nouns"]}
    assert "granddaughter" in recips
    assert intel["affects_l2_market_signal"] is False
    # variants are MENTIONED, never called highest-converting
    assert intel["variant_evidence_type"] == "mentioned_or_reviewed"
    assert intel["complaints"].get("material")            # "thin material" caught


# --- keyword map / broad tags / re-rank ------------------------------------
def test_broad_tags_modifier_only():
    assert fer.classify_keyword_role("baby gifts") == "modifier"
    assert fer.classify_keyword_role("christmas gifts") == "modifier"
    # product-specific long-tail is a real candidate
    assert fer.classify_keyword_role("personalized name tote bag") == "primary_candidate"


def test_keyword_map_caps_and_broad_tags():
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    m = fer.build_keyword_map("4412078408")
    assert m["single_listing_evidence"] is True
    assert m["max_action_without_multishop"] == "CONFIRM_FIRST"
    by_kw = {c["keyword"]: c for c in m["candidates"]}
    # the broad "baby gifts" tag is modifier_only, never a standalone Build
    assert by_kw["baby gifts"]["keyword_role"] == "modifier"
    assert by_kw["baby gifts"]["action_cap"] == "modifier_only"


def test_review_keywords_rerank_not_autobuild():
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    fer.build_keyword_map("4412078408")
    cands = fer.candidates_for_rerank("4412078408")
    review_derived = [c for c in cands if c["match_type"] == "review_derived"]
    assert review_derived, "expected review-derived long-tail candidates"
    for c in review_derived:
        assert c["action_cap"] == "CONFIRM_FIRST"        # enters Re-rank, not build
        assert c["action_cap"] != "BUILD_NOW"
        assert "granddaughter" in " ".join(x["keyword"] for x in review_derived)


def test_medium_match_requires_confirmation():
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    m = fer.build_keyword_map("4412078408")
    for c in m["candidates"]:
        # nothing in a single-listing map may exceed CONFIRM_FIRST-tier action
        assert c["action_cap"] in ("CONFIRM_FIRST", "modifier_only")


def test_market_signal_unchanged_by_reviews():
    # the router must NEVER write the master keyword table that L2 reads
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    fer.review_intel("4412078408")
    assert not Path("keyword_data.csv").exists()


# --- keyword -> evidence join (feeds Pattern Miner + Keyword Lab) ------------
def test_evidence_for_keyword_matches_and_caps():
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    ev = fer.evidence_for_keyword("personalized name tote handbag")
    assert ev["has_evidence"] is True
    assert ev["single_listing_only"] is True
    assert ev["affects_l2_market_signal"] is False
    assert ev["listings"][0]["max_action"] == "CONFIRM_FIRST"   # never BUILD_NOW
    recips = {r["value"] for r in ev["recipient_nouns"]}
    assert "granddaughter" in recips
    # review-derived long-tails carry buyer language back for re-rank
    joined = " ".join(ev["review_derived_keywords"])
    assert "granddaughter" in joined


def test_evidence_for_keyword_no_wrong_attachment():
    # CF007: a listing's evidence must NOT attach to an unrelated keyword
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    ev = fer.evidence_for_keyword("nurse graduation sweatshirt")
    assert ev["has_evidence"] is False
    assert ev["review_derived_keywords"] == []


def test_evidence_for_keyword_empty_when_no_lanes():
    ev = fer.evidence_for_keyword("anything at all")
    assert ev["has_evidence"] is False


def test_evidence_no_cross_product_attachment():
    # CF007 regression: a listing's evidence must not attach to an unrelated keyword
    # that only shares generic modifiers ("custom name"). A necklace/mug keyword must
    # NOT borrow the tote handbag listing's evidence; same-product keywords still do.
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    assert fer.evidence_for_keyword("custom name necklace")["has_evidence"] is False
    assert fer.evidence_for_keyword("custom name mug")["has_evidence"] is False
    assert fer.evidence_for_keyword("nurse sweatshirt")["has_evidence"] is False
    assert fer.evidence_for_keyword("custom name tote bag")["has_evidence"] is True
    assert fer.evidence_for_keyword("personalized name tote handbag")["has_evidence"] is True


# --- recent evidence card (Feed / Import Center) ----------------------------
def test_recent_evidence_card():
    assert fer.recent_evidence() == []                    # no lanes -> empty
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    cards = fer.recent_evidence()
    assert len(cards) == 1
    c = cards[0]
    assert c["listing_id"] == "4412078408"
    assert c["estimated_sold"] == 2294
    assert c["review_count"] == 4
    assert c["has_summary"] is True
    assert c["top_recipient"] == "granddaughter"
    assert c["max_action"] == "CONFIRM_FIRST"             # never BUILD_NOW on the card
    assert c["conversion_rate"] == 0.04


# --- #2 Photo Studio: review-driven "prove this" notes ----------------------
def test_photo_brief_backward_compat_no_evidence():
    slots = photo_brief.build("nurse sweatshirt", mode="embroidery")
    assert len(slots) == 12
    assert all("prove" not in s for s in slots)           # identical to old output


def test_photo_brief_prove_notes_from_reviews():
    ev = {"has_evidence": True,
          "complaints": {"material": 3, "size": 1, "shipping": 2, "accuracy": 1},
          "photo_expectation_signals": 2,
          "recipient_nouns": [{"value": "granddaughter", "count": 2}],
          "top_mentioned_variants": [{"value": "pink", "count": 7}]}
    slots = photo_brief.build("personalized tote handbag", mode="embroidery",
                              evidence=ev)
    macro = next(s for s in slots
                 if "macro" in s["slot"].lower() or "print detail" in s["slot"].lower())
    assert any("thin" in p.lower() for p in macro.get("prove", []))
    hero = next(s for s in slots if "hero" in s["slot"].lower())
    assert hero.get("prove")                              # photo-expectation note
    size = next(s for s in slots if "size chart" in s["slot"].lower())
    assert any("sizing" in p.lower() for p in size.get("prove", []))
    care = next(s for s in slots if "care" in s["slot"].lower())
    assert any("shipping" in p.lower() for p in care.get("prove", []))
    pers = next(s for s in slots if "personalization" in s["slot"].lower())
    assert any("misspelled" in p.lower() for p in pers.get("prove", []))
    grid = next(s for s in slots if "color" in s["slot"].lower())
    assert any("pink" in p.lower() for p in grid.get("prove", []))


def test_photo_brief_prove_notes_end_to_end_from_lanes():
    # real lanes -> evidence_for_keyword -> photo_brief prove notes
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    ev = fer.evidence_for_keyword("personalized name tote handbag")
    slots = photo_brief.build("personalized name tote handbag", mode="pod",
                              evidence=ev)
    # the "thin material" review complaint should surface on a proof slot
    joined = " ".join(p for s in slots for p in s.get("prove", []))
    assert "granddaughter" in joined  # top recipient reaches the gift slot


# --- V37.7: step 10 -> 11, the loop that used to be open ---------------------
def test_candidates_reach_a_keyword_not_just_a_listing():
    """Pattern Miner is keyword-keyed but the map is listing-keyed. Without this
    join staff could see a dissected winner and still had to retype its keywords."""
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    cands = fer.candidates_for_keyword("personalized name tote handbag")
    assert cands, "a mined keyword must expose the winner's candidates"
    assert all(c.get("source_listing_id") for c in cands), "provenance required"
    # the CF007 guard must still hold: an unrelated keyword gets nothing
    assert fer.candidates_for_keyword("stainless steel dog tag") == []


def test_send_to_rerank_writes_the_master_and_an_audit_record():
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    picked = [c["keyword"] for c in fer.candidates_for_rerank("4412078408")][:2]
    res = fer.send_to_rerank(listing_id="4412078408", keywords=picked,
                             mode="pod", actor="tester")
    assert res["ok"] is True and res["added"] >= 1
    # keywords land in the master the Inbox ranks, tagged with their origin
    master = Path("keyword_data.csv").read_text(encoding="utf-8")
    assert "winner:4412078408" in master
    for k in picked:
        assert k in master
    # and the push is auditable: where it came from and why
    files = list((Path("data/imports/rerank_pushes")).glob("*.json"))
    assert len(files) == 1
    rec = json.loads(files[0].read_text(encoding="utf-8"))
    assert rec["source_listing_id"] == "4412078408"
    assert rec["actor"] == "tester"
    assert rec["action_cap"] == "CONFIRM_FIRST"      # never promotes to BUILD
    assert rec["reason"] and rec["evidence_summary"]
    assert "sold (est)" in rec["evidence_summary"]


def test_send_to_rerank_never_duplicates_an_existing_keyword():
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    fer.save_reviews(REVIEW_HEADERS, REVIEW_ROWS)
    picked = [c["keyword"] for c in fer.candidates_for_rerank("4412078408")][:2]
    first = fer.send_to_rerank(listing_id="4412078408", keywords=picked, mode="pod")
    second = fer.send_to_rerank(listing_id="4412078408", keywords=picked, mode="pod")
    assert first["added"] >= 1
    assert second["added"] == 0                       # re-import must not pollute
    assert second["already_present"] == len(picked)


def test_send_to_rerank_is_honest_when_there_is_nothing_to_send():
    res = fer.send_to_rerank(listing_id="does-not-exist")
    assert res["ok"] is False and res["added"] == 0 and res["reason"]


# --- V37.7 step 2: import bugs found by running the real 4412078408 export ---
def test_listing_url_is_the_etsy_listing_not_the_shop_page():
    """_ci returns the FIRST header containing a needle in FILE order, and the
    v3.4 export puts shop_url before etsy_url -- so "open listing" sent the team
    to the HeyEtsy shop page and the real listing URL was dropped entirely."""
    headers = ["listing_id", "title", "shop", "estimated_sold", "shop_url",
               "image_urls", "main_image", "etsy_url", "heyetsy_url"]
    row = ["999", "Custom Name Tote", "TinyBarns", "100",
           "https://www.heyetsy.com/shop/TinyBarns",
           '["https://i.etsystatic.com/a.jpg","https://i.etsystatic.com/b.jpg"]',
           "https://i.etsystatic.com/a.jpg",
           "https://www.etsy.com/listing/999/custom-name-tote",
           "https://heyetsy.com/listing/999"]
    d = fer.normalize_detail(headers, [row])
    assert d["etsy_url"] == "https://www.etsy.com/listing/999/custom-name-tote"
    assert d["heyetsy_url"] == "https://heyetsy.com/listing/999"
    assert "shop/TinyBarns" not in (d["etsy_url"] or "")


def test_winner_photos_are_captured_for_pattern_learning():
    headers = ["listing_id", "title", "estimated_sold", "image_urls",
               "main_image", "shop_rating"]
    row = ["999", "Custom Name Tote", "100",
           '["https://i.etsystatic.com/a.jpg","https://i.etsystatic.com/b.jpg"]',
           "https://i.etsystatic.com/a.jpg", "4.9"]
    d = fer.normalize_detail(headers, [row])
    assert d["images"] == ["https://i.etsystatic.com/a.jpg",
                           "https://i.etsystatic.com/b.jpg"]
    assert d["main_image"] == "https://i.etsystatic.com/a.jpg"
    assert d["image_count"] == 2          # derived when the export omits a count
    assert d["shop_rating"] == 4.9


def test_missing_photo_and_url_columns_stay_honest_nulls():
    """An older export without these columns must not invent them."""
    d = fer.normalize_detail(["listing_id", "title", "estimated_sold"],
                             ["999", "Custom Name Tote", "100"] and
                             [["999", "Custom Name Tote", "100"]])
    assert d["images"] == [] and d["main_image"] is None
    assert d["etsy_url"] is None and d["shop_rating"] is None


def test_flower_is_not_a_recipient_but_flower_girl_is():
    """A bare "flower" token matched floral PATTERN mentions and generated the
    nonsense candidate "personalized tote for flower"."""
    rows = [_review_row("p1", "5", "Love the flower pattern on this bag.", "{}"),
            _review_row("p2", "5", "Perfect for my flower girl!", "{}")]
    fer.save_detail(DETAIL_HEADERS, [DETAIL_ROW])
    fer.save_reviews(REVIEW_HEADERS, rows)
    vals = [r["value"] for r in fer.review_intel("4412078408")["recipient_nouns"]]
    assert "flower" not in vals
    assert "flower girl" in vals
