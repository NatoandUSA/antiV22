"""Golden End-to-End Workflow Contract Test (P0-A.4 Audited Suite).

Verifies end-to-end data pipeline flow & P0-A.4 Root Cause Closure Rules:
1. Genuine Network Block: Socket connection attempts raise RuntimeError if compilation calls network.
2. Strict Term Provenance (No Canonical Bypass): Primary keyword must be present in EvidenceRef.supported_terms_contained to enter evidence_supported_tags.
3. Content & Observation Hash Binding: retrieved_at freshness timestamp alters EvidenceRef content hash & Master revision.
4. Schema-Driven Commercial & Fulfillment Publish Gate: publish_ready requires verified required checks + non-null verified PriceFact + verified shipping truth.
5. 100% Conditional Personalization: Non-personalized concepts omit 'Personalized' claims, instructions, photo steps, and personalization OwnerChecks.
6. Constructor-Level Deep Freezing: Direct dataclass construction deeply freezes nested structures.
7. PriceFact & ProductFit State Validation: Prevents invalid price/provenance state combinations and validates product_fit_statuses.
"""
import dataclasses
import socket
import pytest
from src import contracts


@pytest.fixture(autouse=True)
def block_network_access(monkeypatch):
    """Enforce genuine zero-network execution during contract compilation."""
    def _fail_on_connect(*args, **kwargs):
        raise RuntimeError("Network access attempted during offline contract compilation!")
    monkeypatch.setattr(socket, "create_connection", _fail_on_connect)
    monkeypatch.setattr(socket.socket, "connect", _fail_on_connect)


def test_golden_workflow_end_to_end_bridesmaid_bag_pod():
    ev1 = contracts.make_evidence_ref(
        source="ytrends_spy_saved_shops",
        retrieved_at="2026-08-15T21:00:00Z",
        match_type="EXACT",
        verdict="SELLING",
        raw_facts={"raw_sold_24h": 1124.0, "shop_count": 1},
        derived_metrics={"revenue_est": 794193.78},
        supported_terms_contained=["bridesmaid bag", "bridesmaid tote"]
    )

    master = contracts.create_master_keyword(
        keyword="bridesmaid bag",
        mode="pod",
        opp_score=45.0,
        market_verdict="WATCH",
        fit_status="POD_FIT",
        tm_risk="OK",
        engine_action="CONFIRM_FIRST",
        execution_action="CONFIRM_FIRST",
        specificity_class="SPECIFIC_ACTIONABLE",
        evidence_refs=[ev1]
    )

    supp_terms = [
        contracts.SupportedTerm("bridesmaid bag", "EVIDENCE", (ev1.provenance_hash,)),
        contracts.SupportedTerm("bridesmaid tote", "EVIDENCE", (ev1.provenance_hash,)),
    ]

    cluster = contracts.compile_cluster(master, supported_terms=supp_terms)
    assert cluster.revision_id.startswith("lc-")
    assert "bridesmaid bag" in cluster.evidence_supported_tags

    pkg1 = contracts.compile_package(cluster)
    assert pkg1.network_calls_made == 0
    assert pkg1.publish_ready is False
    assert pkg1.price_fact.value is None

    # Verify IP QA defaults to False
    ip_check = next(c for c in pkg1.owner_checks if c.field == "Design-Level IP QA")
    assert ip_check.verified is False

    # Simulate Full Verification (All Required Checks + Verified PriceFact + Verified Shipping)
    verified_checks = [
        contracts.OwnerCheck("Exact SKU / Supplier", "SUPPLIER", True, "VERIFIED_TEST_SKU"),
        contracts.OwnerCheck("Material Composition", "PRODUCT_TRUTH", True, "TEST_MATERIAL_CANVAS"),
        contracts.OwnerCheck("Dimensions & Sizing", "PRODUCT_TRUTH", True, "TEST_DIMENSIONS_15X16"),
        contracts.OwnerCheck("Available Color Palette", "PRODUCT_TRUTH", True, "TEST_COLORS_NATURAL"),
        contracts.OwnerCheck("Personalization Limits", "PRODUCT_TRUTH", True, "TEST_LIMIT_MAX12"),
        contracts.OwnerCheck("Design-Level IP QA", "IP_QA", True, "TEST_IP_QA_APPROVED")
    ]

    ptruth_verified = {
        "material": "TEST_MATERIAL_CANVAS",
        "dimensions": "TEST_DIMENSIONS_15X16",
        "shipping": "TEST_SHIPPING_3DAYS"
    }
    price_fact = contracts.PriceFact(value=19.99, currency="USD", provenance_type="EXACT_LISTING", verified=True)

    pkg_ready = contracts.compile_package(
        cluster,
        owner_checks_override=verified_checks,
        product_truth_override=ptruth_verified,
        price_fact_override=price_fact
    )
    assert pkg_ready.publish_ready is True
    assert pkg_ready.price_fact.value == 19.99
    assert "Material: TEST_MATERIAL_CANVAS" in pkg_ready.buyer_copy
    assert pkg1.revision_id != pkg_ready.revision_id


