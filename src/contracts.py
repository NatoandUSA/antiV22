"""22Etsy Core Data Contracts (P0-A.5 Final Root Cause Closure).

Defines the immutable, versioned data contracts that pass between execution layers:
  RAW Evidence -> EvidenceRef -> MasterKeyword -> ListingCluster -> ListingPackage

P0-A.5 Final Root Cause Closure Rules:
1. Dynamic Runtime Fit Status Alignment: Imports/shares valid statuses directly from src.product_fit.
2. Value-Bound Product Truth Verification: Uses ProductTruthFact(field, value, verified, provenance_ref). buyer_copy & publish_ready require EXACT verified fact binding.
3. Content Identity vs Freshness Separation: Evidence content_hash excludes retrieved_at so unchanged evidence updates do not churn Master revisions.
4. Tag-Level Provenance Preservation: ListingCluster stores supported_terms tuple carrying exact evidence_ref_ids.
5. Neutral Offer Semantics & Conditional Gift Photo Slot: Non-personalized items omit 'Custom'/'Personalized' claims; Gift photo slot requires gift intent.
6. Constructor-Level Deep Freezing: All dataclass __post_init__ methods recursively freeze nested structures.
"""
import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple, Sequence, Set

from src import product_fit

COMPILER_VERSION = "p0-a.5"
TAG_LIMIT = 13
MAX_TAG_LEN = 20

# Dynamic alignment with src.product_fit vocabulary + runtime extensions
VALID_MODES = {"pod", "embroidery"}
VALID_MARKET_VERDICTS = {"GO", "CONDITIONAL", "WATCH", "SKIP"}
VALID_TM_RISKS = {"OK", "CAUTION", "HIGH"}
VALID_ENGINE_ACTIONS = {"BUILD_NOW", "CONFIRM_FIRST", "REVIEW", "WATCH", "SKIP", "BLOCKED"}
VALID_EXEC_ACTIONS = {"BUILD_NOW", "CONFIRM_FIRST", "MINE_NICHE", "REVIEW_ACTIONABILITY", "BLOCKED", "SKIP", "WATCH"}
VALID_SPECIFICITY_CLASSES = {"SPECIFIC_ACTIONABLE", "BROAD_PARENT", "AMBIGUOUS_REVIEW", "NOT_APPLICABLE", "NONE"}

# Combine product_fit constants dynamically with base contract fallbacks
VALID_FIT_STATUSES = {
    product_fit.POD_FIT, product_fit.EMBROIDERY_FIT, product_fit.JEWELRY_FIT, product_fit.ACRYLIC_FIT,
    product_fit.DIGITAL_FIT, product_fit.SHOP_NAME_LIKELY, product_fit.POLICY_RISK, product_fit.TRADEMARK_RISK,
    product_fit.BROAD_SEED_ONLY, product_fit.NON_PRODUCT, product_fit.NEEDS_REVIEW, product_fit.THEME_FIT_READY,
    product_fit.THEME_FIT_NEEDS_PRODUCT, product_fit.AMBIGUOUS_PHRASE, product_fit.LOW_BUYER_INTENT,
    "NO_FIT", "BLOCKED", "NONE"
}

VALID_MATCH_TYPES = {"EXACT", "GROUP"}
VALID_VERDICTS = {"SELLING", "STRONG_SELLER", "PROVEN_WINNER", "LISTED"}
VALID_CHECK_CATEGORIES = {"PRODUCT_TRUTH", "SUPPLIER", "IP_QA"}

VALID_PRICE_PROVENANCES = {"EXACT_LISTING", "MODELED", "OWNER_SET", "UNVERIFIED"}

BASE_REQUIRED_OWNER_CHECK_FIELDS = {
    "Exact SKU / Supplier",
    "Material Composition",
    "Dimensions & Sizing",
    "Available Color Palette",
    "Design-Level IP QA"
}

GIFT_SIGNALS = {
    "wedding", "bachelorette", "birthday", "christmas", "gift", "gifts",
    "bridesmaid", "grandpa", "papa", "mom", "dad", "teacher", "nurse", "bride"
}


