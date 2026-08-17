"""22Etsy Core Data Contracts (P0-A.6 Final Contract Closure).

Defines immutable, versioned contracts across:
  RAW Evidence -> EvidenceRef -> MasterKeyword -> ListingCluster -> ListingPackage

P0-A.6 closure rules:
1. Product Truth is exact-value bound: verified facts require provenance and OwnerCheck subject_ref binds to the exact fact revision.
2. Publish price is seller-owned: only verified OWNER_SET PriceFact can satisfy publish readiness.
3. Evidence content identity is stable across observations; same-content refreshes dedupe to the latest observation without revision churn.
4. Tag provenance survives the cluster boundary with evidence ref + source-path bindings.
5. Offer semantics stay neutral unless personalization/gift intent is explicitly present.
6. Product-fit vocabulary comes from product_fit.PRODUCT_FIT_STATUSES as the canonical runtime source.
"""
import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Tuple, Sequence

from src import product_fit

COMPILER_VERSION = "p0-a.6"
TAG_LIMIT = 13
MAX_TAG_LEN = 20

VALID_MODES = {"pod", "embroidery"}
VALID_MARKET_VERDICTS = {"GO", "CONDITIONAL", "WATCH", "SKIP"}
VALID_TM_RISKS = {"OK", "CAUTION", "HIGH"}
VALID_ENGINE_ACTIONS = {"BUILD_NOW", "CONFIRM_FIRST", "REVIEW", "WATCH", "SKIP", "BLOCKED"}
VALID_EXEC_ACTIONS = {"BUILD_NOW", "CONFIRM_FIRST", "MINE_NICHE", "REVIEW_ACTIONABILITY", "BLOCKED", "SKIP", "WATCH"}
VALID_SPECIFICITY_CLASSES = {"SPECIFIC_ACTIONABLE", "BROAD_PARENT", "AMBIGUOUS_REVIEW", "NOT_APPLICABLE", "NONE"}
CONTRACT_ONLY_FIT_STATUSES = {"NO_FIT", "BLOCKED", "NONE"}
VALID_FIT_STATUSES = set(product_fit.PRODUCT_FIT_STATUSES) | CONTRACT_ONLY_FIT_STATUSES

VALID_MATCH_TYPES = {"EXACT", "GROUP"}
VALID_VERDICTS = {"SELLING", "STRONG_SELLER", "PROVEN_WINNER", "LISTED"}
VALID_CHECK_CATEGORIES = {"PRODUCT_TRUTH", "SUPPLIER", "IP_QA"}
VALID_PRICE_PROVENANCES = {"EXACT_LISTING", "MODELED", "OWNER_SET", "UNVERIFIED"}
VALID_PRODUCT_TRUTH_FIELDS = {"material", "dimensions", "colors", "shipping"}

# Single source of truth for owner-check fields: name, category, default
# unverified message, and (if any) the product-truth field it binds to.
# publish_ready and compile_package's default check list both derive from
# this so the two representations of "what must be verified" can't drift --
# a field renamed/removed in one place is automatically renamed/removed
# in the other, instead of failing silently later.
OWNER_CHECK_SPECS = (
    ("Exact SKU / Supplier", "SUPPLIER", "Supplier not selected yet", None),
    ("Material Composition", "PRODUCT_TRUTH", "Material unverified", "material"),
    ("Dimensions & Sizing", "PRODUCT_TRUTH", "Dimensions unverified", "dimensions"),
    ("Available Color Palette", "PRODUCT_TRUTH", "Colors unverified", "colors"),
    ("Shipping / Processing", "PRODUCT_TRUTH", "Shipping unverified", "shipping"),
    ("Design-Level IP QA", "IP_QA", "Artwork and design-level IP clearance required", None),
)
BASE_REQUIRED_OWNER_CHECK_FIELDS = {spec[0] for spec in OWNER_CHECK_SPECS}
TRUTH_CHECK_TO_FIELD = {spec[0]: spec[3] for spec in OWNER_CHECK_SPECS if spec[3]}

# Stable, form-safe identifiers for the owner-check fields that have no
# bound product-truth field -- truth-bound fields reuse their own truth
# field name ("material", "dimensions", ...) as the slug already. Shared by
# Studio's save form (src/interactive.py) and its save route (src/web.py)
# so the two sides of one HTML form can't drift on field naming.
CHECK_FIELD_SLUGS = {
    "Exact SKU / Supplier": "sku",
    "Design-Level IP QA": "ipqa",
    "Personalization Limits": "personalization_limits",
}