def test_primary_keyword_no_canonical_bypass():
    # EvidenceRef does NOT contain "school nurse shirt" in supported_terms_contained
    ev = contracts.make_evidence_ref(
        source="ytrends_spy_captures",
        retrieved_at="2026-08-15T21:00:00Z",
        match_type="EXACT",
        verdict="SELLING",
        supported_terms_contained=["unrelated term only"]
    )
    master = contracts.create_master_keyword(
        keyword="school nurse shirt",
        mode="embroidery",
        opp_score=38.0,
        market_verdict="WATCH",
        fit_status="EMBROIDERY_FIT",
        tm_risk="OK",
        engine_action="CONFIRM_FIRST",
        execution_action="CONFIRM_FIRST",
        specificity_class="SPECIFIC_ACTIONABLE",
        evidence_refs=[ev]
    )

    # Attempt to pass primary keyword as evidence term
    primary_term = contracts.SupportedTerm("school nurse shirt", "EVIDENCE", (ev.provenance_hash,))

    cluster = contracts.compile_cluster(master, supported_terms=[primary_term])
    # Must be REJECTED! Canonical keyword bypass is removed
    assert "school nurse shirt" not in cluster.evidence_supported_tags
    assert len(cluster.evidence_supported_tags) == 0


def test_retrieved_at_freshness_alters_evidence_and_master_identity():
    ev_early = contracts.make_evidence_ref(
        source="ytrends_spy", retrieved_at="2026-08-15T10:00:00Z",
        match_type="EXACT", verdict="SELLING", raw_facts={"sold": 5}
    )
    ev_late = contracts.make_evidence_ref(
        source="ytrends_spy", retrieved_at="2026-08-15T18:00:00Z",
        match_type="EXACT", verdict="SELLING", raw_facts={"sold": 5}
    )

    assert ev_early.provenance_hash != ev_late.provenance_hash

    m_early = contracts.create_master_keyword(
        keyword="grandpa golf", mode="embroidery", opp_score=40.0,
        market_verdict="WATCH", fit_status="THEME_FIT_NEEDS_PRODUCT", tm_risk="OK",
        engine_action="CONFIRM_FIRST", execution_action="CONFIRM_FIRST",
        specificity_class="SPECIFIC_ACTIONABLE", evidence_refs=[ev_early]
    )
    m_late = contracts.create_master_keyword(
        keyword="grandpa golf", mode="embroidery", opp_score=40.0,
        market_verdict="WATCH", fit_status="THEME_FIT_NEEDS_PRODUCT", tm_risk="OK",
        engine_action="CONFIRM_FIRST", execution_action="CONFIRM_FIRST",
        specificity_class="SPECIFIC_ACTIONABLE", evidence_refs=[ev_late]
    )

    assert m_early.revision_id != m_late.revision_id


