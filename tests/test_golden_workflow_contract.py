"""Golden End-to-End Workflow Contract Test (P0-A.5 Audited Suite).

Verifies end-to-end data pipeline flow & P0-A.5 Root Cause Closure Rules:
1. Dynamic Runtime Fit Status Alignment: Exhaustively tests all product_fit statuses against create_master_keyword.
2. Value-Bound Product Truth Verification: ProductTruthFact.verified=True is required for physical copy rendering.
3. Content Identity vs Freshness Separation: retrieved_at alters observation_id but leaves content_hash & master revision unchanged.
4. Tag-Level Provenance Preservation: ListingCluster.supported_terms retains exact evidence_ref_ids for every tag.
5. Neutral Offer Semantics & Conditional Gift Photo Slot: Non-personalized items omit 'Custom'/'Personalized'; Gift slot is conditional on gift intent.
"""
import dataclasses
import socket
import pytest
from src import contracts, product_fit


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

    # Tag-Level Provenance Preservation Assertion!
    st_bag = next(st for st in cluster.supported_terms if st.term == "bridesmaid bag")
    assert st_bag.evidence_ref_ids == (ev1.provenance_hash,)

    pkg1 = contracts.compile_package(cluster)
    assert pkg1.network_calls_made == 0
    assert pkg1.publish_ready is False
    assert pkg1.price_fact.value is None

    # Simulate Full Verification with ProductTruthFact instances
    verified_checks = [
        contracts.OwnerCheck("Exact SKU / Supplier", "SUPPLIER", True, "VERIFIED_TEST_SKU"),
        contracts.OwnerCheck("Material Composition", "PRODUCT_TRUTH", True, "TEST_MATERIAL_CANVAS"),
        contracts.OwnerCheck("Dimensions & Sizing", "PRODUCT_TRUTH", True, "TEST_DIMENSIONS_15X16"),
        contracts.OwnerCheck("Available Color Palette", "PRODUCT_TRUTH", True, "TEST_COLORS_NATURAL"),
        contracts.OwnerCheck("Personalization Limits", "PRODUCT_TRUTH", True, "TEST_LIMIT_MAX12"),
        contracts.OwnerCheck("Design-Level IP QA", "IP_QA", True, "TEST_IP_QA_APPROVED")
    ]

    verified_ptruth_facts = [
        contracts.ProductTruthFact("material", "TEST_MATERIAL_CANVAS", True, "ev-1"),
        contracts.ProductTruthFact("dimensions", "TEST_DIMENSIONS_15X16", True, "ev-2"),
        contracts.ProductTruthFact("shipping", "TEST_SHIPPING_3DAYS", True, "ev-3"),
    ]
    price_fact = contracts.PriceFact(value=19.99, currency="USD", provenance_type="EXACT_LISTING", verified=True)

    pkg_ready = contracts.compile_package(
        cluster,
        owner_checks_override=verified_checks,
        product_truth_facts_override=verified_ptruth_facts,
        price_fact_override=price_fact
    )
    assert pkg_ready.publish_ready is True
    assert pkg_ready.price_fact.value == 19.99
    assert "Material: TEST_MATERIAL_CANVAS" in pkg_ready.buyer_copy


def test_exhaustive_product_fit_statuses_pass():
    """Verify that EVERY single status produced by src.product_fit compiles without error."""
    statuses = [
        product_fit.POD_FIT, product_fit.EMBROIDERY_FIT, product_fit.JEWELRY_FIT, product_fit.ACRYLIC_FIT,
        product_fit.DIGITAL_FIT, product_fit.SHOP_NAME_LIKELY, product_fit.POLICY_RISK, product_fit.TRADEMARK_RISK,
        product_fit.BROAD_SEED_ONLY, product_fit.NON_PRODUCT, product_fit.NEEDS_REVIEW, product_fit.THEME_FIT_READY,
        product_fit.THEME_FIT_NEEDS_PRODUCT, product_fit.AMBIGUOUS_PHRASE, product_fit.LOW_BUYER_INTENT,
        "NO_FIT", "BLOCKED", "NONE"
    ]
    for st in statuses:
        m = contracts.create_master_keyword(
            keyword="test keyword", mode="pod", opp_score=25.0, market_verdict="WATCH",
            fit_status=st, tm_risk="OK", engine_action="WATCH", execution_action="WATCH",
            specificity_class="SPECIFIC_ACTIONABLE"
        )
        assert m.product_fit_status == st