# Buyer role alone (bridesmaid, grandpa, ...) is inferred, not explicit --
# rule #5 requires explicit gift intent, so only occasion words or a literal
# "gift"/"gifts" token trigger the photo-brief Gift Context slot. See
# test_bare_buyer_role_alone_does_not_trigger_gift_context.
GIFT_OCCASIONS = {"wedding", "bachelorette", "birthday", "christmas"}


def _deep_freeze(val: Any) -> Any:
    if isinstance(val, dict):
        return tuple(sorted((k, _deep_freeze(v)) for k, v in val.items()))
    if isinstance(val, (list, set, tuple)):
        return tuple(_deep_freeze(v) for v in val)
    return val


def _canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class PriceFact:
    value: Optional[float]
    currency: str = "USD"
    provenance_type: str = "UNVERIFIED"
    verified: bool = False

    def __post_init__(self):
        currency = (self.currency or "").strip().upper()
        object.__setattr__(self, "currency", currency)
        if self.provenance_type not in VALID_PRICE_PROVENANCES:
            raise ValueError(f"Invalid price provenance_type: {self.provenance_type}")
        if not currency:
            raise ValueError("PriceFact currency cannot be empty")
        if self.provenance_type == "UNVERIFIED" and self.verified:
            raise ValueError("UNVERIFIED price provenance cannot have verified=True!")
        if self.value is None and self.verified:
            raise ValueError("PriceFact with value=None cannot be verified=True!")
        if self.value is not None and self.value <= 0:
            raise ValueError("Price value must be positive")

    @property
    def publish_eligible(self) -> bool:
        return bool(
            self.verified
            and self.provenance_type == "OWNER_SET"
            and self.value is not None
            and self.value > 0
            and self.currency
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProductTruthFact:
    field: str
    value: str
    verified: bool = False
    provenance_ref: str = ""

    def __post_init__(self):
        field = (self.field or "").strip().lower()
        value = (self.value or "").strip()
        provenance_ref = (self.provenance_ref or "").strip()
        object.__setattr__(self, "field", field)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "provenance_ref", provenance_ref)
        if field not in VALID_PRODUCT_TRUTH_FIELDS:
            raise ValueError(f"Invalid ProductTruthFact field: {field}")
        if not value:
            raise ValueError("ProductTruthFact value cannot be empty")
        if self.verified and not provenance_ref:
            raise ValueError("Verified ProductTruthFact requires provenance_ref")
        if self.verified and value == "UNVERIFIED":
            raise ValueError("UNVERIFIED ProductTruthFact cannot have verified=True")

    @property
    def revision_id(self) -> str:
        payload = {
            "field": self.field,
            "value": self.value,
            "provenance_ref": self.provenance_ref,
        }
        return f"pt-{hashlib.sha256(_canonical_json(payload).encode('utf-8')).hexdigest()[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["revision_id"] = self.revision_id
        return d


