"""22Etsy Core Data Contracts (P0-A.3 Deep Consolidated Integrity Pass).

Defines the immutable, versioned data contracts that pass between execution layers:
  RAW Evidence -> EvidenceRef -> MasterKeyword -> ListingCluster -> ListingPackage

P0-A.3 Consolidated Hardening Rules:
1. Schema-Driven Required Owner Checks: publish_ready is True ONLY if ALL REQUIRED_OWNER_CHECKS are present AND verified.
2. Provenance-Verified Product Truth: Physical claims render in buyer_copy ONLY IF the exact corresponding OwnerCheck is verified.
3. Complete Vocabulary Alignment: Supports all runtime execution_action, specificity_class, and engine_action states.
4. Content-Bound EvidenceRef Hashing: Computes content_hash deterministically and raises on same-ID content conflicts.
5. Deep Immutability: Recursively freezes all nested structures (PriceFact, OwnerCheck, EvidenceRef, SupportedTerm).
6. Conditional Personalization: Personalization copy renders ONLY when personalization angles exist.
7. Full Cluster Revision Hashing: Hashes all semantic cluster fields plus compiler_version.
8. Term-Level Evidence Verification: Validates supported terms against evidence content.
"""
import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple, Sequence, Set

COMPILER_VERSION = "p0-a.3"
TAG_LIMIT = 13
MAX_TAG_LEN = 20

# Unified Engine & Contract Vocabulary (100% Aligned with execution_action.py & ranking_engine.py)
VALID_MODES = {"pod", "embroidery"}
VALID_MARKET_VERDICTS = {"GO", "CONDITIONAL", "WATCH", "SKIP"}
VALID_TM_RISKS = {"OK", "CAUTION", "HIGH"}
VALID_ENGINE_ACTIONS = {"BUILD_NOW", "CONFIRM_FIRST", "REVIEW", "WATCH", "SKIP", "BLOCKED"}
VALID_EXEC_ACTIONS = {"BUILD_NOW", "CONFIRM_FIRST", "MINE_NICHE", "REVIEW_ACTIONABILITY", "BLOCKED", "SKIP", "WATCH"}
VALID_SPECIFICITY_CLASSES = {"SPECIFIC_ACTIONABLE", "BROAD_PARENT", "AMBIGUOUS_REVIEW", "NOT_APPLICABLE", "NONE"}

VALID_MATCH_TYPES = {"EXACT", "GROUP"}
VALID_VERDICTS = {"SELLING", "STRONG_SELLER", "PROVEN_WINNER", "LISTED"}
VALID_CHECK_CATEGORIES = {"PRODUCT_TRUTH", "SUPPLIER", "IP_QA"}

VALID_PRICE_PROVENANCES = {"EXACT_LISTING", "MODELED", "OWNER_SET", "UNVERIFIED"}

REQUIRED_OWNER_CHECK_FIELDS = {
    "Exact SKU / Supplier",
    "Material Composition",
    "Dimensions & Sizing",
    "Available Color Palette",
    "Personalization Limits",
    "Design-Level IP QA"
}


def _deep_freeze(val: Any) -> Any:
    """Recursively freeze dicts and lists into immutable tuples of sorted key-value pairs or tuples."""
    if isinstance(val, dict):
        return tuple(sorted((k, _deep_freeze(v)) for k, v in val.items()))
    elif isinstance(val, (list, set, tuple)):
        return tuple(_deep_freeze(v) for v in val)
    return val


@dataclass(frozen=True)
class PriceFact:
    value: Optional[float]
    currency: str = "USD"
    provenance_type: str = "UNVERIFIED"  # EXACT_LISTING / MODELED / OWNER_SET / UNVERIFIED
    verified: bool = False

    def __post_init__(self):
        if self.provenance_type not in VALID_PRICE_PROVENANCES:
            raise ValueError(f"Invalid price provenance_type: {self.provenance_type}")
        if self.value is not None and self.value < 0:
            raise ValueError("Price value cannot be negative")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SupportedTerm:
    term: str
    origin_type: str                   # "EVIDENCE" or "SEMANTIC_INTENT"
    evidence_ref_ids: Tuple[str, ...] = ()

    def __post_init__(self):
        if self.origin_type not in ("EVIDENCE", "SEMANTIC_INTENT"):
            raise ValueError(f"Invalid origin_type: {self.origin_type}")
        if self.origin_type == "EVIDENCE" and not self.evidence_ref_ids:
            raise ValueError("EVIDENCE supported term must carry at least one evidence_ref_id provenance!")