def _deep_freeze(val: Any) -> Any:
    """Recursively freeze dicts, lists, and sets into immutable tuples."""
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
        if self.provenance_type == "UNVERIFIED" and self.verified:
            raise ValueError("UNVERIFIED price provenance cannot have verified=True!")
        if self.value is None and self.verified:
            raise ValueError("PriceFact with value=None cannot be verified=True!")
        if self.value is not None and self.value <= 0:
            raise ValueError("Price value must be positive")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProductTruthFact:
    field: str                        # material / dimensions / colors / shipping
    value: str                        # e.g., "100% Cotton Canvas"
    verified: bool = False
    provenance_ref: str = ""

    def __post_init__(self):
        if not self.field:
            raise ValueError("ProductTruthFact field cannot be empty")
        if not self.value:
            raise ValueError("ProductTruthFact value cannot be empty")

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
        object.__setattr__(self, "term", self.term.lower().strip())
        object.__setattr__(self, "evidence_ref_ids", _deep_freeze(self.evidence_ref_ids))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
            
        object.__setattr__(self, "raw_facts", _deep_freeze(self.raw_facts))
        object.__setattr__(self, "derived_metrics", _deep_freeze(self.derived_metrics))
        object.__setattr__(
            self,
            "supported_terms_contained",
            tuple(sorted(t.lower().strip() for t in self.supported_terms_contained))
        )

        computed = self.compute_content_hash()
        if self.provenance_hash and self.provenance_hash != computed:
            raise ValueError(f"Supplied provenance_hash '{self.provenance_hash}' does not match computed content_hash '{computed}'!")
        object.__setattr__(self, "provenance_hash", computed)

    def compute_content_hash(self) -> str:
        """Compute stable content_hash EXCLUDING observation time retrieved_at.
        
        Prevents Master revision churn on periodic refreshes if raw facts are unchanged.
        """
        payload = {
            "source": self.source,
            "match_type": self.match_type,
            "verdict": self.verdict,
            "raw_facts": self.raw_facts,
            "derived_metrics": self.derived_metrics,
            "supported_terms": self.supported_terms_contained
        }
        raw_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return f"ev-{hashlib.sha256(raw_json.encode('utf-8')).hexdigest()[:12]}"

    @property
    def observation_id(self) -> str:
        """Observation ID includes retrieved_at for snapshot freshness tracking."""
        obs_payload = {"content_hash": self.provenance_hash, "retrieved_at": self.retrieved_at}
        obs_json = json.dumps(obs_payload, sort_keys=True, separators=(',', ':'))
        return f"obs-{hashlib.sha256(obs_json.encode('utf-8')).hexdigest()[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "retrieved_at": self.retrieved_at,
            "provenance_hash": self.provenance_hash,
            "observation_id": self.observation_id,
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
    """Helper constructor for EvidenceRef."""
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
    product_fit_status: str            # POD_FIT / EMBROIDERY_FIT / THEME_FIT_NEEDS_PRODUCT / NO_FIT / BLOCKED / NONE
    trademark_risk: str                # OK / CAUTION / HIGH
    engine_action: str                 # BUILD_NOW / CONFIRM_FIRST / REVIEW / WATCH / SKIP / BLOCKED
    execution_action: str              # BUILD_NOW / CONFIRM_FIRST / MINE_NICHE / REVIEW_ACTIONABILITY / BLOCKED / SKIP / WATCH
    specificity_class: str             # SPECIFIC_ACTIONABLE / BROAD_PARENT / AMBIGUOUS_REVIEW / NOT_APPLICABLE / NONE
    evidence_refs: Tuple[EvidenceRef, ...] = ()
    created_at: str = ""

    def __post_init__(self):
        object.__setattr__(self, "evidence_refs", _deep_freeze(self.evidence_refs))

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
    supported_terms: Tuple[SupportedTerm, ...]
    tag_gap_count: int
    compiler_version: str = COMPILER_VERSION

    def __post_init__(self):
        object.__setattr__(self, "product_nouns", _deep_freeze(self.product_nouns))
        object.__setattr__(self, "buyer_roles", _deep_freeze(self.buyer_roles))
        object.__setattr__(self, "occasions", _deep_freeze(self.occasions))
        object.__setattr__(self, "personalization_angles", _deep_freeze(self.personalization_angles))
        object.__setattr__(self, "style_modifiers", _deep_freeze(self.style_modifiers))
        object.__setattr__(self, "supported_terms", _deep_freeze(self.supported_terms))

    @property
    def evidence_supported_tags(self) -> Tuple[str, ...]:
        """Derived property: plain tag strings carrying evidence provenance."""
        tags = []
        for st in self.supported_terms:
            if st.origin_type == "EVIDENCE" and st.evidence_ref_ids:
                tags.append(st.term)
        return tuple(tags)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["evidence_supported_tags"] = list(self.evidence_supported_tags)
        d["supported_terms"] = [st.to_dict() for st in self.supported_terms]
        return d


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
    product_truth_facts: Tuple[ProductTruthFact, ...]
    photo_brief: str
    price_fact: PriceFact
    owner_checks: Tuple[OwnerCheck, ...]
    network_calls_made: int = 0

    def __post_init__(self):
        object.__setattr__(self, "evidence_tags", _deep_freeze(self.evidence_tags))
        object.__setattr__(self, "tag_gaps", _deep_freeze(self.tag_gaps))
        object.__setattr__(self, "product_truth_facts", _deep_freeze(self.product_truth_facts))
        object.__setattr__(self, "owner_checks", _deep_freeze(self.owner_checks))

    @property
    def publish_ready(self) -> bool:
        """Derived property: publish_ready is True ONLY IF:
        1. All required Owner Checks (context-aware) are present & verified.
        2. PriceFact has a valid verified non-null positive price.
        3. ProductTruthFact for 'shipping' exists AND is verified.
        """
        if not self.owner_checks:
            return False
        
        # 1. Price Verification
        if not self.price_fact or not self.price_fact.verified or self.price_fact.value is None or self.price_fact.value <= 0:
            return False

        # 2. Verified Shipping ProductTruthFact
        shipping_fact = next((f for f in self.product_truth_facts if f.field == "shipping"), None)
        if not shipping_fact or not shipping_fact.verified or shipping_fact.value == "UNVERIFIED":
            return False

        # 3. Context-Aware Required Checks
        check_map = {c.field: c.verified for c in self.owner_checks}
        if len(self.owner_checks) != len(check_map):
            return False
            
        required_fields = set(BASE_REQUIRED_OWNER_CHECK_FIELDS)
        if "PERSONALIZATION INSTRUCTIONS" in self.buyer_copy:
            required_fields.add("Personalization Limits")

        for req_field in required_fields:
            if req_field not in check_map or not check_map[req_field]:
                return False
                
        return True

    def to_deterministic_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["publish_ready"] = self.publish_ready
        d["price_fact"] = self.price_fact.to_dict()
        d["product_truth_facts"] = [f.to_dict() for f in self.product_truth_facts]
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
    if fit_status not in VALID_FIT_STATUSES:
        raise ValueError(f"Invalid product_fit_status: {fit_status}")
    if tm_risk not in VALID_TM_RISKS:
        raise ValueError(f"Invalid trademark_risk: {tm_risk}")
    if engine_action not in VALID_ENGINE_ACTIONS:
        raise ValueError(f"Invalid engine_action: {engine_action}")
    if execution_action not in VALID_EXEC_ACTIONS:
        raise ValueError(f"Invalid execution_action: {execution_action}")
    if spec_cls not in VALID_SPECIFICITY_CLASSES:
        raise ValueError(f"Invalid specificity_class: {spec_cls}")

    # Deduplicate & Sort EvidenceRefs by content_hash (provenance_hash)
    ev_map: Dict[str, EvidenceRef] = {}
    if evidence_refs:
        for ev in evidence_refs:
            h = ev.provenance_hash
            if h in ev_map and ev_map[h] != ev:
                raise ValueError(f"EvidenceRef hash collision detected! Same hash '{h}' supplied for conflicting evidence content.")
            ev_map[h] = ev

    sorted_ev_hashes = sorted(ev_map.keys())
    sorted_ev_refs = tuple(ev_map[h] for h in sorted_ev_hashes)

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
    """Compile a deterministic ListingCluster revision from a MasterKeyword record."""
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

    valid_ev_map = {e.provenance_hash: e for e in master.evidence_refs}

    cluster_terms = []
    seen = set()

    if supported_terms:
        for st in supported_terms:
            if st.origin_type == "EVIDENCE" and st.evidence_ref_ids:
                t_clean = st.term.lower().strip()
                # Filter to EXACT evidence refs that contain t_clean
                verified_refs = tuple(
                    ref_id for ref_id in st.evidence_ref_ids
                    if ref_id in valid_ev_map and t_clean in valid_ev_map[ref_id].supported_terms_contained
                )
                if verified_refs and t_clean not in seen and len(t_clean) <= MAX_TAG_LEN:
                    seen.add(t_clean)
                    cluster_terms.append(SupportedTerm(t_clean, "EVIDENCE", verified_refs))

    supported_tuple = tuple(cluster_terms[:TAG_LIMIT])
    tag_gap_count = max(0, TAG_LIMIT - len(supported_tuple))

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
        "supported_terms": [st.to_dict() for st in supported_tuple],
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
        supported_terms=supported_tuple,
        tag_gap_count=tag_gap_count,
        compiler_version=COMPILER_VERSION
    )