@dataclass(frozen=True)
class SupportedTerm:
    term: str
    origin_type: str
    evidence_ref_ids: Tuple[str, ...] = ()
    source_paths: Tuple[str, ...] = ()

    def __post_init__(self):
        if self.origin_type not in ("EVIDENCE", "SEMANTIC_INTENT"):
            raise ValueError(f"Invalid origin_type: {self.origin_type}")
        term = (self.term or "").lower().strip()
        object.__setattr__(self, "term", term)
        object.__setattr__(self, "evidence_ref_ids", _deep_freeze(self.evidence_ref_ids))
        object.__setattr__(self, "source_paths", _deep_freeze(self.source_paths))
        if self.origin_type == "EVIDENCE":
            if not self.evidence_ref_ids:
                raise ValueError("EVIDENCE supported term requires evidence_ref_ids")
            if not self.source_paths or len(self.source_paths) != len(self.evidence_ref_ids):
                raise ValueError("EVIDENCE supported term requires one source_path per evidence_ref_id")
            if any(not str(p).strip() for p in self.source_paths):
                raise ValueError("EVIDENCE source_paths cannot be empty")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRef:
    source: str
    retrieved_at: str
    provenance_hash: str
    match_type: str
    verdict: str
    raw_facts: Tuple[Tuple[str, Any], ...] = ()
    derived_metrics: Tuple[Tuple[str, Any], ...] = ()
    supported_terms_contained: Tuple[str, ...] = ()
    term_source_paths: Tuple[Tuple[str, str], ...] = ()

    def __post_init__(self):
        if self.match_type not in VALID_MATCH_TYPES:
            raise ValueError(f"Invalid match_type: {self.match_type}")
        if self.verdict not in VALID_VERDICTS:
            raise ValueError(f"Invalid verdict: {self.verdict}")
        object.__setattr__(self, "raw_facts", _deep_freeze(self.raw_facts))
        object.__setattr__(self, "derived_metrics", _deep_freeze(self.derived_metrics))
        normalized_sources = tuple(sorted(
            ((str(term).lower().strip(), str(path).strip()) for term, path in self.term_source_paths),
            key=lambda x: (x[0], x[1]),
        ))
        if any(not term or not path for term, path in normalized_sources):
            raise ValueError("EvidenceRef term_source_paths require non-empty term and path")
        object.__setattr__(self, "term_source_paths", normalized_sources)
        source_terms = {term for term, _ in normalized_sources}
        legacy_terms = {str(t).lower().strip() for t in self.supported_terms_contained if str(t).strip()}
        object.__setattr__(self, "supported_terms_contained", tuple(sorted(source_terms | legacy_terms)))

        computed = self.compute_content_hash()
        if self.provenance_hash and self.provenance_hash != computed:
            raise ValueError(
                f"Supplied provenance_hash '{self.provenance_hash}' does not match computed content_hash '{computed}'!"
            )
        object.__setattr__(self, "provenance_hash", computed)

    def compute_content_hash(self) -> str:
        payload = {
            "source": self.source,
            "match_type": self.match_type,
            "verdict": self.verdict,
            "raw_facts": self.raw_facts,
            "derived_metrics": self.derived_metrics,
            "supported_terms": self.supported_terms_contained,
            "term_source_paths": self.term_source_paths,
        }
        return f"ev-{hashlib.sha256(_canonical_json(payload).encode('utf-8')).hexdigest()[:12]}"

    @property
    def observation_id(self) -> str:
        payload = {"content_hash": self.provenance_hash, "retrieved_at": self.retrieved_at}
        return f"obs-{hashlib.sha256(_canonical_json(payload).encode('utf-8')).hexdigest()[:12]}"

    def source_paths_for_term(self, term: str) -> Tuple[str, ...]:
        t = (term or "").lower().strip()
        return tuple(path for candidate, path in self.term_source_paths if candidate == t)

    def same_content(self, other: "EvidenceRef") -> bool:
        return bool(
            isinstance(other, EvidenceRef)
            and self.provenance_hash == other.provenance_hash
            and self.source == other.source
            and self.match_type == other.match_type
            and self.verdict == other.verdict
            and self.raw_facts == other.raw_facts
            and self.derived_metrics == other.derived_metrics
            and self.supported_terms_contained == other.supported_terms_contained
            and self.term_source_paths == other.term_source_paths
        )

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
            "supported_terms_contained": list(self.supported_terms_contained),
            "term_source_paths": [list(x) for x in self.term_source_paths],
        }


def make_evidence_ref(
    source: str,
    retrieved_at: str,
    match_type: str,
    verdict: str,
    raw_facts: Optional[Dict[str, Any]] = None,
    derived_metrics: Optional[Dict[str, Any]] = None,
    supported_terms_contained: Optional[Sequence[str]] = None,
    term_source_paths: Optional[Sequence[Tuple[str, str]]] = None,
    provenance_hash: str = "",
) -> EvidenceRef:
    frozen_raw = _deep_freeze(raw_facts or {})
    frozen_derived = _deep_freeze(derived_metrics or {})
    terms = tuple(sorted(t.lower().strip() for t in (supported_terms_contained or []) if t.strip()))
    sources = tuple(term_source_paths or ())
    dummy_ref = EvidenceRef(
        source=source,
        retrieved_at=retrieved_at,
        provenance_hash="",
        match_type=match_type,
        verdict=verdict,
        raw_facts=frozen_raw,
        derived_metrics=frozen_derived,
        supported_terms_contained=terms,
        term_source_paths=sources,
    )
    return EvidenceRef(
        source=source,
        retrieved_at=retrieved_at,
        provenance_hash=provenance_hash or dummy_ref.provenance_hash,
        match_type=match_type,
        verdict=verdict,
        raw_facts=frozen_raw,
        derived_metrics=frozen_derived,
        supported_terms_contained=terms,
        term_source_paths=sources,
    )