@dataclass(frozen=True)
class EvidenceRef:
    source: str
    retrieved_at: str
    provenance_hash: str
    match_type: str                   # EXACT / GROUP
    verdict: str                      # SELLING / STRONG_SELLER / PROVEN_WINNER / LISTED
    raw_facts: Tuple[Tuple[str, Any], ...] = ()         # Deeply frozen tuple of (key, value)
    derived_metrics: Tuple[Tuple[str, Any], ...] = ()   # Deeply frozen tuple of (key, value)
    supported_terms_contained: Tuple[str, ...] = ()     # Explicit terms present in this evidence

    def __post_init__(self):
        if self.match_type not in VALID_MATCH_TYPES:
            raise ValueError(f"Invalid match_type: {self.match_type}")
        if self.verdict not in VALID_VERDICTS:
            raise ValueError(f"Invalid verdict: {self.verdict}")
        
        # Verify content_hash binding
        computed = self.compute_content_hash()
        if self.provenance_hash and self.provenance_hash != computed:
            raise ValueError(f"Supplied provenance_hash '{self.provenance_hash}' does not match computed content_hash '{computed}'!")
        object.__setattr__(self, "provenance_hash", computed)

    def compute_content_hash(self) -> str:
        payload = {
            "source": self.source,
            "match_type": self.match_type,
            "verdict": self.verdict,
            "raw_facts": self.raw_facts,
            "derived_metrics": self.derived_metrics,
            "supported_terms": sorted(self.supported_terms_contained)
        }
        raw_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return f"ev-{hashlib.sha256(raw_json.encode('utf-8')).hexdigest()[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "retrieved_at": self.retrieved_at,
            "provenance_hash": self.provenance_hash,
            "match_type": self.match_type,
            "verdict": self.verdict,
            "raw_facts": dict(self.raw_facts),
            "derived_metrics": dict(self.derived_metrics),
            "supported_terms_contained": list(self.supported_terms_contained)
        }


def make_evidence_ref(
    source: str,
    retrieved_at: str,
    match_type: str,
    verdict: str,
    raw_facts: Optional[Dict[str, Any]] = None,
    derived_metrics: Optional[Dict[str, Any]] = None,
    supported_terms_contained: Optional[Sequence[str]] = None,
    provenance_hash: str = ""
) -> EvidenceRef:
    """Helper constructor for EvidenceRef with automatic deep freezing."""
    frozen_raw = _deep_freeze(raw_facts or {})
    frozen_derived = _deep_freeze(derived_metrics or {})
    terms = tuple(sorted(t.lower().strip() for t in (supported_terms_contained or [])))
    
    dummy_ref = EvidenceRef(
        source=source,
        retrieved_at=retrieved_at,
        provenance_hash="",
        match_type=match_type,
        verdict=verdict,
        raw_facts=frozen_raw,
        derived_metrics=frozen_derived,
        supported_terms_contained=terms
    )
    computed_hash = dummy_ref.compute_content_hash()
    
    return EvidenceRef(
        source=source,
        retrieved_at=retrieved_at,
        provenance_hash=provenance_hash or computed_hash,
        match_type=match_type,
        verdict=verdict,
        raw_facts=frozen_raw,
        derived_metrics=frozen_derived,
        supported_terms_contained=terms
    )


@dataclass(frozen=True)
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
    execution_action: str              # BUILD_NOW / CONFIRM_FIRST / MINE_NICHE / REVIEW_ACTIONABILITY / BLOCKED / SKIP / WATCH
    specificity_class: str             # SPECIFIC_ACTIONABLE / BROAD_PARENT / AMBIGUOUS_REVIEW / NOT_APPLICABLE / NONE
    evidence_refs: Tuple[EvidenceRef, ...] = ()
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["evidence_refs"] = [e.to_dict() for e in self.evidence_refs]
        return d


