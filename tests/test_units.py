"""Idiomatic, isolated unit tests for the pure decision logic.

These need no network, no reports/ tree, and no monkeypatching of module
globals, so they are order-independent and fast. The heavier end-to-end
pipeline is covered by test_integration.py inside a temp-cwd sandbox.
"""
import pytest

from src.validators import validate_title, validate_tags
from src.publish_gate import publish_gate, partner_status
from src.trademark import check as tm_check


# --------------------------------------------------------------------------
# Title validation
# --------------------------------------------------------------------------

def test_clean_title_passes():
    ok, issues = validate_title(
        "Personalized Clear Concert Bag with Name - "
        "Stadium Approved Festival Purse")
    assert ok, issues


def test_keyword_stuffed_title_fails():
    ok, issues = validate_title(
        "Bag Bag Bag Custom Bag Personalized Bag, Cute Bag, Gift Bag, "
        "Best Bag, Trendy Bag, New Bag, Nice Bag Pouch")
    assert not ok
    assert any("stuffing" in i for i in issues)


def test_title_without_product_noun_fails():
    ok, issues = validate_title("Personalized Custom Design for Fans")
    assert not ok
    assert any("product noun" in i for i in issues)


def test_title_flags_unsupported_material_claim():
    ok, issues = validate_title("Genuine Leather Tote Bag", confirmed_material="")
    assert not ok
    assert any("material" in i for i in issues)
    # ...but passes once the supplier-confirmed material backs the claim.
    ok2, _ = validate_title("Genuine Leather Tote Bag",
                            confirmed_material="leather")
    assert ok2


# --------------------------------------------------------------------------
# Tag validation
# --------------------------------------------------------------------------

GOOD_TAGS = [
    "clear concert bag", "stadium approved bag", "festival purse",
    "personalized pouch", "game day bag", "clear stadium purse",
    "custom name bag", "concert accessories", "transparent tote",
    "event clear bag", "gift for her bag", "travel pouch bag",
    "clear crossbody bag",
]


def test_good_tags_pass():
    ok, issues = validate_tags(GOOD_TAGS)
    assert ok, issues


def test_wrong_tag_count_fails():
    ok, issues = validate_tags(GOOD_TAGS[:12])
    assert not ok
    assert any("exactly 13" in i for i in issues)


def test_duplicate_tags_fail():
    ok, issues = validate_tags(["clear bag"] * 13)
    assert not ok
    assert any("duplicate" in i for i in issues)


def test_over_length_tag_fails():
    tags = GOOD_TAGS[:12] + ["this tag is definitely longer than twenty chars"]
    ok, issues = validate_tags(tags)
    assert not ok
    assert any("over 20 chars" in i for i in issues)


# --------------------------------------------------------------------------
# Trademark heuristic
# --------------------------------------------------------------------------

def test_known_brand_is_high_risk():
    assert tm_check("taylor swift hoodie")[0] == "HIGH"


def test_descriptive_keyword_is_not_high_risk():
    assert tm_check("clear concert bag")[0] != "HIGH"


def test_slogan_pronoun_is_caution():
    assert tm_check("you are my sunshine shirt")[0] == "CAUTION"


# --------------------------------------------------------------------------
# Publish gate (the single source of truth)
# --------------------------------------------------------------------------

def _ready_candidate():
    """A candidate that should clear every gate -> PUBLISH_READY."""
    return {
        "title": "Personalized Clear Concert Bag with Name - "
                 "Stadium Approved Festival Purse",
        "tags": list(GOOD_TAGS),
        "description": "A clear stadium bag personalized with any name.",
        "supplier_status": "SUPPLIER_CONFIRMED",
        "supplier_record": {
            "last_verified": "2026-07-01",
            "product_url": "https://printify.com/app/products/1090",
            "supplier_catalog_url": "https://printify.com/catalog",
            "material": "clear TPU",
            "available_sizes": "one size",
            "base_cost": "8.50",
            "shipping_cost": "4.75",
            "processing_time": "3 days",
            "production_partner_required": "no",
            "seller_original_design_confirmed": "yes",
        },
        "tm_states": ["TM_VERIFIED_CLEAR"],
        "policy_violations": [],
        "audit_status": "COMPETITOR_AUDIT_OK",
        "primary_data_check": False,
        "cluster_has_flagged": False,
        "profit_model": {"net_profit": 8},
        "manual_review": "yes",
    }


def test_fully_evidenced_candidate_is_publish_ready():
    g = publish_gate(_ready_candidate())
    assert g["final_status"] == "PUBLISH_READY", g["blocked_by"]


def test_trademark_block_forces_blocked():
    c = _ready_candidate()
    c["tm_states"] = ["TM_BLOCKED"]
    g = publish_gate(c)
    assert g["final_status"] == "BLOCKED"
    assert "trademark_clear" in g["blocked_by"]


def test_missing_supplier_is_insufficient_data():
    c = _ready_candidate()
    c["supplier_status"] = "SUPPLIER_PARTIAL"
    c["supplier_record"] = {}
    g = publish_gate(c)
    assert g["final_status"] == "INSUFFICIENT_DATA"
    assert "supplier_confirmed" in g["blocked_by"]


def test_thin_margin_is_insufficient_data():
    c = _ready_candidate()
    c["profit_model"] = {"net_profit": 2}
    g = publish_gate(c)
    assert "profitability_verified" in g["blocked_by"]
    assert g["final_status"] != "PUBLISH_READY"


def test_placeholder_description_blocks_publish():
    c = _ready_candidate()
    c["description"] = "NEED_SUPPLIER_DETAILS material and size"
    g = publish_gate(c)
    assert "no_placeholders" in g["blocked_by"]


@pytest.mark.parametrize("required,disclosed,expected", [
    ("no", "", "NOT_REQUIRED"),
    ("yes", "yes", "REQUIRED_DISCLOSED"),
    ("yes", "no", "REQUIRED_NOT_DISCLOSED"),
    ("", "", "UNKNOWN_REVIEW_REQUIRED"),
])
def test_partner_status_four_states(required, disclosed, expected):
    assert partner_status({
        "production_partner_required": required,
        "production_partner_disclosed": disclosed,
    }) == expected


def test_run_harvest_summary_matches_return_dict(monkeypatch, tmp_path):
    """run_harvest's summary print must only use keys harvest() returns.
    Guards the KeyError class of bug (offline: the network pull is stubbed)."""
    import src.harvest as h
    monkeypatch.chdir(tmp_path)
    (tmp_path / "keywords.csv").write_text("keyword,competition\nfoo,\n",
                                           encoding="utf-8")

    def fake_pull(store, log=lambda s: None):
        store.update({
            "embroidered hat": {"tag": "embroidered hat", "score": 9.0,
                                "source": "trending", "listings": 5,
                                "sellers": 3, "comp": "low", "price": 20.0,
                                "conv": 0.03, "revenue": 100.0, "sold": 2,
                                "views": 300.0},
            "dad shirt": {"tag": "dad shirt", "score": 8.0,
                          "source": "opportunity", "listings": 9, "sellers": 4,
                          "comp": "low", "price": 18.0, "conv": 0.03,
                          "revenue": 90.0, "sold": 1, "views": 250.0},
        })
    monkeypatch.setattr(h, "_pull", fake_pull)

    s = h.run_harvest([])            # must NOT raise (KeyError etc.)
    assert s["wrote_data"] == 2
    for k in ("scanned", "new_total", "new_emb", "new_pod", "top_emb",
              "top_pod", "emb_sample", "pod_sample"):
        assert k in s