@dataclass(frozen=True)
class MasterKeyword:
    revision_id: str
    keyword: str
    canonical_keyword: str
    mode: str
    opportunity_score: float
    market_verdict: str
    product_fit_status: str
    trademark_risk: str
    engine_action: str
    execution_action: str
    specificity_class: str
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
        return tuple(
            st.term for st in self.supported_terms
            if st.origin_type == "EVIDENCE" and st.evidence_ref_ids and st.source_paths
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["evidence_supported_tags"] = list(self.evidence_supported_tags)
        d["supported_terms"] = [st.to_dict() for st in self.supported_terms]
        return d


@dataclass(frozen=True)
class OwnerCheck:
    field: str
    category: str
    verified: bool = False
    note: str = ""
    subject_ref: str = ""

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
        fields = [f.field for f in self.product_truth_facts]
        if len(fields) != len(set(fields)):
            raise ValueError("Duplicate ProductTruthFact fields are not allowed")

    @property
    def publish_ready(self) -> bool:
        if not self.owner_checks or not self.price_fact.publish_eligible:
            return False

        check_map = {c.field: c for c in self.owner_checks}
        if len(self.owner_checks) != len(check_map):
            return False

        truth_map = {f.field: f for f in self.product_truth_facts}
        required_fields = set(BASE_REQUIRED_OWNER_CHECK_FIELDS)
        if "PERSONALIZATION INSTRUCTIONS" in self.buyer_copy:
            required_fields.add("Personalization Limits")

        # One loop over the single required-fields source of truth: every
        # field must be verified, and any field with a truth-fact binding
        # (per TRUTH_CHECK_TO_FIELD) must also have its exact fact revision
        # bound. required_fields and TRUTH_CHECK_TO_FIELD both derive from
        # OWNER_CHECK_SPECS, so a binding check can no longer be silently
        # skipped by the two sets drifting apart.
        for check_field in required_fields:
            check = check_map.get(check_field)
            if not check or not check.verified:
                return False
            truth_field = TRUTH_CHECK_TO_FIELD.get(check_field)
            if truth_field:
                fact = truth_map.get(truth_field)
                if not fact or not fact.verified or check.subject_ref != fact.revision_id:
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
    created_at: str = "",
) -> MasterKeyword:
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

    ev_map: Dict[str, EvidenceRef] = {}
    if evidence_refs:
        for ev in evidence_refs:
            h = ev.provenance_hash
            if h not in ev_map:
                ev_map[h] = ev
                continue
            existing = ev_map[h]
            if not existing.same_content(ev):
                raise ValueError(f"EvidenceRef hash collision detected for conflicting content: {h}")
            if (ev.retrieved_at or "") > (existing.retrieved_at or ""):
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
        "evidence_hashes": sorted_ev_hashes,
    }
    rev_id = f"mk-{hashlib.sha256(_canonical_json(hash_payload).encode('utf-8')).hexdigest()[:12]}"
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
        created_at=created_at,
    )


def compile_cluster(
    master: MasterKeyword,
    supported_terms: Optional[Sequence[SupportedTerm]] = None,
) -> ListingCluster:
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
            if st.origin_type != "EVIDENCE":
                continue
            verified_ids = []
            verified_paths = []
            for ref_id, requested_path in zip(st.evidence_ref_ids, st.source_paths):
                ev = valid_ev_map.get(ref_id)
                if not ev:
                    continue
                allowed_paths = ev.source_paths_for_term(st.term)
                if requested_path in allowed_paths:
                    verified_ids.append(ref_id)
                    verified_paths.append(requested_path)
            if verified_ids and st.term not in seen and len(st.term) <= MAX_TAG_LEN:
                seen.add(st.term)
                cluster_terms.append(SupportedTerm(
                    st.term,
                    "EVIDENCE",
                    tuple(verified_ids),
                    tuple(verified_paths),
                ))

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
        "tag_gap_count": tag_gap_count,
    }
    cluster_rev = f"lc-{hashlib.sha256(_canonical_json(cluster_payload).encode('utf-8')).hexdigest()[:12]}"
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
        compiler_version=COMPILER_VERSION,
    )