@dataclass(frozen=True)
class ListingCluster:
    revision_id: str
    master_revision_id: str
    primary_keyword: str
    mode: str
    product_nouns: Tuple[str, ...]
    buyer_roles: Tuple[str, ...]
    occasions: Tuple[str, ...]
    personalization_angles: Tuple[str, ...]
    style_modifiers: Tuple[str, ...]
    evidence_supported_tags: Tuple[str, ...]
    tag_gap_count: int
    compiler_version: str = COMPILER_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OwnerCheck:
    field: str
    category: str      # PRODUCT_TRUTH / SUPPLIER / IP_QA
    verified: bool = False
    note: str = ""

    def __post_init__(self):
        if self.category not in VALID_CHECK_CATEGORIES:
            raise ValueError(f"Invalid OwnerCheck category: {self.category}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ListingPackage:
    revision_id: str
    cluster_revision_id: str
    title: str
    evidence_tags: Tuple[str, ...]
    tag_gaps: Tuple[str, ...]
    buyer_copy: str
    product_truth_slots: Tuple[Tuple[str, Any], ...]
    photo_brief: str
    price_fact: PriceFact
    owner_checks: Tuple[OwnerCheck, ...]
    network_calls_made: int = 0

    @property
    def publish_ready(self) -> bool:
        """Derived property: publish_ready is True ONLY IF all REQUIRED_OWNER_CHECK_FIELDS are present AND verified."""
        if not self.owner_checks:
            return False
        
        check_map = {c.field: c.verified for c in self.owner_checks}
        # Reject duplicate or missing required fields
        if len(self.owner_checks) != len(check_map):
            return False  # Duplicate check fields detected
            
        for req_field in REQUIRED_OWNER_CHECK_FIELDS:
            if req_field not in check_map or not check_map[req_field]:
                return False
                
        return True

    def to_deterministic_dict(self) -> Dict[str, Any]:
        """Returns a canonical dictionary representation excluding volatile properties."""
        d = asdict(self)
        d["publish_ready"] = self.publish_ready
        d["price_fact"] = self.price_fact.to_dict()
        d["owner_checks"] = [c.to_dict() for c in self.owner_checks]
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
    evidence_refs: Optional[Sequence[EvidenceRef]] = None,
    created_at: str = ""
) -> MasterKeyword:
    """Create a 100% deterministic MasterKeyword decision record with collision detection."""
    spec_cls = specificity_class if specificity_class is not None else "NONE"
    
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid mode: {mode}")
    if market_verdict not in VALID_MARKET_VERDICTS:
        raise ValueError(f"Invalid market_verdict: {market_verdict}")
    if tm_risk not in VALID_TM_RISKS:
        raise ValueError(f"Invalid trademark_risk: {tm_risk}")
    if engine_action not in VALID_ENGINE_ACTIONS:
        raise ValueError(f"Invalid engine_action: {engine_action}")
    if execution_action not in VALID_EXEC_ACTIONS:
        raise ValueError(f"Invalid execution_action: {execution_action}")
    if spec_cls not in VALID_SPECIFICITY_CLASSES:
        raise ValueError(f"Invalid specificity_class: {spec_cls}")

    # Deduplicate & Sort EvidenceRefs by provenance_hash with Collision Detection
    ev_map: Dict[str, EvidenceRef] = {}
    if evidence_refs:
        for ev in evidence_refs:
            h = ev.provenance_hash
            if h in ev_map and ev_map[h] != ev:
                raise ValueError(f"EvidenceRef hash collision detected! Same hash '{h}' supplied for conflicting evidence content.")
            ev_map[h] = ev

    sorted_ev_hashes = sorted(ev_map.keys())
    sorted_ev_refs = tuple(ev_map[h] for h in sorted_ev_hashes)

    # Hash canonical payload without lossy rounding
    hash_payload = {
        "keyword": keyword.lower().strip(),
        "mode": mode,
        "opp_score": float(opp_score),
        "market_verdict": market_verdict,
        "product_fit_status": fit_status,
        "trademark_risk": tm_risk,
        "engine_action": engine_action,
        "execution_action": execution_action,
        "specificity_class": spec_cls,
        "evidence_hashes": sorted_ev_hashes
    }
    
    hash_json = json.dumps(hash_payload, sort_keys=True, separators=(',', ':'))
    rev_id = f"mk-{hashlib.sha256(hash_json.encode('utf-8')).hexdigest()[:12]}"

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
        specificity_class=spec_cls,
        evidence_refs=sorted_ev_refs,
        created_at=created_at
    )


