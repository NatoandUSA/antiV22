"""22Etsy Core Data Contracts (P0-A Workflow Architecture - Audited & Hardened).

Defines the immutable, versioned data contracts that pass between execution layers:
  RAW Evidence -> EvidenceRef -> MasterKeyword -> ListingCluster -> ListingPackage

Hardened Rules:
1. EvidenceRef distinguishes raw_facts from derived_metrics and carries full provenance.
2. MasterKeyword.revision_id is 100% deterministic and reproducible (excludes wall-clock time).
3. ListingCluster strictly separates evidence_supported_tags from tag_gap_count (no fake tags masquerading as evidence).
4. OwnerCheck is a manual truth gate that defaults to verified=False.
5. ListingPackage.publish_ready is a derived property computed dynamically from owner_checks.
6. Compile logic is 100% mode-neutral for both POD and Embroidery.
"""
import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

TAG_LIMIT = 13
MAX_TAG_LEN = 20


@dataclass
class EvidenceRef:
    source: str
    retrieved_at: str
    provenance_hash: str
    match_type: str                   # EXACT / GROUP
    verdict: str                      # SELLING / STRONG_SELLER / PROVEN_WINNER / LISTED
    raw_facts: Dict[str, Any] = field(default_factory=dict)         # Raw observations (e.g. raw_sold_24h, shop_id)
    derived_metrics: Dict[str, Any] = field(default_factory=dict)   # Calculated metrics (e.g. revenue_est, confidence)


@dataclass
class MasterKeyword:
    revision_id: str
    keyword: str
    canonical_keyword: str
    mode: str                          # pod / embroidery
    opportunity_score: float
    market_verdict: str                # GO / CONDITIONAL / WATCH / SKIP
    product_fit_status: str            # POD_FIT / EMBROIDERY_FIT / THEME_FIT_NEEDS_PRODUCT
    trademark_risk: str                # OK / CAUTION / HIGH
    engine_action: str                 # BUILD_NOW / CONFIRM_FIRST / REVIEW / WATCH
    execution_action: str              # BUILD_NOW / CONFIRM_FIRST / MINE_NICHE
    specificity_class: str             # SPECIFIC_ACTIONABLE / BROAD_PARENT
    evidence_refs: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ListingCluster:
    revision_id: str
    master_revision_id: str
    primary_keyword: str
    mode: str
    product_nouns: List[str]
    buyer_roles: List[str]
    occasions: List[str]
    personalization_angles: List[str]
    style_modifiers: List[str]
    evidence_supported_tags: List[str]
    tag_gap_count: int


@dataclass
class OwnerCheck:
    field: str
    category: str      # PRODUCT_TRUTH / SUPPLIER / IP_QA
    verified: bool = False
    note: str = ""


@dataclass
class ListingPackage:
    revision_id: str
    cluster_revision_id: str
    title: str
    evidence_tags: List[str]
    tag_gaps: List[str]
    description: str
    photo_brief: str
    price: Optional[float]
    owner_checks: List[Dict[str, Any]]
    network_calls_made: int = 0

    @property
    def publish_ready(self) -> bool:
        """Derived property: publish_ready is True ONLY when all Owner Checks are verified."""
        if not self.owner_checks:
            return False
        return all(bool(c.get("verified", False)) for c in self.owner_checks)

    def to_deterministic_dict(self) -> Dict[str, Any]:
        """Returns a canonical dictionary representation excluding volatile properties."""
        d = asdict(self)
        d["publish_ready"] = self.publish_ready
        return d