def compile_package(
    cluster: ListingCluster,
    owner_checks_override: Optional[Sequence[OwnerCheck]] = None,
    product_truth_facts_override: Optional[Sequence[ProductTruthFact]] = None,
    price_fact_override: Optional[PriceFact] = None,
) -> ListingPackage:
    kw_cap = cluster.primary_keyword.title()
    title = kw_cap
    evidence_tags = tuple(cluster.evidence_supported_tags)
    tag_gaps = tuple(f"TAG_GAP_{i + 1}" for i in range(cluster.tag_gap_count))

    if product_truth_facts_override:
        truth_facts = tuple(product_truth_facts_override)
    else:
        truth_facts = tuple(
            ProductTruthFact(field, "UNVERIFIED", False, "")
            for field in ("material", "dimensions", "colors", "shipping")
        )
    truth_fields = [f.field for f in truth_facts]
    if len(truth_fields) != len(set(truth_fields)):
        raise ValueError("Duplicate ProductTruthFact fields are not allowed")
    truth_map = {f.field: f for f in truth_facts}

    if owner_checks_override:
        checks = tuple(owner_checks_override)
    else:
        check_list = [OwnerCheck(name, category, False, msg)
                      for name, category, msg, _ in OWNER_CHECK_SPECS]
        if cluster.personalization_angles:
            check_list.append(OwnerCheck("Personalization Limits", "PRODUCT_TRUTH", False, "Character count limits unverified"))
        checks = tuple(check_list)

    check_map = {c.field: c for c in checks}
    if len(checks) != len(check_map):
        raise ValueError("Duplicate OwnerCheck fields are not allowed")

    if cluster.personalization_angles:
        buyer_copy_lines = [
            f"Personalized {kw_cap} — custom designed for {cluster.buyer_roles[0] if cluster.buyer_roles else 'special occasions'}.",
            "",
            "PERSONALIZATION INSTRUCTIONS",
            "• Enter the exact name, date, or text for customization.",
            "• Double-check spelling before submitting your order.",
        ]
    else:
        buyer_copy_lines = [f"{kw_cap}."]

    def _verified_bound_fact(truth_field: str, check_field: str) -> Optional[ProductTruthFact]:
        fact = truth_map.get(truth_field)
        check = check_map.get(check_field)
        if not fact or not check:
            return None
        if not fact.verified or not check.verified:
            return None
        if not fact.provenance_ref or check.subject_ref != fact.revision_id:
            return None
        return fact

    mat_fact = _verified_bound_fact("material", "Material Composition")
    if mat_fact:
        buyer_copy_lines.append(f"• Material: {mat_fact.value}")
    dim_fact = _verified_bound_fact("dimensions", "Dimensions & Sizing")
    if dim_fact:
        buyer_copy_lines.append(f"• Dimensions: {dim_fact.value}")
    buyer_copy = "\n".join(buyer_copy_lines)

    keyword_tokens = set(cluster.primary_keyword.lower().split())
    has_explicit_gift = bool(keyword_tokens & {"gift", "gifts"})
    has_gift_occasion = bool(set(cluster.occasions) & GIFT_OCCASIONS)
    has_gift_intent = has_explicit_gift or has_gift_occasion

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

    price_fact = price_fact_override or PriceFact(None, "USD", "UNVERIFIED", False)
    pkg_payload = {
        "cluster_revision_id": cluster.revision_id,
        "title": title,
        "evidence_tags": list(evidence_tags),
        "tag_gap_count": cluster.tag_gap_count,
        "buyer_copy": buyer_copy,
        "photo_brief": photo_brief,
        "product_truth_facts": [f.to_dict() for f in truth_facts],
        "price_fact": price_fact.to_dict(),
        "owner_checks": [c.to_dict() for c in checks],
    }
    pkg_rev = f"lp-{hashlib.sha256(_canonical_json(pkg_payload).encode('utf-8')).hexdigest()[:12]}"
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
        network_calls_made=0,
    )