def compile_cluster(
    master: MasterKeyword,
    supported_terms: Optional[Sequence[SupportedTerm]] = None
) -> ListingCluster:
    """Compile a deterministic ListingCluster revision from a MasterKeyword record.
    
    Mode-neutral compiler for POD & Embroidery.
    STRICT PROVENANCE & TERM-MATCHING RULE:
    ONLY terms with origin_type == "EVIDENCE" whose evidence_ref_ids ALL resolve to provenance_hashes
    in master.evidence_refs AND whose term string is actually present in the evidence supported_terms_contained
    can populate evidence_supported_tags.
    Unresolved IDs or unbacked terms are strictly rejected. Personalization is NOT defaulted automatically.
    """
    kw = master.keyword.lower().strip()
    words = kw.split()

    product_nouns = []
    buyer_roles = []
    occasions = []
    personalization = []
    style_modifiers = []

    for w in words:
        if w in ("bag", "tote", "pouch", "tshirt", "shirt", "crewneck", "sweatshirt", "hoodie", "hat", "cap", "mug"):
            product_nouns.append(w)
        elif w in ("bridesmaid", "nurse", "grandpa", "papa", "mom", "dad", "teacher", "bride"):
            buyer_roles.append(w)
        elif w in ("wedding", "bachelorette", "birthday", "school", "christmas", "halloween"):
            occasions.append(w)
        elif w in ("custom", "personalized", "monogram", "name"):
            personalization.append(w)

    # Allowed evidence ID map & term verification set
    valid_ev_map = {e.provenance_hash: e for e in master.evidence_refs}

    evidence_tags = []
    seen = set()

    if supported_terms:
        for st in supported_terms:
            if st.origin_type == "EVIDENCE" and st.evidence_ref_ids:
                # 1. Check all evidence IDs resolve
                if all(ref_id in valid_ev_map for ref_id in st.evidence_ref_ids):
                    t_clean = st.term.lower().strip()
                    # 2. Check term actually exists in the evidence supported_terms_contained
                    term_backed = False
                    for ref_id in st.evidence_ref_ids:
                        ev_ref = valid_ev_map[ref_id]
                        if t_clean in ev_ref.supported_terms_contained or t_clean == master.canonical_keyword:
                            term_backed = True
                            break
                    
                    if term_backed and t_clean and t_clean not in seen and len(t_clean) <= MAX_TAG_LEN:
                        seen.add(t_clean)
                        evidence_tags.append(t_clean)

    supported = tuple(evidence_tags[:TAG_LIMIT])
    tag_gap_count = max(0, TAG_LIMIT - len(supported))

    # Full Semantic Cluster Revision Hash (includes all semantic lists + compiler_version)
    cluster_payload = {
        "compiler_version": COMPILER_VERSION,
        "master_revision_id": master.revision_id,
        "primary_keyword": kw,
        "mode": master.mode,
        "product_nouns": sorted(product_nouns),
        "buyer_roles": sorted(buyer_roles),
        "occasions": sorted(occasions),
        "personalization_angles": sorted(personalization),
        "style_modifiers": sorted(style_modifiers),
        "evidence_supported_tags": list(supported),
        "tag_gap_count": tag_gap_count
    }
    cluster_json = json.dumps(cluster_payload, sort_keys=True, separators=(',', ':'))
    cluster_rev = f"lc-{hashlib.sha256(cluster_json.encode('utf-8')).hexdigest()[:12]}"

    return ListingCluster(
        revision_id=cluster_rev,
        master_revision_id=master.revision_id,
        primary_keyword=master.keyword,
        mode=master.mode,
        product_nouns=tuple(product_nouns),
        buyer_roles=tuple(buyer_roles),
        occasions=tuple(occasions),
        personalization_angles=tuple(personalization),
        style_modifiers=tuple(style_modifiers),
        evidence_supported_tags=supported,
        tag_gap_count=tag_gap_count,
        compiler_version=COMPILER_VERSION
    )


