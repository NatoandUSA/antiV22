"""22Etsy Core Data Contracts (P0-A.2 Contract Integrity & Deep Immutability).

Defines the immutable, versioned data contracts that pass between execution layers:
  RAW Evidence -> EvidenceRef -> MasterKeyword -> ListingCluster -> ListingPackage

P0-A.2 Integrity Rules:
1. Strict Provenance Validation: SupportedTerm evidence_ref_ids MUST resolve to a valid provenance_hash in master.evidence_refs. Fake/unresolved IDs are rejected.
2. Full Revision Identity: ListingPackage revision hash includes ALL content & state fields (product_truth_slots, photo_brief, price, owner_checks).
3. Deep Immutability: All nested dataclasses (EvidenceRef, OwnerCheck) remain frozen dataclasses in tuples, preventing dictionary mutations.
4. Value Validations: Enforces valid match_types, verdicts, and OwnerCheck categories.
5. Truthful Metadata: Excludes volatile/fake created_at timestamps from contract decision identity.
"""
import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple, Sequence

TAG_LIMIT = 13
MAX_TAG_LEN = 20

VALID_MODES = {"pod", "embroidery"}
VALID_MARKET_VERDICTS = {"GO", "CONDITIONAL", "WATCH", "SKIP"}
VALID_TM_RISKS = {"OK", "CAUTION", "HIGH"}
VALID_ENGINE_ACTIONS = {"BUILD_NOW", "CONFIRM_FIRST", "REVIEW", "WATCH", "SKIP", "BLOCKED"}
VALID_EXEC_ACTIONS = {"BUILD_NOW", "CONFIRM_FIRST", "MINE_NICHE"}
VALID_SPECIFICITY_CLASSES = {"SPECIFIC_ACTIONABLE", "BROAD_PARENT"}

VALID_MATCH_TYPES = {"EXACT", "GROUP"}
VALID_VERDICTS = {"SELLING", "STRONG_SELLER", "PROVEN_WINNER", "LISTED"}
VALID_CHECK_CATEGORIES = {"PRODUCT_TRUTH", "SUPPLIER", "IP_QA"}


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
    raw_facts: Tuple[Tuple[str, Any], ...] = ()         # Sorted immutable tuple of (key, value)
    derived_metrics: Tuple[Tuple[str, Any], ...] = ()   # Sorted immutable tuple of (key, value)

    def __post_init__(self):
        if self.match_type not in VALID_MATCH_TYPES:
            raise ValueError(f"Invalid match_type: {self.match_type}")
        if self.verdict not in VALID_VERDICTS:
            raise ValueError(f"Invalid verdict: {self.verdict}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "retrieved_at": self.retrieved_at,
            "provenance_hash": self.provenance_hash,
            "match_type": self.match_type,
            "verdict": self.verdict,
            "raw_facts": dict(self.raw_facts),
            "derived_metrics": dict(self.derived_metrics)
        }


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
    execution_action: str              # BUILD_NOW / CONFIRM_FIRST / MINE_NICHE
    specificity_class: str             # SPECIFIC_ACTIONABLE / BROAD_PARENT
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
    price: Optional[float]
    owner_checks: Tuple[OwnerCheck, ...]
    network_calls_made: int = 0

    @property
    def publish_ready(self) -> bool:
        """Derived property: publish_ready is True ONLY when all Owner Checks are verified."""
        if not self.owner_checks:
            return False
        return all(c.verified for c in self.owner_checks)

    def to_deterministic_dict(self) -> Dict[str, Any]:
        """Returns a canonical dictionary representation excluding volatile properties."""
        d = asdict(self)
        d["publish_ready"] = self.publish_ready
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
    """Create a 100% deterministic MasterKeyword decision record from canonical multi-EvidenceRef data."""
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
    if specificity_class not in VALID_SPECIFICITY_CLASSES:
        raise ValueError(f"Invalid specificity_class: {specificity_class}")

    # Deduplicate & Sort EvidenceRefs by provenance_hash
    ev_map: Dict[str, EvidenceRef] = {}
    if evidence_refs:
        for ev in evidence_refs:
            ev_map[ev.provenance_hash] = ev

    sorted_ev_hashes = sorted(ev_map.keys())
    sorted_ev_refs = tuple(ev_map[h] for h in sorted_ev_hashes)

    # Canonical Hash Data Payload (Sorted Keys)
    hash_payload = {
        "keyword": keyword.lower().strip(),
        "mode": mode,
        "opp_score": round(float(opp_score), 2),
        "market_verdict": market_verdict,
        "product_fit_status": fit_status,
        "trademark_risk": tm_risk,
        "engine_action": engine_action,
        "execution_action": execution_action,
        "specificity_class": specificity_class,
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
        specificity_class=specificity_class,
        evidence_refs=sorted_ev_refs,
        created_at=created_at
    )