def test_content_identity_vs_freshness_observation():
    """Identical evidence facts fetched at a later retrieved_at share the SAME content_hash & Master revision."""
    ev_early = contracts.make_evidence_ref(
        source="ytrends_spy", retrieved_at="2026-08-15T10:00:00Z",
        match_type="EXACT", verdict="SELLING", raw_facts={"sold": 5}
    )
    ev_late = contracts.make_evidence_ref(
        source="ytrends_spy", retrieved_at="2026-08-15T18:00:00Z",
        match_type="EXACT", verdict="SELLING", raw_facts={"sold": 5}
    )

    # Content hashes MUST match!
    assert ev_early.provenance_hash == ev_late.provenance_hash
    # Observation IDs MUST be distinct (freshness metadata)!
    assert ev_early.observation_id != ev_late.observation_id

    # Master Keyword revision MUST remain stable across periodic freshness refreshes!
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

    assert m_early.revision_id == m_late.revision_id


def test_value_bound_product_truth_verification():
    """Physical claims render ONLY IF ProductTruthFact is explicitly verified."""
    master = contracts.create_master_keyword(
        keyword="school nurse shirt", mode="embroidery", opp_score=38.0,
        market_verdict="WATCH", fit_status="EMBROIDERY_FIT", tm_risk="OK",
        engine_action="CONFIRM_FIRST", execution_action="CONFIRM_FIRST",
        specificity_class="SPECIFIC_ACTIONABLE"
    )
    cluster = contracts.compile_cluster(master)

    # Unverified ProductTruthFact for material
    unverified_facts = [
        contracts.ProductTruthFact("material", "POLYESTER_BLEND", verified=False),
    ]
    pkg = contracts.compile_package(cluster, product_truth_facts_override=unverified_facts)

    # Must NOT render POLYESTER_BLEND because verified == False!
    assert "POLYESTER_BLEND" not in pkg.buyer_copy


def test_neutral_lead_and_conditional_gift_photo_slot():
    # 1. Non-gift non-personalized candidate (e.g. "school supply labels")
    m_labels = contracts.create_master_keyword(
        keyword="school supply labels", mode="pod", opp_score=30.0,
        market_verdict="WATCH", fit_status="POD_FIT", tm_risk="OK",
        engine_action="WATCH", execution_action="WATCH", specificity_class="SPECIFIC_ACTIONABLE"
    )
    c_labels = contracts.compile_cluster(m_labels)
    pkg_labels = contracts.compile_package(c_labels)

    # Lead sentence uses neutral wording (NO "Custom" or "Personalized")
    assert pkg_labels.buyer_copy.startswith("School Supply Labels — designed for")
    assert "Gift Context" not in pkg_labels.photo_brief

    # 2. Gift candidate ("bridesmaid bag")
    m_gift = contracts.create_master_keyword(
        keyword="bridesmaid bag", mode="pod", opp_score=45.0,
        market_verdict="WATCH", fit_status="POD_FIT", tm_risk="OK",
        engine_action="CONFIRM_FIRST", execution_action="CONFIRM_FIRST", specificity_class="SPECIFIC_ACTIONABLE"
    )
    c_gift = contracts.compile_cluster(m_gift)
    pkg_gift = contracts.compile_package(c_gift)

    # Gift photo slot MUST be present for bridesmaid gift concept!
    assert "Gift Context" in pkg_gift.photo_brief