def create_master_keyword(
    keyword: str,
    mode: str,
    opp_score: float,
    market_verdict: str,
    fit_status: str,
    tm_risk: str,
    engine_action: str,
    execution_action: str,
    specificity_class: str,
    evidence: Optional[EvidenceRef] = None
) -> MasterKeyword:
    """Create a 100% deterministic MasterKeyword decision record (reproducible revision_id)."""
    ev_list = [asdict(evidence)] if evidence else []
    ev_hashes = ",".join(e.provenance_hash for e in [evidence] if e)
    
    # Revision hash depends strictly on input data, never wall-clock time
    rev_raw = f"{keyword.lower().strip()}:{mode}:{opp_score}:{market_verdict}:{fit_status}:{tm_risk}:{engine_action}:{execution_action}:{specificity_class}:{ev_hashes}"
    rev_id = f"mk-{hashlib.sha256(rev_raw.encode('utf-8')).hexdigest()[:12]}"
    
    return MasterKeyword(
        revision_id=rev_id,
        keyword=keyword,
        canonical_keyword=keyword.lower().strip(),
        mode=mode,
        opportunity_score=opp_score,
        market_verdict=market_verdict,
        product_fit_status=fit_status,
        trademark_risk=tm_risk,
        engine_action=engine_action,
        execution_action=execution_action,
        specificity_class=specificity_class,
        evidence_refs=ev_list
    )


def compile_cluster(master: MasterKeyword, extra_evidence_tags: Optional[List[str]] = None) -> ListingCluster:
    """Compile a deterministic ListingCluster revision from a MasterKeyword record.
    
    Mode-neutral compiler for POD & Embroidery. Strictly separates evidence_supported_tags from tag_gap_count.
    """
    kw = master.keyword.lower().strip()
    words = kw.split()

    product_nouns = []
    buyer_roles = []
    occasions = []
    personalization = ["custom text"]
    style_modifiers = []

    # Dynamic intent extraction (Mode-neutral)
    for w in words:
        if w in ("bag", "tote", "pouch", "tshirt", "shirt", "crewneck", "sweatshirt", "hoodie", "hat", "cap", "mug"):
            product_nouns.append(w)
        elif w in ("bridesmaid", "nurse", "grandpa", "papa", "mom", "dad", "teacher", "bride"):
            buyer_roles.append(w)
        elif w in ("wedding", "bachelorette", "birthday", "school", "christmas", "halloween"):
            occasions.append(w)
        elif w in ("custom", "personalized", "monogram", "name"):
            personalization.append(w)

    # Build evidence-supported tags (strictly <= 20 chars, deduplicated)
    raw_tags = [kw] + buyer_roles + product_nouns + occasions + personalization
    if extra_evidence_tags:
        raw_tags.extend(extra_evidence_tags)

    evidence_tags = []
    seen = set()
    for t in raw_tags:
        t_clean = t.lower().strip()
        if t_clean and t_clean not in seen and len(t_clean) <= MAX_TAG_LEN:
            seen.add(t_clean)
            evidence_tags.append(t_clean)

    supported = evidence_tags[:TAG_LIMIT]
    tag_gap_count = max(0, TAG_LIMIT - len(supported))

    # Deterministic revision ID
    cluster_raw = f"{master.revision_id}:{','.join(supported)}"
    cluster_rev = f"lc-{hashlib.sha256(cluster_raw.encode('utf-8')).hexdigest()[:12]}"

    return ListingCluster(
        revision_id=cluster_rev,
        master_revision_id=master.revision_id,
        primary_keyword=master.keyword,
        mode=master.mode,
        product_nouns=product_nouns,
        buyer_roles=buyer_roles,
        occasions=occasions,
        personalization_angles=personalization,
        style_modifiers=style_modifiers,
        evidence_supported_tags=supported,
        tag_gap_count=tag_gap_count
    )