def compile_package(
    cluster: ListingCluster,
    owner_checks_override: Optional[Sequence[OwnerCheck]] = None,
    product_truth_facts_override: Optional[Sequence[ProductTruthFact]] = None,
    price_fact_override: Optional[PriceFact] = None
) -> ListingPackage:
    """Compile a deterministic ListingPackage from a frozen ListingCluster revision.
    
    Zero network calls.
    VALUE-BOUND PRODUCT TRUTH: Physical copy renders in buyer_copy ONLY IF exact ProductTruthFact is verified.
    NEUTRAL OFFER COPY & CONDITIONAL GIFT PHOTO SLOT: Non-personalized items omit 'Custom'/'Personalized' claims.
    """
    kw_cap = cluster.primary_keyword.title()
    roles = [r.title() for r in cluster.buyer_roles if r.lower() != cluster.primary_keyword.lower()]
    prods = [p.title() for p in cluster.product_nouns]
    
    title_parts = [kw_cap]
    if roles:
        title_parts.append(roles[0] + " Gift")
    if prods:
        title_parts.append(prods[0])
    
    title = ", ".join(title_parts)

    evidence_tags = tuple(cluster.evidence_supported_tags)
    tag_gaps = tuple(f"TAG_GAP_{i+1}" for i in range(cluster.tag_gap_count))

    # Default Owner Checks
    if owner_checks_override:
        checks = tuple(owner_checks_override)
    else:
        check_list = [
            OwnerCheck("Exact SKU / Supplier", "SUPPLIER", False, "Supplier not selected yet"),
            OwnerCheck("Material Composition", "PRODUCT_TRUTH", False, "Material unverified"),
            OwnerCheck("Dimensions & Sizing", "PRODUCT_TRUTH", False, "Dimensions unverified"),
            OwnerCheck("Available Color Palette", "PRODUCT_TRUTH", False, "Colors unverified"),
            OwnerCheck("Design-Level IP QA", "IP_QA", False, "Artwork and design-level IP clearance required"),
        ]
        if cluster.personalization_angles:
            check_list.append(OwnerCheck("Personalization Limits", "PRODUCT_TRUTH", False, "Character count limits unverified"))
            
        checks = tuple(check_list)

    # Product Truth Facts
    if product_truth_facts_override:
        truth_facts = tuple(product_truth_facts_override)
    else:
        truth_facts = (
            ProductTruthFact("material", "UNVERIFIED", False),
            ProductTruthFact("dimensions", "UNVERIFIED", False),
            ProductTruthFact("colors", "UNVERIFIED", False),
            ProductTruthFact("shipping", "UNVERIFIED", False),
        )

    truth_map = {f.field: f for f in truth_facts}

    # NEUTRAL LEAD SENTENCE & CONDITIONAL INSTRUCTIONS
    if cluster.personalization_angles:
        buyer_copy_lines = [
            f"Personalized {kw_cap} — custom designed for {cluster.buyer_roles[0] if cluster.buyer_roles else 'special occasions'}.",
            "",
            "PERSONALIZATION INSTRUCTIONS",
            "• Enter the exact name, date, or text for customization.",
            "• Double-check spelling before submitting your order.",
        ]
    else:
        buyer_copy_lines = [
            f"{kw_cap} — designed for {cluster.buyer_roles[0] if cluster.buyer_roles else 'special occasions'}.",
        ]

    # VALUE-BOUND PHYSICAL CLAIMS RENDERING: Render ONLY IF ProductTruthFact exists AND verified == True
    mat_fact = truth_map.get("material")
    if mat_fact and mat_fact.verified and mat_fact.value != "UNVERIFIED":
        buyer_copy_lines.append(f"• Material: {mat_fact.value}")

    dim_fact = truth_map.get("dimensions")
    if dim_fact and dim_fact.verified and dim_fact.value != "UNVERIFIED":
        buyer_copy_lines.append(f"• Dimensions: {dim_fact.value}")

    buyer_copy = "\n".join(buyer_copy_lines)

    # CONDITIONAL PHOTO BRIEF (GIFT SLOT CONDITIONAL ON GIFT INTENT)
    has_gift_intent = any(
        w.lower() in GIFT_SIGNALS
        for list_terms in (cluster.buyer_roles, cluster.occasions, cluster.product_nouns, [cluster.primary_keyword])
        for w in list_terms
    )

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
    ])
    if has_gift_intent:
        photo_lines.append("7. Gift Context: Package / presentation visual.")

    if cluster.personalization_angles:
        photo_lines.append("8. Ordering Process Infographic: Step 1 Select Options -> Step 2 Add Personalization -> Step 3 Checkout.")
    else:
        photo_lines.append("8. Ordering Process Infographic: Step 1 Select Options -> Step 2 Checkout.")

    photo_brief = "\n".join(photo_lines)

    price_fact = price_fact_override or PriceFact(value=None, currency="USD", provenance_type="UNVERIFIED", verified=False)

    # Full Revision Identity: Include all content, truth_facts, price_fact, and owner checks
    pkg_payload = {
        "cluster_revision_id": cluster.revision_id,
        "title": title,
        "evidence_tags": list(evidence_tags),
        "tag_gap_count": cluster.tag_gap_count,
        "buyer_copy": buyer_copy,
        "photo_brief": photo_brief,
        "product_truth_facts": [f.to_dict() for f in truth_facts],
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
        product_truth_facts=truth_facts,
        photo_brief=photo_brief,
        price_fact=price_fact,
        owner_checks=checks,
        network_calls_made=0
    )
