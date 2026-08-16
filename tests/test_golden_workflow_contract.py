"""Golden End-to-End Workflow Contract Test (P0-A.2 Audited Suite).

Verifies end-to-end data pipeline flow & P0-A.2 Integrity Rules:
1. Fake/Unresolved Evidence IDs: SupportedTerms carrying fake/unresolved evidence_ref_ids are strictly rejected.
2. Full Package Revision Identity: Material changes to Product Truth, Owner Checks, Photo Brief, or Price change revision_id.
3. Deep Immutability: Mutating nested dataclass attributes raises FrozenInstanceError.
4. Enum & Value Validation: Invalid match_types, verdicts, or OwnerCheck categories raise ValueError.
5. Truthful Metadata: created_at is omitted from decision revision hashing.
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
        evidence_refs=[ev2, ev1],
        created_at="2026-08-16T07:00:00Z"
    )

    # Prove created_at does NOT alter decision revision_id
    master_diff_time = contracts.create_master_keyword(
        keyword="bridesmaid bag",
        mode="pod",
        opp_score=45.0,
        market_verdict="WATCH",
        fit_status="POD_FIT",
        tm_risk="OK",
        engine_action="CONFIRM_FIRST",
        execution_action="CONFIRM_FIRST",
        specificity_class="SPECIFIC_ACTIONABLE",
        evidence_refs=[ev1, ev2],
        created_at="2026-08-16T09:00:00Z"
    )
    assert master.revision_id == master_diff_time.revision_id
    assert master.canonical_keyword == "bridesmaid bag"

    # Valid supported terms matching master's evidence IDs
    supp_terms = [
        contracts.SupportedTerm("bridesmaid bag", "EVIDENCE", ("ev-hash-12345",)),
        contracts.SupportedTerm("bridesmaid tote", "EVIDENCE", ("ev-hash-12345",)),
        contracts.SupportedTerm("bridal bag", "EVIDENCE", ("ev-hash-67890",)),
    ]

    cluster = contracts.compile_cluster(master, supported_terms=supp_terms)
    assert cluster.revision_id.startswith("lc-")
    assert "bridesmaid bag" in cluster.evidence_supported_tags
    assert "bridesmaid tote" in cluster.evidence_supported_tags
    assert "bridal bag" in cluster.evidence_supported_tags

    pkg1 = contracts.compile_package(cluster)
    assert pkg1.network_calls_made == 0

    pkg2 = contracts.compile_package(cluster)
    assert pkg1.revision_id == pkg2.revision_id
    assert pkg1.to_deterministic_dict() == pkg2.to_deterministic_dict()

    assert pkg1.price is None
    assert pkg1.publish_ready is False
    assert "[DATA UNAVAILABLE — OWNER CHECK]" not in pkg1.buyer_copy

    # Verify IP QA defaults to False
    ip_check = next(c for c in pkg1.owner_checks if c.field == "Design-Level IP QA")
    assert ip_check.verified is False

    # Simulate Verification with synthetic test values
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
        product_truth_override=ptruth_verified,
        price_override=24.99
    )
    assert pkg_ready.publish_ready is True
    assert pkg_ready.price == 24.99
    assert "Material: TEST_MATERIAL_CANVAS" in pkg_ready.buyer_copy

    # Full Revision Identity Assertion: Changing Product Truth or Price MUST change package revision_id!
    assert pkg1.revision_id != pkg_ready.revision_id


def test_unresolved_fake_evidence_id_is_rejected():
    ev = contracts.EvidenceRef(
        source="ytrends_spy_captures",
        retrieved_at="2026-08-15T21:00:00Z",
        provenance_hash="real-hash-111",
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

    # SupportedTerm with a FAKE evidence_ref_id that is NOT in master's evidence set
    fake_term = contracts.SupportedTerm("fake nurse tee", "EVIDENCE", ("fake-unresolved-hash-999",))
    real_term = contracts.SupportedTerm("school nurse shirt", "EVIDENCE", ("real-hash-111",))

    cluster = contracts.compile_cluster(master, supported_terms=[fake_term, real_term])

    # Assert fake_term was REJECTED while real_term was ACCEPTED
    assert "school nurse shirt" in cluster.evidence_supported_tags
    assert "fake nurse tee" not in cluster.evidence_supported_tags
    assert len(cluster.evidence_supported_tags) == 1


def test_deep_immutability_and_enum_validations():
    ev = contracts.EvidenceRef(
        source="ytrends_spy_captures",
        retrieved_at="2026-08-15T21:00:00Z",
        provenance_hash="hash-123",
        match_type="EXACT",
        verdict="SELLING"
    )

    # 1. Invalid enum validations raise ValueError
    with pytest.raises(ValueError, match="Invalid match_type"):
        contracts.EvidenceRef("src", "now", "h1", "INVALID_MATCH", "SELLING")

    with pytest.raises(ValueError, match="Invalid verdict"):
        contracts.EvidenceRef("src", "now", "h1", "EXACT", "INVALID_VERDICT")

    with pytest.raises(ValueError, match="Invalid OwnerCheck category"):
        contracts.OwnerCheck("field", "INVALID_CATEGORY")

    # 2. Deep Immutability Check (dataclass & nested tuple immutability)
    master = contracts.create_master_keyword(
        keyword="grandpa golf",
        mode="embroidery",
        opp_score=40.0,
        market_verdict="WATCH",
        fit_status="THEME_FIT_NEEDS_PRODUCT",
        tm_risk="OK",
        engine_action="CONFIRM_FIRST",
        execution_action="CONFIRM_FIRST",
        specificity_class="SPECIFIC_ACTIONABLE",
        evidence_refs=[ev]
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        master.keyword = "hacked"

    cluster = contracts.compile_cluster(master)
    pkg = contracts.compile_package(cluster)

    with pytest.raises(dataclasses.FrozenInstanceError):
        pkg.owner_checks[0].verified = True