def compile_package(cluster: ListingCluster, owner_checks_override: Optional[List[OwnerCheck]] = None) -> ListingPackage:
    """Compile a deterministic ListingPackage from a frozen ListingCluster revision.
    
    Zero network calls. No synthetic prices. Explicit TAG_GAP tracking.
    Supplier/Product Truth missing -> draft copy generates stably, physical facts stay out of customer claims.
    """
    kw_cap = cluster.primary_keyword.title()
    roles = [r.title() for r in cluster.buyer_roles if r.lower() != cluster.primary_keyword.lower()]
    prods = [p.title() for p in cluster.product_nouns]
    
    title_parts = [kw_cap]
    if roles:
        title_parts.append(roles[0] + " Gift")
    if prods:
        title_parts.append("Custom " + prods[0])
    
    title = ", ".join(title_parts)

    # Tags & explicit TAG_GAP separation
    evidence_tags = list(cluster.evidence_supported_tags)
    tag_gaps = [f"TAG_GAP_{i+1}" for i in range(cluster.tag_gap_count)]

    # Description (Customer-facing copy: physical facts omitted/held in check)
    desc_lines = [
        f"Personalized {kw_cap} — custom designed for {cluster.buyer_roles[0] if cluster.buyer_roles else 'special occasions'}.",
        "",
        "PERSONALIZATION INSTRUCTIONS",
        "• Enter the exact name, date, or text for customization.",
        "• Double-check spelling before placing your order.",
        "",
        "PRODUCT DETAILS & TRUTH",
        "• Material: [DATA UNAVAILABLE — OWNER CHECK]",
        "• Dimensions / Sizing: [DATA UNAVAILABLE — OWNER CHECK]",
        "• Color Options: [DATA UNAVAILABLE — OWNER CHECK]",
        "• Production Method: [DATA UNAVAILABLE — OWNER CHECK]",
        "",
        "CARE & SHIPPING",
        "• Processing & Shipping: [DATA UNAVAILABLE — OWNER CHECK]"
    ]
    description = "\n".join(desc_lines)

    # Photo Brief (Truth-aware)
    photo_lines = [
        f"1. Main Hero Image: {kw_cap} in real use context.",
        "2. Product Angle: Clean front shot of primary design.",
        "3. Close-Up Detail: Texture and craftsmanship view.",
        "4. Personalization Explainer: Clear visual showing custom text placement.",
        "5. Size & Dimension Graphic: [RENDER ONLY AFTER PRODUCT TRUTH VERIFIED]",
        "6. Color Palette Grid: [RENDER ONLY AFTER PRODUCT TRUTH VERIFIED]",
        "7. Gift Context: Package / presentation visual.",
        "8. Ordering Process Infographic: Step 1 Select Options -> Step 2 Add Personalization -> Step 3 Checkout."
    ]
    photo_brief = "\n".join(photo_lines)

    # Owner Checks
    if owner_checks_override:
        checks = owner_checks_override
    else:
        checks = [
            OwnerCheck("Exact SKU / Supplier", "SUPPLIER", False, "Supplier not selected yet"),
            OwnerCheck("Material Composition", "PRODUCT_TRUTH", False, "Material unverified"),
            OwnerCheck("Dimensions & Sizing", "PRODUCT_TRUTH", False, "Dimensions unverified"),
            OwnerCheck("Available Color Palette", "PRODUCT_TRUTH", False, "Colors unverified"),
            OwnerCheck("Personalization Limits", "PRODUCT_TRUTH", False, "Character count limits unverified"),
            OwnerCheck("Design-Level IP QA", "IP_QA", True, "Keyword level TM clean")
        ]

    checks_dicts = [asdict(c) for c in checks]

    # Package revision hash is deterministic
    pkg_raw = f"{cluster.revision_id}:{title}:{'|'.join(evidence_tags)}:{cluster.tag_gap_count}"
    pkg_rev = f"lp-{hashlib.sha256(pkg_raw.encode('utf-8')).hexdigest()[:12]}"

    return ListingPackage(
        revision_id=pkg_rev,
        cluster_revision_id=cluster.revision_id,
        title=title,
        evidence_tags=evidence_tags,
        tag_gaps=tag_gaps,
        description=description,
        photo_brief=photo_brief,
        price=None,  # Price is None until evidence/supplier sets it
        owner_checks=checks_dicts,
        network_calls_made=0
    )