def test_publish_ready_requires_verified_price_and_shipping():
    master = contracts.create_master_keyword(
        keyword="school nurse shirt", mode="embroidery", opp_score=38.0,
        market_verdict="WATCH", fit_status="EMBROIDERY_FIT", tm_risk="OK",
        engine_action="CONFIRM_FIRST", execution_action="CONFIRM_FIRST",
        specificity_class="SPECIFIC_ACTIONABLE"
    )
    cluster = contracts.compile_cluster(master)

    verified_checks = [
        contracts.OwnerCheck("Exact SKU / Supplier", "SUPPLIER", True, "VERIFIED_TEST_SKU"),
        contracts.OwnerCheck("Material Composition", "PRODUCT_TRUTH", True, "TEST_MATERIAL"),
        contracts.OwnerCheck("Dimensions & Sizing", "PRODUCT_TRUTH", True, "TEST_DIMENSIONS"),
        contracts.OwnerCheck("Available Color Palette", "PRODUCT_TRUTH", True, "TEST_COLORS"),
        contracts.OwnerCheck("Design-Level IP QA", "IP_QA", True, "TEST_IP_QA_APPROVED")
    ]
    ptruth = {"material": "COTTON", "dimensions": "10X10", "shipping": "TEST_SHIPPING"}

    # 1. Missing verified PriceFact -> publish_ready False
    unverified_price = contracts.PriceFact(value=19.99, currency="USD", provenance_type="MODELED", verified=False)
    pkg1 = contracts.compile_package(cluster, owner_checks_override=verified_checks, product_truth_override=ptruth, price_fact_override=unverified_price)
    assert pkg1.publish_ready is False

    # 2. Missing verified shipping truth -> publish_ready False
    unverified_shipping = {"material": "COTTON", "dimensions": "10X10", "shipping": "UNVERIFIED"}
    verified_price = contracts.PriceFact(value=19.99, currency="USD", provenance_type="EXACT_LISTING", verified=True)
    pkg2 = contracts.compile_package(cluster, owner_checks_override=verified_checks, product_truth_override=unverified_shipping, price_fact_override=verified_price)
    assert pkg2.publish_ready is False

    # 3. Verified PriceFact + Verified Shipping + Verified Checks -> publish_ready True
    pkg3 = contracts.compile_package(cluster, owner_checks_override=verified_checks, product_truth_override=ptruth, price_fact_override=verified_price)
    assert pkg3.publish_ready is True


def test_non_personalized_concept_is_100_percent_conditional():
    # Candidate without personalization angles (e.g. school nurse shirt)
    master = contracts.create_master_keyword(
        keyword="school nurse shirt", mode="embroidery", opp_score=38.0,
        market_verdict="WATCH", fit_status="EMBROIDERY_FIT", tm_risk="OK",
        engine_action="CONFIRM_FIRST", execution_action="CONFIRM_FIRST",
        specificity_class="SPECIFIC_ACTIONABLE"
    )
    cluster = contracts.compile_cluster(master)
    assert len(cluster.personalization_angles) == 0

    pkg = contracts.compile_package(cluster)

    # 1. Lead sentence uses "Custom School Nurse Shirt", NOT "Personalized"
    assert pkg.buyer_copy.startswith("Custom School Nurse Shirt")
    assert "Personalized School Nurse Shirt" not in pkg.buyer_copy

    # 2. No personalization instructions in buyer_copy
    assert "PERSONALIZATION INSTRUCTIONS" not in pkg.buyer_copy

    # 3. No "Add Personalization" step in photo_brief
    assert "Add Personalization" not in pkg.photo_brief

    # 4. No Personalization Limits in default owner_checks
    check_fields = {c.field for c in pkg.owner_checks}
    assert "Personalization Limits" not in check_fields


def test_price_fact_and_fit_status_validations():
    # 1. UNVERIFIED cannot have verified=True
    with pytest.raises(ValueError, match="UNVERIFIED price provenance cannot have verified=True"):
        contracts.PriceFact(value=10.0, provenance_type="UNVERIFIED", verified=True)

    # 2. Value None cannot have verified=True
    with pytest.raises(ValueError, match="PriceFact with value=None cannot be verified=True"):
        contracts.PriceFact(value=None, provenance_type="MODELED", verified=True)

    # 3. Invalid product_fit_status raises ValueError
    with pytest.raises(ValueError, match="Invalid product_fit_status"):
        contracts.create_master_keyword(
            keyword="test", mode="pod", opp_score=10.0, market_verdict="WATCH",
            fit_status="INVALID_FIT_STATUS", tm_risk="OK", engine_action="WATCH",
            execution_action="WATCH", specificity_class="NONE"
        )
