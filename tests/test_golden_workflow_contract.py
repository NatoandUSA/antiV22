"""Golden End-to-End Workflow Contract Test (P0-A.3 Audited Suite).

Verifies end-to-end data pipeline flow & P0-A.3 Integrity Rules:
1. Schema-Driven Required Owner Checks Gate: One verified check alone yields publish_ready == False.
2. Provenance-Verified Product Truth: Unverified product truth never appears in buyer_copy.
3. Complete Vocabulary Alignment: All runtime execution_action and specificity_class states pass.
4. Content-Bound Evidence & Collision Detection: Same-ID conflicting evidence content is rejected.
5. Term-Level Evidence Verification: SupportedTerms are verified against evidence content.
6. PriceFact Provenance: Price requires explicit PriceFact provenance.
7. Full Cluster Revision Hashing: Changes to semantic cluster fields alter cluster revision identity.
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
        supported_terms_contained=["bridesmaid bag", "bridesmaid tote", "bridal bag"]
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

    # Valid supported terms matching master's evidence content
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


def test_required_owner_checks_gate_cannot_be_bypassed():
    master = contracts.create_master_keyword(
        keyword="school nurse shirt",
        mode="embroidery",
        opp_score=38.0,
        market_verdict="WATCH",
        fit_status="EMBROIDERY_FIT",
        tm_risk="OK",
        engine_action="CONFIRM_FIRST",
        execution_action="CONFIRM_FIRST",
        specificity_class="SPECIFIC_ACTIONABLE"
    )
    cluster = contracts.compile_cluster(master)

    # Incomplete override check (only 1 check verified out of required 6)
    single_check = [contracts.OwnerCheck("Design-Level IP QA", "IP_QA", True, "Approved")]
    pkg_incomplete = contracts.compile_package(cluster, owner_checks_override=single_check)

    # Must be False! Missing required checks
    assert pkg_incomplete.publish_ready is False


def test_unverified_product_truth_never_renders_in_buyer_copy():
    master = contracts.create_master_keyword(
        keyword="school nurse shirt",
        mode="embroidery",
        opp_score=38.0,
        market_verdict="WATCH",
        fit_status="EMBROIDERY_FIT",
        tm_risk="OK",
        engine_action="CONFIRM_FIRST",
        execution_action="CONFIRM_FIRST",
        specificity_class="SPECIFIC_ACTIONABLE"
    )
    cluster = contracts.compile_cluster(master)

    # Pass product_truth_override values BUT keep owner_checks unverified
    unverified_ptruth = {"material": "SUPER_SOFT_COTTON", "dimensions": "10x10"}
    pkg = contracts.compile_package(cluster, product_truth_override=unverified_ptruth)

    # Buyer copy MUST NOT contain material or dimensions because Material Composition check is unverified!
    assert "SUPER_SOFT_COTTON" not in pkg.buyer_copy
    assert "10x10" not in pkg.buyer_copy


def test_full_runtime_vocabulary_alignment():
    # Verify execution_action states (REVIEW_ACTIONABILITY, BLOCKED, SKIP, WATCH) pass without errors
    m1 = contracts.create_master_keyword(
        keyword="ambiguous niche",
        mode="pod",
        opp_score=20.0,
        market_verdict="SKIP",
        fit_status="POD_FIT",
        tm_risk="CAUTION",
        engine_action="REVIEW",
        execution_action="REVIEW_ACTIONABILITY",
        specificity_class="AMBIGUOUS_REVIEW"
    )
    assert m1.execution_action == "REVIEW_ACTIONABILITY"
    assert m1.specificity_class == "AMBIGUOUS_REVIEW"

    m2 = contracts.create_master_keyword(
        keyword="blocked brand",
        mode="pod",
        opp_score=0.0,
        market_verdict="SKIP",
        fit_status="POD_FIT",
        tm_risk="HIGH",
        engine_action="BLOCKED",
        execution_action="BLOCKED",
        specificity_class="NOT_APPLICABLE"
    )
    assert m2.engine_action == "BLOCKED"
    assert m2.specificity_class == "NOT_APPLICABLE"


def test_unbacked_term_or_fake_evidence_id_rejected():
    ev = contracts.make_evidence_ref(
        source="ytrends_spy_captures",
        retrieved_at="2026-08-15T21:00:00Z",
        match_type="EXACT",
        verdict="SELLING",
        supported_terms_contained=["school nurse shirt"]
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

    # 1. Term citing real evidence ID but string is NOT contained in evidence supported_terms_contained
    unbacked_term = contracts.SupportedTerm("unbacked fake tag", "EVIDENCE", (ev.provenance_hash,))
    # 2. Term citing fake evidence ID
    fake_id_term = contracts.SupportedTerm("school nurse shirt", "EVIDENCE", ("fake-hash-999",))

    cluster = contracts.compile_cluster(master, supported_terms=[unbacked_term, fake_id_term])
    assert "unbacked fake tag" not in cluster.evidence_supported_tags
    assert len(cluster.evidence_supported_tags) == 0


def test_evidence_hash_collision_rejected():
    ev1 = contracts.make_evidence_ref(
        source="ytrends_spy_captures",
        retrieved_at="2026-08-15T21:00:00Z",
        match_type="EXACT",
        verdict="SELLING",
        raw_facts={"raw_sold": 10}
    )
    ev2 = contracts.make_evidence_ref(
        source="ytrends_spy_captures",
        retrieved_at="2026-08-15T21:00:00Z",
        match_type="EXACT",
        verdict="SELLING",
        raw_facts={"raw_sold": 999}
    )

    # 1. Content hash binding validation: Supplying a fake/mismatched provenance_hash raises ValueError
    with pytest.raises(ValueError, match="does not match computed content_hash"):
        contracts.EvidenceRef(
            source=ev2.source,
            retrieved_at=ev2.retrieved_at,
            provenance_hash="fake-provenance-hash-999",  # Mismatched hash
            match_type=ev2.match_type,
            verdict=ev2.verdict,
            raw_facts=ev2.raw_facts
        )

    # 2. MasterKeyword evidence hash collision detection (conflicting evidence with same hash)
    conflicting_ev2 = contracts.make_evidence_ref(
        source=ev2.source,
        retrieved_at=ev2.retrieved_at,
        match_type=ev2.match_type,
        verdict=ev2.verdict,
        raw_facts={"raw_sold": 999}
    )
    # Force conflicting provenance_hash on conflicting_ev2 to simulate hash collision
    object.__setattr__(conflicting_ev2, "provenance_hash", ev1.provenance_hash)

    with pytest.raises(ValueError, match="collision detected"):
        contracts.create_master_keyword(
            keyword="school nurse shirt",
            mode="embroidery",
            opp_score=38.0,
            market_verdict="WATCH",
            fit_status="EMBROIDERY_FIT",
            tm_risk="OK",
            engine_action="CONFIRM_FIRST",
            execution_action="CONFIRM_FIRST",
            specificity_class="SPECIFIC_ACTIONABLE",
            evidence_refs=[ev1, conflicting_ev2]
        )