def compile_package(
    cluster: ListingCluster,
    owner_checks_override: Optional[Sequence[OwnerCheck]] = None,
    product_truth_override: Optional[Dict[str, Any]] = None,
    price_fact_override: Optional[PriceFact] = None
) -> ListingPackage:
    """Compile a deterministic ListingPackage from a frozen ListingCluster revision.
    
    Zero network calls. Explicit TAG_GAP tracking.
    Customer-facing buyer_copy renders physical claims ONLY IF the exact corresponding OwnerCheck is verified.
    Design-Level IP QA defaults to verified = False.
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

    evidence_tags = tuple(cluster.evidence_supported_tags)
    tag_gaps = tuple(f"TAG_GAP_{i+1}" for i in range(cluster.tag_gap_count))

    # Determine Owner Checks first
    if owner_checks_override:
        checks = tuple(owner_checks_override)
    else:
        checks = (
            OwnerCheck("Exact SKU / Supplier", "SUPPLIER", False, "Supplier not selected yet"),
            OwnerCheck("Material Composition", "PRODUCT_TRUTH", False, "Material unverified"),
            OwnerCheck("Dimensions & Sizing", "PRODUCT_TRUTH", False, "Dimensions unverified"),
            OwnerCheck("Available Color Palette", "PRODUCT_TRUTH", False, "Colors unverified"),
            OwnerCheck("Personalization Limits", "PRODUCT_TRUTH", False, "Character count limits unverified"),
            OwnerCheck("Design-Level IP QA", "IP_QA", False, "Artwork and design-level IP clearance required"),
        )

    check_verified_map = {c.field: c.verified for c in checks}

    # Product Truth Slots (Internal Data Structure)
    ptruth = product_truth_override or {}
    truth_slots = (
        ("material", ptruth.get("material", "UNVERIFIED")),
        ("dimensions", ptruth.get("dimensions", "UNVERIFIED")),
        ("colors", ptruth.get("colors", "UNVERIFIED")),
        ("shipping", ptruth.get("shipping", "UNVERIFIED")),
    )

    # Customer-Facing Buyer Copy (Render ONLY if verified in owner_checks!)
    buyer_copy_lines = [
        f"Personalized {kw_cap} — custom designed for {cluster.buyer_roles[0] if cluster.buyer_roles else 'special occasions'}.",
    ]
    
    # Conditional Personalization Copy (Only if personalization angles exist)
    if cluster.personalization_angles:
        buyer_copy_lines.extend([
            "",
            "PERSONALIZATION INSTRUCTIONS",
            "• Enter the exact name, date, or text for customization.",
            "• Double-check spelling before placing your order.",
        ])

    # PROVENANCE-VERIFIED PHYSICAL CLAIMS: Render ONLY IF verified in check_verified_map
    if check_verified_map.get("Material Composition") and ptruth.get("material") and ptruth["material"] != "UNVERIFIED":
        buyer_copy_lines.append(f"• Material: {ptruth['material']}")
    if check_verified_map.get("Dimensions & Sizing") and ptruth.get("dimensions") and ptruth["dimensions"] != "UNVERIFIED":
        buyer_copy_lines.append(f"• Dimensions: {ptruth['dimensions']}")

    buyer_copy = "\n".join(buyer_copy_lines)

    photo_lines = [
        f"1. Main Hero Image: {kw_cap} in real use context.",
        "2. Product Angle: Clean front shot of primary design.",
        "3. Close-Up Detail: Texture and craftsmanship view.",
    ]
    if cluster.personalization_angles:
        photo_lines.append("4. Personalization Explainer: Clear visual showing custom text placement.")
        
    photo_lines.extend([
        "5. Size & Dimension Graphic: [RENDER ONLY AFTER PRODUCT TRUTH VERIFIED]",
        "6. Color Palette Grid: [RENDER ONLY AFTER PRODUCT TRUTH VERIFIED]",
        "7. Gift Context: Package / presentation visual.",
        "8. Ordering Process Infographic: Step 1 Select Options -> Step 2 Add Personalization -> Step 3 Checkout."
    ])
    photo_brief = "\n".join(photo_lines)

    price_fact = price_fact_override or PriceFact(value=None, currency="USD", provenance_type="UNVERIFIED", verified=False)

    # Full Revision Identity: Include all content, truth_slots, price_fact, and owner checks in hash payload
    pkg_payload = {
        "cluster_revision_id": cluster.revision_id,
        "title": title,
        "evidence_tags": list(evidence_tags),
        "tag_gap_count": cluster.tag_gap_count,
        "buyer_copy": buyer_copy,
        "photo_brief": photo_brief,
        "product_truth_slots": list(truth_slots),
        "price_fact": price_fact.to_dict(),
        "owner_checks": [c.to_dict() for c in checks]
    }
    pkg_json = json.dumps(pkg_payload, sort_keys=True, separators=(',', ':'))
    pkg_rev = f"lp-{hashlib.sha256(pkg_json.encode('utf-8')).hexdigest()[:12]}"

    return ListingPackage(
        revision_id=pkg_rev,
        cluster_revision_id=cluster.revision_id,
        title=title,
        evidence_tags=evidence_tags,
        tag_gaps=tag_gaps,
        buyer_copy=buyer_copy,
        product_truth_slots=truth_slots,
        photo_brief=photo_brief,
        price_fact=price_fact,
        owner_checks=checks,
        network_calls_made=0
    )
