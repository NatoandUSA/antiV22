"""Golden End-to-End Workflow Contract Test (P0-A Audited Suite).

Verifies end-to-end data pipeline flow:
  Stored Evidence -> EvidenceRef -> MasterKeyword -> ListingCluster -> ListingPackage -> Photo Brief -> Owner Checks -> Publish Readiness

Acceptance Criteria Verified:
1. Genuine Network Block: Socket connection attempts raise RuntimeError if compilation calls network.
2. 100% Deterministic: Same frozen cluster revision -> exact same output hash (excluding volatile timestamps).
3. No Fake Price: Missing price remains None.
4. No Invented Tags: Explicit separation of evidence_tags and tag_gaps.
5. No Leaked Facts: Unverified materials/dimensions/colors kept out of customer copy.
6. Derived publish_ready: Property computed strictly from owner_checks (not a mutable boolean).
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
    # 1. EvidenceRef with explicit raw_facts vs derived_metrics
    ev = contracts.EvidenceRef(
        source="ytrends_spy_saved_shops",
        retrieved_at="2026-08-15T21:00:00Z",
        provenance_hash="ev-hash-12345",
        match_type="EXACT",
        verdict="SELLING",
        raw_facts={"raw_sold_24h": 1124.0, "shop_count": 1, "listing_ids": [98765]},
        derived_metrics={"revenue_est": 794193.78, "match_confidence": 1.0}
    )

    # 2. Reproducible MasterKeyword decision record
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
        evidence=ev
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
        evidence=ev
    )
    assert master.revision_id == master2.revision_id
    assert master.canonical_keyword == "bridesmaid bag"

    # 3. Compile ListingCluster revision
    cluster = contracts.compile_cluster(master)
    assert cluster.revision_id.startswith("lc-")
    assert cluster.master_revision_id == master.revision_id
    assert "bag" in cluster.product_nouns
    assert "bridesmaid" in cluster.buyer_roles
    assert all(len(t) <= 20 for t in cluster.evidence_supported_tags)

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
    assert isinstance(pkg1.evidence_tags, list)
    assert isinstance(pkg1.tag_gaps, list)
    assert len(pkg1.evidence_tags) + len(pkg1.tag_gaps) == 13

    # Rule 5: Unverified product facts stay out of customer copy
    assert "[DATA UNAVAILABLE — OWNER CHECK]" in pkg1.description
    assert "[RENDER ONLY AFTER PRODUCT TRUTH VERIFIED]" in pkg1.photo_brief

    # Rule 6: Supplier unselected -> draft text generates
    assert len(pkg1.title) > 0
    assert len(pkg1.description) > 0

    # Rule 7: Derived publish_ready is False when Owner Checks are unverified
    assert pkg1.publish_ready is False

    # 5. Simulate Owner Checks Verification -> Publish Readiness
    verified_checks = [
        contracts.OwnerCheck("Exact SKU / Supplier", "SUPPLIER", True, "Printify Monster Digital Tote"),
        contracts.OwnerCheck("Material Composition", "PRODUCT_TRUTH", True, "100% 12oz Cotton Canvas"),
        contracts.OwnerCheck("Dimensions & Sizing", "PRODUCT_TRUTH", True, '15" x 16" with 20" handles'),
        contracts.OwnerCheck("Available Color Palette", "PRODUCT_TRUTH", True, "Natural Off-White, Black"),
        contracts.OwnerCheck("Personalization Limits", "PRODUCT_TRUTH", True, "Max 12 characters"),
        contracts.OwnerCheck("Design-Level IP QA", "IP_QA", True, "Keyword level TM clean")
    ]

    pkg_ready = contracts.compile_package(cluster, owner_checks_override=verified_checks)
    assert pkg_ready.publish_ready is True


def test_mode_neutrality_embroidery_school_nurse_shirt():
    ev = contracts.EvidenceRef(
        source="ytrends_spy_captures",
        retrieved_at="2026-08-15T21:00:00Z",
        provenance_hash="ev-hash-67890",
        match_type="GROUP",
        verdict="SELLING",
        raw_facts={"raw_sold_24h": 69.0, "shop_count": 1},
        derived_metrics={"revenue_est": 297.94}
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
        evidence=ev
    )

    cluster = contracts.compile_cluster(master)
    assert cluster.mode == "embroidery"
    assert "shirt" in cluster.product_nouns
    assert "nurse" in cluster.buyer_roles

    pkg = contracts.compile_package(cluster)
    assert pkg.network_calls_made == 0
    assert pkg.publish_ready is False
    assert pkg.price is None
