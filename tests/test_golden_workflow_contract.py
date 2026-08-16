"""Golden End-to-End Workflow Contract Test (P0-A.6).

Covers the final contract closure classes:
- exact ProductTruthFact/OwnerCheck binding
- OWNER_SET-only publish price
- stable content identity + multi-observation dedupe
- source-path term provenance retention
- neutral offer/gift semantics
- canonical product_fit status source
- duplicate Product Truth rejection
"""
import socket
import pytest
from src import contracts, product_fit


@pytest.fixture(autouse=True)
def block_network_access(monkeypatch):
    def _fail_on_connect(*args, **kwargs):
        raise RuntimeError("Network access attempted during offline contract compilation!")
    monkeypatch.setattr(socket, "create_connection", _fail_on_connect)
    monkeypatch.setattr(socket.socket, "connect", _fail_on_connect)


def _master(keyword="school nurse shirt", fit_status=product_fit.POD_FIT, evidence_refs=None):
    return contracts.create_master_keyword(
        keyword=keyword,
        mode="pod",
        opp_score=38.0,
        market_verdict="WATCH",
        fit_status=fit_status,
        tm_risk="OK",
        engine_action="CONFIRM_FIRST",
        execution_action="CONFIRM_FIRST",
        specificity_class="SPECIFIC_ACTIONABLE",
        evidence_refs=evidence_refs,
    )


def _verified_truth_bundle():
    facts = [
        contracts.ProductTruthFact("material", "TEST_CANVAS", True, "ptr-src-material"),
        contracts.ProductTruthFact("dimensions", "TEST_15X16", True, "ptr-src-dimensions"),
        contracts.ProductTruthFact("colors", "TEST_NATURAL", True, "ptr-src-colors"),
        contracts.ProductTruthFact("shipping", "TEST_3_DAYS", True, "ptr-src-shipping"),
    ]
    by_field = {f.field: f for f in facts}
    checks = [
        contracts.OwnerCheck("Exact SKU / Supplier", "SUPPLIER", True, "VERIFIED_TEST_SKU"),
        contracts.OwnerCheck("Material Composition", "PRODUCT_TRUTH", True, "verified exact material", by_field["material"].revision_id),
        contracts.OwnerCheck("Dimensions & Sizing", "PRODUCT_TRUTH", True, "verified exact dimensions", by_field["dimensions"].revision_id),
        contracts.OwnerCheck("Available Color Palette", "PRODUCT_TRUTH", True, "verified exact colors", by_field["colors"].revision_id),
        contracts.OwnerCheck("Shipping / Processing", "PRODUCT_TRUTH", True, "verified exact shipping", by_field["shipping"].revision_id),
        contracts.OwnerCheck("Design-Level IP QA", "IP_QA", True, "TEST_IP_QA_APPROVED"),
    ]
    return facts, checks


def test_golden_workflow_end_to_end_with_source_path_provenance():
    ev = contracts.make_evidence_ref(
        source="ytrends_spy_saved_shops",
        retrieved_at="2026-08-15T21:00:00Z",
        match_type="EXACT",
        verdict="SELLING",
        raw_facts={"raw_sold_24h": 12},
        term_source_paths=[
            ("bridesmaid bag", "rows[0].title"),
            ("bridesmaid tote", "rows[1].title"),
        ],
    )
    master = _master("bridesmaid bag", product_fit.POD_FIT, [ev])
    cluster = contracts.compile_cluster(master, [
        contracts.SupportedTerm(
            "bridesmaid bag", "EVIDENCE",
            (ev.provenance_hash,), ("rows[0].title",),
        )
    ])
    assert cluster.evidence_supported_tags == ("bridesmaid bag",)
    assert cluster.supported_terms[0].evidence_ref_ids == (ev.provenance_hash,)
    assert cluster.supported_terms[0].source_paths == ("rows[0].title",)

    facts, checks = _verified_truth_bundle()
    pkg = contracts.compile_package(
        cluster,
        owner_checks_override=checks,
        product_truth_facts_override=facts,
        price_fact_override=contracts.PriceFact(19.99, "usd", "OWNER_SET", True),
    )
    assert pkg.publish_ready is True
    assert pkg.price_fact.currency == "USD"
    assert "Material: TEST_CANVAS" in pkg.buyer_copy
    assert pkg.network_calls_made == 0


def test_product_truth_requires_provenance_and_exact_owner_binding():
    with pytest.raises(ValueError, match="requires provenance_ref"):
        contracts.ProductTruthFact("material", "COTTON", True, "")

    cluster = contracts.compile_cluster(_master())
    fact = contracts.ProductTruthFact("material", "VALUE_A", True, "ptr-src-a")
    wrong_fact = contracts.ProductTruthFact("material", "VALUE_B", True, "ptr-src-b")

    checks = [
        contracts.OwnerCheck("Material Composition", "PRODUCT_TRUTH", True, "approved A", fact.revision_id),
    ]
    pkg = contracts.compile_package(
        cluster,
        owner_checks_override=checks,
        product_truth_facts_override=[wrong_fact],
    )
    assert "VALUE_B" not in pkg.buyer_copy
    assert pkg.publish_ready is False


