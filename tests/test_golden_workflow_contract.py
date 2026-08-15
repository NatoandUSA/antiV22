"""Golden End-to-End Workflow Contract Test (P0-A.1 Audited Suite).

Verifies end-to-end data pipeline flow:
  Stored Evidence -> EvidenceRef -> MasterKeyword -> ListingCluster -> ListingPackage -> Photo Brief -> Owner Checks -> Publish Readiness

Acceptance Criteria & Hardened Rules Verified:
1. Genuine Network Block: Socket connection attempts raise RuntimeError if compilation calls network.
2. Provenance-Backed Tags: ONLY terms linked to EvidenceRef (origin_type == "EVIDENCE") populate evidence_supported_tags.
3. Design-Level IP QA Gate: Defaults to verified = False. Keyword TM cleanliness DOES NOT satisfy design-level IP QA.
4. Contract Immutability: Mutating a frozen dataclass raises FrozenInstanceError.
5. Clean Customer Copy: buyer_copy contains NO internal operator placeholders ([DATA UNAVAILABLE] lines are omitted).
6. Multi-EvidenceRef Canonical Hashing: create_master_keyword deduplicates and sorts multi-source EvidenceRefs.
7. Mode Neutrality: Evaluates both POD and Embroidery candidates cleanly.
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
    # 1. Multi-EvidenceRefs with raw_facts vs derived_metrics
    ev1 = contracts.EvidenceRef(
        source="ytrends_spy_saved_shops",
        retrieved_at="2026-08-15T21:00:00Z",
        provenance_hash="ev-hash-12345",
        match_type="EXACT",
        verdict="SELLING",
        raw_facts=(("raw_sold_24h", 1124.0), ("shop_count", 1)),
        derived_metrics=(("revenue_est", 794193.78), ("match_confidence", 1.0))
    )
    ev2 = contracts.EvidenceRef(
        source="ytrends_spy_captures",
        retrieved_at="2026-08-15T21:05:00Z",
        provenance_hash="ev-hash-67890",
        match_type="EXACT",
        verdict="SELLING",
        raw_facts=(("raw_sold_24h", 50.0),),
        derived_metrics=(("revenue_est", 1200.0),)
    )

    # 2. Reproducible MasterKeyword decision record with multi-EvidenceRef
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
        evidence_refs=[ev2, ev1]  # Passed in reverse order to test sorting/deduping
    )

    # Verify deterministic revision ID (excludes wall-clock randomness)
    master2 = contracts.create_master_keyword(
        keyword="bridesmaid bag",
        mode="pod",
        opp_score=45.0,
        market_verdict="WATCH",
        fit_status="POD_FIT",
        tm_risk="OK",
        engine_action="CONFIRM_FIRST",
        execution_action="CONFIRM_FIRST",
        specificity_class="SPECIFIC_ACTIONABLE",
        evidence_refs=[ev1, ev2]
    )
    assert master.revision_id == master2.revision_id
    assert master.canonical_keyword == "bridesmaid bag"
    assert len(master.evidence_refs) == 2

    # 3. Provenance-backed SupportedTerms
    supp_terms = [
        contracts.SupportedTerm("bridesmaid bag", "EVIDENCE", ("ev-hash-12345",)),
        contracts.SupportedTerm("bridesmaid tote", "EVIDENCE", ("ev-hash-12345",)),
        contracts.SupportedTerm("bridal bag", "EVIDENCE", ("ev-hash-67890",)),
    ]

    cluster = contracts.compile_cluster(master, supported_terms=supp_terms)
    assert cluster.revision_id.startswith("lc-")
    assert cluster.master_revision_id == master.revision_id
    assert "bridesmaid bag" in cluster.evidence_supported_tags
    assert "bridesmaid tote" in cluster.evidence_supported_tags
    assert "bridal bag" in cluster.evidence_supported_tags
    # Ensure unbacked semantic tokens like "custom text" are NOT in evidence_supported_tags
    assert "custom text" not in cluster.evidence_supported_tags

    # 4. Compile ListingPackage (Acceptance Criteria Assertions)
    pkg1 = contracts.compile_package(cluster)

    # Rule 1: Zero network calls
    assert pkg1.network_calls_made == 0

    # Rule 2: Deterministic output for same frozen cluster
    pkg2 = contracts.compile_package(cluster)
    assert pkg1.revision_id == pkg2.revision_id
    assert pkg1.to_deterministic_dict() == pkg2.to_deterministic_dict()

    # Rule 3: No synthetic price
    assert pkg1.price is None

    # Rule 4: Explicit separation of evidence_tags and tag_gaps
    assert isinstance(pkg1.evidence_tags, tuple)
    assert isinstance(pkg1.tag_gaps, tuple)
    assert len(pkg1.evidence_tags) + len(pkg1.tag_gaps) == 13

    # Rule 5: Clean buyer_copy has NO internal operator placeholders
    assert "[DATA UNAVAILABLE — OWNER CHECK]" not in pkg1.buyer_copy
    assert "[DATA UNAVAILABLE]" not in pkg1.buyer_copy

    # Rule 6: Supplier unselected -> draft text generates
    assert len(pkg1.title) > 0
    assert len(pkg1.buyer_copy) > 0

    # Rule 7: Design-Level IP QA defaults to verified = False -> publish_ready == False
    assert pkg1.publish_ready is False
    ip_check = next(c for c in pkg1.owner_checks if c["field"] == "Design-Level IP QA")
    assert ip_check["verified"] is False

    # 5. Simulate Verified Product Truth & IP QA using synthetic test values
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
        "dimensions": "TEST_DIMENSIONS_15X16"
    }

    pkg_ready = contracts.compile_package(
        cluster,
        owner_checks_override=verified_checks,
        product_truth_override=ptruth_verified
    )
    assert pkg_ready.publish_ready is True
    assert "Material: TEST_MATERIAL_CANVAS" in pkg_ready.buyer_copy


def test_contract_immutability_raises_frozen_error():
    ev = contracts.EvidenceRef(
        source="ytrends_spy_captures",
        retrieved_at="2026-08-15T21:00:00Z",
        provenance_hash="ev-hash-67890",
        match_type="EXACT",
        verdict="SELLING"
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

    # Immutability Check: Mutation must raise FrozenInstanceError
    with pytest.raises(dataclasses.FrozenInstanceError):
        master.keyword = "hacked keyword"

    cluster = contracts.compile_cluster(master)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cluster.primary_keyword = "hacked primary"

    pkg = contracts.compile_package(cluster)
    with pytest.raises(dataclasses.FrozenInstanceError):
        pkg.title = "hacked title"


def test_negative_derived_terms_cannot_enter_evidence_supported_tags():
    master = contracts.create_master_keyword(
        keyword="grandpa golf",
        mode="embroidery",
        opp_score=40.0,
        market_verdict="WATCH",
        fit_status="THEME_FIT_NEEDS_PRODUCT",
        tm_risk="OK",
        engine_action="CONFIRM_FIRST",
        execution_action="CONFIRM_FIRST",
        specificity_class="SPECIFIC_ACTIONABLE"
    )

    # Pass unsupported semantic term (origin_type == "SEMANTIC_INTENT")
    semantic_term = contracts.SupportedTerm("golf dad hat", "SEMANTIC_INTENT", ())

    cluster = contracts.compile_cluster(master, supported_terms=[semantic_term])

    # Assert semantic term did NOT leak into evidence_supported_tags!
    assert "golf dad hat" not in cluster.evidence_supported_tags
    assert len(cluster.evidence_supported_tags) == 0
    assert cluster.tag_gap_count == 13