def compile_cluster(
    master: MasterKeyword,
    supported_terms: Optional[Sequence[SupportedTerm]] = None
) -> ListingCluster:
    """Compile a deterministic ListingCluster revision from a MasterKeyword record.
    
    Mode-neutral compiler for POD & Embroidery.
    STRICT PROVENANCE RULE: ONLY terms with origin_type == "EVIDENCE" whose evidence_ref_ids ALL
    resolve to provenance_hashes present in master.evidence_refs can populate evidence_supported_tags.
    Unresolved/fake provenance IDs are strictly rejected.
    """
    kw = master.keyword.lower().strip()
    words = kw.split()

    product_nouns = []
    buyer_roles = []
    occasions = []
    personalization = ["custom text"]
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

    # Allowed evidence ID set from master
    valid_evidence_ids = {e.provenance_hash for e in master.evidence_refs}

    evidence_tags = []
    seen = set()

    if supported_terms:
        for st in supported_terms:
            if st.origin_type == "EVIDENCE" and st.evidence_ref_ids:
                # STRICT PROVENANCE RESOLUTION: ALL evidence_ref_ids must resolve to master's evidence set
                if all(ref_id in valid_evidence_ids for ref_id in st.evidence_ref_ids):
                    t_clean = st.term.lower().strip()
                    if t_clean and t_clean not in seen and len(t_clean) <= MAX_TAG_LEN:
                        seen.add(t_clean)
                        evidence_tags.append(t_clean)

    supported = tuple(evidence_tags[:TAG_LIMIT])
    tag_gap_count = max(0, TAG_LIMIT - len(supported))

    cluster_payload = {
        "master_revision_id": master.revision_id,
        "primary_keyword": kw,
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
        tag_gap_count=tag_gap_count
    )


def compile_package(
    cluster: ListingCluster,
    owner_checks_override: Optional[Sequence[OwnerCheck]] = None,
    product_truth_override: Optional[Dict[str, Any]] = None,
    price_override: Optional[float] = None
) -> ListingPackage:
    """Compile a deterministic ListingPackage from a frozen ListingCluster revision.
    
    Zero network calls. No synthetic prices. Explicit TAG_GAP tracking.
    Full Revision Identity: revision hash includes ALL content & state fields (product_truth_slots, photo_brief, price, owner_checks).
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

    ptruth = product_truth_override or {}
    truth_slots = (
        ("material", ptruth.get("material", "UNVERIFIED")),
        ("dimensions", ptruth.get("dimensions", "UNVERIFIED")),
        ("colors", ptruth.get("colors", "UNVERIFIED")),
        ("shipping", ptruth.get("shipping", "UNVERIFIED")),
    )

    buyer_copy_lines = [
        f"Personalized {kw_cap} — custom designed for {cluster.buyer_roles[0] if cluster.buyer_roles else 'special occasions'}.",
        "",
        "PERSONALIZATION INSTRUCTIONS",
        "• Enter the exact name, date, or text for customization.",
        "• Double-check spelling before placing your order.",
    ]
    
    if ptruth.get("material") and ptruth["material"] != "UNVERIFIED":
        buyer_copy_lines.append(f"• Material: {ptruth['material']}")
    if ptruth.get("dimensions") and ptruth["dimensions"] != "UNVERIFIED":
        buyer_copy_lines.append(f"• Dimensions: {ptruth['dimensions']}")

    buyer_copy = "\n".join(buyer_copy_lines)

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

    # FULL REVISION IDENTITY: Include all content, truth_slots, price, and owner check states in the hash payload
    pkg_payload = {
        "cluster_revision_id": cluster.revision_id,
        "title": title,
        "evidence_tags": list(evidence_tags),
        "tag_gap_count": cluster.tag_gap_count,
        "buyer_copy": buyer_copy,
        "photo_brief": photo_brief,
        "product_truth_slots": list(truth_slots),
        "price": price_override,
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
        price=price_override,
        owner_checks=checks,
        network_calls_made=0
    )