def test_publish_price_requires_owner_set_not_competitor_or_modeled_price():
    cluster = contracts.compile_cluster(_master())
    facts, checks = _verified_truth_bundle()

    competitor_price = contracts.PriceFact(19.99, "USD", "EXACT_LISTING", True)
    modeled_price = contracts.PriceFact(21.50, "USD", "MODELED", True)
    owner_price = contracts.PriceFact(22.00, "USD", "OWNER_SET", True)

    assert contracts.compile_package(cluster, checks, facts, competitor_price).publish_ready is False
    assert contracts.compile_package(cluster, checks, facts, modeled_price).publish_ready is False
    assert contracts.compile_package(cluster, checks, facts, owner_price).publish_ready is True


def test_same_content_multiple_observations_dedupe_to_latest_without_revision_churn():
    common = dict(
        source="ytrends_spy",
        match_type="EXACT",
        verdict="SELLING",
        raw_facts={"sold": 5},
        term_source_paths=[("grandpa golf", "rows[0].title")],
    )
    early = contracts.make_evidence_ref(retrieved_at="2026-08-15T10:00:00Z", **common)
    late = contracts.make_evidence_ref(retrieved_at="2026-08-15T18:00:00Z", **common)
    assert early.provenance_hash == late.provenance_hash
    assert early.observation_id != late.observation_id

    one = _master("grandpa golf", product_fit.THEME_FIT_NEEDS_PRODUCT, [early])
    both = _master("grandpa golf", product_fit.THEME_FIT_NEEDS_PRODUCT, [early, late])
    assert one.revision_id == both.revision_id
    assert len(both.evidence_refs) == 1
    assert both.evidence_refs[0].retrieved_at == late.retrieved_at


def test_term_source_path_must_match_evidence_relation():
    ev = contracts.make_evidence_ref(
        source="capture",
        retrieved_at="2026-08-16T00:00:00Z",
        match_type="EXACT",
        verdict="SELLING",
        term_source_paths=[("school nurse shirt", "rows[2].title")],
    )
    master = _master("school nurse shirt", product_fit.POD_FIT, [ev])
    wrong = contracts.SupportedTerm(
        "school nurse shirt", "EVIDENCE",
        (ev.provenance_hash,), ("rows[99].title",),
    )
    right = contracts.SupportedTerm(
        "school nurse shirt", "EVIDENCE",
        (ev.provenance_hash,), ("rows[2].title",),
    )
    assert contracts.compile_cluster(master, [wrong]).evidence_supported_tags == ()
    accepted = contracts.compile_cluster(master, [right])
    assert accepted.evidence_supported_tags == ("school nurse shirt",)


def test_neutral_role_does_not_invent_gift_semantics():
    nurse_cluster = contracts.compile_cluster(_master("school nurse shirt"))
    nurse_pkg = contracts.compile_package(nurse_cluster)
    assert nurse_pkg.title == "School Nurse Shirt"
    assert "Nurse Gift" not in nurse_pkg.title
    assert "Gift Context" not in nurse_pkg.photo_brief
    assert "Custom" not in nurse_pkg.buyer_copy
    assert "Personalized" not in nurse_pkg.buyer_copy

    wedding_cluster = contracts.compile_cluster(_master("wedding bridesmaid bag"))
    wedding_pkg = contracts.compile_package(wedding_cluster)
    assert "Gift Context" in wedding_pkg.photo_brief


def test_duplicate_or_invalid_product_truth_facts_are_rejected():
    with pytest.raises(ValueError, match="Invalid ProductTruthFact field"):
        contracts.ProductTruthFact("unknown_field", "X", False, "")

    cluster = contracts.compile_cluster(_master())
    dup = [
        contracts.ProductTruthFact("material", "A", False, ""),
        contracts.ProductTruthFact("material", "B", False, ""),
    ]
    with pytest.raises(ValueError, match="Duplicate ProductTruthFact fields"):
        contracts.compile_package(cluster, product_truth_facts_override=dup)


def test_product_fit_statuses_use_one_canonical_runtime_collection():
    assert set(product_fit.PRODUCT_FIT_STATUSES).issubset(contracts.VALID_FIT_STATUSES)
    for status in product_fit.PRODUCT_FIT_STATUSES:
        master = _master("test keyword", status)
        assert master.product_fit_status == status

    with pytest.raises(ValueError, match="Invalid product_fit_status"):
        _master("test keyword", "NEW_STATUS_NOT_IN_PRODUCT_FIT_SOURCE")
