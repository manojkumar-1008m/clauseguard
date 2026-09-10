"""backend/schemas/evidence.py
Pydantic models for ClauseGuard Phase 8.6 & B5.1 Unified Evidence Contract.
Unified representations for cross-source evidence items, evidence groups,
financial impact, consumer consequences, and fusion responses.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, validator

from .price import PriceAnalysisResponse
from . import PredictResponse

# Controlled vocabularies for Phase B5.1
ALLOWED_SOURCES = {"text", "price", "behavior", "dom", "image", "system", "ui", "rules", "history"}
ALLOWED_STRENGTHS = {"weak", "moderate", "strong", "insufficient"}
ALLOWED_TEMPORAL_POSITIONS = {"before_action", "during_action", "after_action", "static", "unknown"}
ALLOWED_DECISION_CONTEXTS = {
    "cancellation",
    "subscription",
    "checkout",
    "billing",
    "consent",
    "purchase",
    "account_deletion",
    "membership",
    "renewal",
    "dialog",
    "unknown",
}

CONTEXT_FAMILY_MAP: Dict[str, str] = {
    # CANCELLATION FAMILY:
    "cancellation": "cancellation_family",
    "subscription": "cancellation_family",
    "membership": "cancellation_family",
    "renewal": "cancellation_family",
    # PURCHASE FAMILY:
    "checkout": "purchase_family",
    "billing": "purchase_family",
    "purchase": "purchase_family",
    # ACCOUNT FAMILY:
    "account_deletion": "account_family",
    # CONSENT FAMILY:
    "consent": "consent_family",
    # DIALOG FAMILY:
    "dialog": "dialog_family",
    # UNKNOWN FAMILY:
    "unknown": "unknown_family",
}


class StructuredProvenance(BaseModel):
    """Structured provenance metadata for traceable evidence audit (Part 13)."""
    source: str = Field(..., description="Originating source subsystem")
    model_version: Optional[str] = Field(None, description="Model or analyzer version")
    timestamp: Optional[float] = Field(None, description="Epoch timestamp of evidence creation")
    page_load_id: Optional[str] = Field(None, description="Unique identifier for the page load session")
    session_id: Optional[str] = Field(None, description="Active user interaction session identifier")
    tab_id: Optional[int] = Field(None, description="Browser tab identifier")
    frame_id: Optional[str] = Field(None, description="DOM frame or iframe identifier")

    @validator("source")
    def validate_source(cls, v: str) -> str:
        s = v.lower()
        if s not in ALLOWED_SOURCES:
            raise ValueError(f"Invalid provenance source '{v}'. Must be one of {sorted(ALLOWED_SOURCES)}")
        return s


class EvidenceItem(BaseModel):
    """Atomic evidence item with deterministic provenance, multimodal context, and identification."""
    evidence_id: str = Field(..., description="Deterministic unique identifier (e.g. E001, E002)")
    source: str = Field(..., description="Origin source: 'text', 'price', 'behavior', 'dom', 'image', 'system'")
    type: str = Field(..., description="Specific evidence type (e.g. 'subscription_trap', 'renewal_price', 'free_trial', 'late_disclosure')")
    pattern: Optional[str] = Field(None, description="Standardized dark pattern category if applicable")
    description: str = Field(default="", description="Factual description of the evidence")
    value: Optional[Any] = Field(None, description="Extracted value (numeric, string, or boolean)")
    currency: Optional[str] = Field(None, description="Currency code if monetary")

    # Detection & Evidence Strength (Part 1 & 2)
    detected: bool = Field(default=True, description="Whether the signal was observed/detected")
    strength: Optional[str] = Field(default=None, description="Observable evidence quality: 'weak', 'moderate', 'strong', 'insufficient'")

    # ML Confidence vs. Evidence Strength (Part 2)
    model_confidence: Optional[float] = Field(default=None, description="ML model output probability only (0.0 to 1.0)")
    confidence: Optional[float] = Field(default=None, description="Legacy backward-compatible confidence score (0.0 to 1.0)")

    # Spatial / Textual Provenance
    character_start: Optional[int] = Field(None, description="Character start offset in original text if applicable")
    character_end: Optional[int] = Field(None, description="Character end offset in original text if applicable")

    # DOM & Behavioral Provenance (Part 1, 10, 11)
    element_ref: Optional[str] = Field(None, description="DOM selector, tag, or element reference identifier")
    event_indices: List[int] = Field(default_factory=list, description="Interaction event indices associated with this evidence")
    route: Optional[str] = Field(None, description="Navigation route or page path")
    route_sequence: List[str] = Field(default_factory=list, description="Sequence of routes traversed")

    # Decision Context & Temporal Position (Part 4 & 5)
    decision_context: Optional[str] = Field(None, description="Decision domain context: cancellation, subscription, checkout, etc.")
    temporal_position: Optional[str] = Field(None, description="Temporal position: before_action, during_action, after_action, static, unknown")

    # Phase B5.4 Journey Boundary Fields
    journey_id: Optional[str] = Field(None, description="Opaque unique journey identifier (jrn_<uuid4 hex>)")
    journey_stage: Optional[str] = Field(None, description="Canonical journey stage: PRODUCT, CART, CHECKOUT, etc.")
    is_auxiliary: bool = Field(default=False, description="True if evidence originates from an auxiliary context (e.g. privacy, terms)")

    # Phase B5.5 Evidence Graph & Event Clustering Fields
    event_node_id: Optional[str] = Field(None, description="Deterministic event node ID if clustered")

    # Phase B5.6 Cross-Page Continuity & Transaction State Fields
    continuity_status: Optional[str] = Field(None, description="Continuity classification: CONTINUOUS, UNEXPECTED, UNKNOWN, UNCERTAIN")
    continuity_confidence: Optional[float] = Field(None, description="Confidence of continuity relationship (0.0 to 1.0; does not modify model_confidence)")
    anchor_tier: Optional[str] = Field(None, description="Product anchor quality tier: STRONG, MODERATE, WEAK, UNKNOWN")

    # Visual / Image Attributes (Part 12)
    bounding_box: Optional[Dict[str, Any]] = Field(None, description="Visual bounding box coordinates (e.g. x, y, width, height)")
    frame_id: Optional[str] = Field(None, description="Visual frame or iframe identifier")

    # Severity & Provenance (Part 13)
    severity: Optional[str] = Field(None, description="Severity rating: 'low', 'medium', 'high'")
    provenance: Optional[Union[str, StructuredProvenance]] = Field(None, description="Originating analyzer component or structured provenance")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional contextual metadata")

    @validator("source")
    def validate_source(cls, v: str) -> str:
        s = v.lower()
        if s not in ALLOWED_SOURCES:
            raise ValueError(f"Invalid source '{v}'. Must be one of {sorted(ALLOWED_SOURCES)}")
        return s

    @validator("strength")
    def validate_strength(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.lower()
        if s not in ALLOWED_STRENGTHS:
            raise ValueError(f"Invalid strength '{v}'. Must be one of {sorted(ALLOWED_STRENGTHS)}")
        return s

    @validator("model_confidence")
    def validate_model_confidence(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if not (0.0 <= v <= 1.0):
                raise ValueError(f"model_confidence must be between 0.0 and 1.0, got {v}")
        return v

    @validator("confidence")
    def validate_confidence(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if not (0.0 <= v <= 1.0):
                raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v

    @validator("temporal_position")
    def validate_temporal_position(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.lower()
        if s not in ALLOWED_TEMPORAL_POSITIONS:
            raise ValueError(f"Invalid temporal_position '{v}'. Must be one of {sorted(ALLOWED_TEMPORAL_POSITIONS)}")
        return s

    @validator("decision_context")
    def validate_decision_context(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.lower()
        if s not in ALLOWED_DECISION_CONTEXTS:
            raise ValueError(f"Invalid decision_context '{v}'. Must be one of {sorted(ALLOWED_DECISION_CONTEXTS)}")
        return s


class EvidenceGroup(BaseModel):
    """Cluster of related evidence items describing a unified risk or pattern."""
    group_id: str = Field(..., description="Deterministic group identifier (e.g. G001, G002)")
    pattern: Optional[str] = Field(None, description="Standardized pattern category unifying this group")
    evidence_ids: List[str] = Field(default_factory=list, description="IDs of constituent evidence items")
    sources: List[str] = Field(default_factory=list, description="List of unique sources contributing to this group")
    corroborated: bool = Field(False, description="True when multiple independent sources support this pattern")
    description: Optional[str] = Field(None, description="Summary of how constituent signals relate")


class EvidenceConflict(BaseModel):
    """Traceable record of conflicting evidence between sources."""
    type: str = Field(default="evidence_conflict", description="Classification of the conflict")
    sources: List[str] = Field(default_factory=list, description="Conflicting sources")
    description: str = Field(..., description="Description of the conflicting facts")
    resolution: str = Field(default="preserve_both", description="Conflict resolution policy ('preserve_both')")


class FinancialImpact(BaseModel):
    """Structured financial impact metrics extracted from price evidence."""
    initial_price: Optional[float] = Field(None, description="Displayed upfront or initial price")
    additional_cost: Optional[float] = Field(None, description="Additional mandatory fee or surcharge")
    known_total: Optional[float] = Field(None, description="Authoritative or computed total price")
    additional_cost_percentage: Optional[float] = Field(None, description="Percentage of additional fee relative to base price")
    trial_price: Optional[float] = Field(None, description="Trial period price (0 for free trial)")
    trial_duration_days: Optional[int] = Field(None, description="Trial duration in days")
    renewal_price: Optional[float] = Field(None, description="Recurring renewal price")
    billing_period: Optional[str] = Field(None, description="Billing cycle: day, week, month, year")
    currency: Optional[str] = Field(None, description="Currency code")
    previous_price: Optional[float] = Field(None, description="Former price in price-change relationship")
    current_price: Optional[float] = Field(None, description="New price in price-change relationship")
    price_change: Optional[float] = Field(None, description="Numeric price difference (current - previous)")
    price_change_percentage: Optional[float] = Field(None, description="Percentage price change")


class ConsumerConsequence(BaseModel):
    """Structured consumer consequence derived from combined evidence."""
    type: Optional[str] = Field(None, description="Consequence classification (e.g. 'recurring_charge', 'additional_fee', 'price_change')")
    amount: Optional[float] = Field(None, description="Monetary consequence amount")
    currency: Optional[str] = Field(None, description="Currency code")
    period: Optional[str] = Field(None, description="Billing or recurring period")
    description: Optional[str] = Field(None, description="Factual description of the consumer consequence")


class EvidenceFusionRequest(BaseModel):
    """Request payload for Evidence Fusion Engine."""
    text: Optional[str] = Field(None, description="Raw input text to analyze across pipelines")
    text_prediction: Optional[PredictResponse] = Field(None, description="Pre-computed text prediction response")
    price_analysis: Optional[PriceAnalysisResponse] = Field(None, description="Pre-computed price analysis response")
    ui_evidence: Optional[Union[List[EvidenceItem], List[Dict[str, Any]], Dict[str, Any], Any]] = Field(default_factory=list, description="External UI/DOM evidence items (legacy alias)")
    dom_evidence: Optional[Union[List[EvidenceItem], List[Dict[str, Any]], Dict[str, Any], Any]] = Field(default_factory=list, description="External DOM / interaction context evidence items")
    behavior_evidence: Optional[Union[List[EvidenceItem], List[Dict[str, Any]], Dict[str, Any], Any]] = Field(default_factory=list, description="External user behavior evidence items")
    image_evidence: Optional[Union[List[EvidenceItem], List[Dict[str, Any]], Dict[str, Any], Any]] = Field(default_factory=list, description="External visual / image evidence items")
    raw_evidence: Optional[Union[List[EvidenceItem], List[Dict[str, Any]], Dict[str, Any], Any]] = Field(default_factory=list, description="Additional arbitrary evidence items")


class ContradictionItem(BaseModel):
    """Deterministic, traceable record of semantic incompatibility between observable sources (Part A)."""
    contradiction_id: str = Field(..., description="Deterministic contradiction identifier (e.g. C001)")
    type: str = Field(..., description="Contradiction type (e.g. text_vs_dom, text_vs_behavior, text_vs_price, price_before_vs_after, dom_vs_behavior, image_vs_text)")
    source_a: str = Field(..., description="First evidence source (e.g. text)")
    source_b: str = Field(..., description="Second evidence source (e.g. dom)")
    pattern: Optional[str] = Field(None, description="Related dark pattern category if applicable (e.g. obstruction, drip_pricing)")
    severity: Literal["weak", "moderate", "strong"] = Field(default="moderate", description="Contradiction evidence severity: weak, moderate, strong")
    reason: str = Field(..., description="Explainable description of the semantic contradiction")
    evidence_ids: List[str] = Field(default_factory=list, description="IDs of conflicting evidence items")
    event_indices: Optional[List[int]] = Field(default=None, description="Chronological event indices associated with the contradiction")
    route: Optional[str] = Field(None, description="Page route or URL where contradiction occurred")
    decision_context: Optional[str] = Field(None, description="Decision context (e.g. cancellation, checkout)")


class TemporalRelationshipItem(BaseModel):
    """Deterministic record of state change or temporal progression across user interactions (Part E)."""
    temporal_id: str = Field(..., description="Deterministic temporal relationship identifier (e.g. T001)")
    type: str = Field(..., description="Temporal relationship type (e.g. price_change_after_action, fee_added_after_action, option_added_after_action, action_disabled_after_action, alternative_removed_after_action, modal_appeared_after_action, required_step_appeared_after_action)")
    before_evidence_ids: List[str] = Field(default_factory=list, description="IDs of evidence observing state before action")
    after_evidence_ids: List[str] = Field(default_factory=list, description="IDs of evidence observing state after action")
    event_indices: Optional[List[int]] = Field(default=None, description="Chronological event indices spanning the interaction")
    route: Optional[str] = Field(None, description="Page route or URL where transition occurred")
    decision_context: Optional[str] = Field(None, description="Decision context governing the temporal event")
    strength: Literal["weak", "moderate", "strong"] = Field(default="moderate", description="Evidence strength of the temporal relationship")
    reason: str = Field(..., description="Explainable description of what changed across the interaction")


class EvidenceFusionResponse(BaseModel):
    """Unified response payload from Evidence Fusion Engine."""
    source: str = Field(default="evidence_fusion", description="Source analyzer identifier")
    risk_level: str = Field(default="LOW", description="Deterministic risk level: 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'")
    risk_score: float = Field(default=0.0, description="Deterministic risk score")
    confidence: Optional[float] = Field(None, description="Evidence-backed confidence between 0.0 and 1.0")
    potential_pattern: Optional[str] = Field(None, description="Primary detected pattern if corroborated or strongly indicated")
    dark_pattern: Optional[str] = Field(None, description="Dark pattern label if warranted; null for pure financial signals")
    financial_signal: bool = Field(default=False, description="True if an objective financial change or structure exists")
    is_corroborated: bool = Field(default=False, description="True if multi-source corroboration was achieved")
    requires_context: bool = Field(default=False, description="True if evidence lacks sufficient context for high confidence")
    context_requirements: Dict[str, bool] = Field(
        default_factory=lambda: {
            "text": False,
            "price": False,
            "behavior": False,
            "dom": False,
            "image": False,
        },
        description="Source-scoped context requirements mapping (Part 6)",
    )
    evidence_groups: List[EvidenceGroup] = Field(default_factory=list, description="Grouped evidence clusters")
    evidence: List[EvidenceItem] = Field(default_factory=list, description="All individual detected evidence items")
    conflicts: List[EvidenceConflict] = Field(default_factory=list, description="Detected cross-source contradictions")
    financial_impact: Optional[FinancialImpact] = Field(None, description="Structured financial impact metrics")
    consumer_consequence: Optional[ConsumerConsequence] = Field(None, description="Structured consumer consequence")
    # Phase 9.1: Text + Price Evidence Fusion fields
    risk_detected: bool = Field(default=False, description="True if a potential consumer risk was detected")
    primary_pattern: Optional[str] = Field(None, description="Primary detected pattern category if risk detected or corroborated")
    signals: List[str] = Field(default_factory=list, description="Extracted high-level text and price signals")
    supporting_evidence: List[EvidenceItem] = Field(default_factory=list, description="Evidence items directly supporting the primary finding")
    price_changed: Optional[bool] = Field(default=None, description="True if an explicit price change was detected")
    renewal_signal: Optional[bool] = Field(default=None, description="True if a renewal or recurring price structure was detected")
    # Phase B5.3: Contradiction & Temporal Evidence fields
    contradictions: List[ContradictionItem] = Field(default_factory=list, description="Detected cross-source semantic contradictions (Part A & K)")
    temporal_relationships: List[TemporalRelationshipItem] = Field(default_factory=list, description="Detected before/after temporal state changes (Part E & K)")
    # Phase B5.5: Evidence Graph & Event Clustering fields
    evidence_graph: Optional[Dict[str, Any]] = Field(None, description="Deterministic evidence graph representation (Phase B5.5)")
    # Phase B5.6: Cross-Page Continuity & Transaction State fields
    transaction_state: Optional[Dict[str, Any]] = Field(None, description="Deterministic transaction state and continuity ledger (Phase B5.6)")
    # Phase B5.7: Intelligence Analysis Layer fields
    intelligence_analysis: Optional[IntelligenceAnalysisResponse] = Field(None, description="Structured intelligence analysis output (Phase B5.7)")


class PatternAssessment(BaseModel):
    """Structured assessment of a potential dark pattern (Phase B5.7)."""
    pattern: str = Field(..., description="Dark pattern category (e.g. SUBSCRIPTION_TRAP, DRIP_PRICING)")
    status: Literal["NOT_SUPPORTED", "POTENTIAL", "SUPPORTED"] = Field(..., description="Pattern support status")
    confidence: float = Field(default=0.0, description="Confidence in pattern assessment (0.0 to 1.0)")
    severity: Literal["low", "moderate", "strong"] = Field(default="moderate", description="Assessed severity")
    decision_context: Optional[str] = Field(None, description="Decision domain context")
    reason: str = Field(default="", description="Explainable description of the pattern assessment")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="IDs of supporting evidence items")
    consumer_consequence: Optional[str] = Field(None, description="Direct consumer consequence of this pattern")


class ConsumerConsequenceDetail(BaseModel):
    """Structured consumer consequence derived from unified evidence (Phase B5.7)."""
    type: str = Field(..., description="Consequence classification (e.g. recurring_charge, additional_fee, price_change)")
    actual_cost: Optional[float] = Field(None, description="Current known cost")
    future_cost: Optional[float] = Field(None, description="Future committed cost if known")
    renewal_cost: Optional[float] = Field(None, description="Recurring renewal amount")
    financial_exposure: Optional[Union[float, str]] = Field(None, description="Monetary exposure or 'UNKNOWN'")
    currency: Optional[str] = Field(None, description="Currency code")
    period: Optional[str] = Field(None, description="Billing cycle: day, week, month, year")
    trial_duration: Optional[str] = Field(None, description="Duration of free or discounted trial")
    consumer_effort: Optional[str] = Field(None, description="Effort required: low, moderate, high_friction")
    consumer_consequence: str = Field(..., description="Explainable consumer consequence description")
    recommended_action: Optional[str] = Field(None, description="Objective, non-legal protective suggestion")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="Traceable evidence IDs")


class HistoricalChangeDetail(BaseModel):
    """Factual record of historical change between verified states (Phase B5.7)."""
    category: Literal["PRICE_CHANGE", "TERMS_CHANGE", "UI_CHANGE", "RENEWAL_CHANGE", "CANCELLATION_CHANGE", "FEE_CHANGE"] = Field(..., description="Historical change category")
    previous_value: Optional[Any] = Field(None, description="Former value or 'UNKNOWN'")
    current_value: Optional[Any] = Field(None, description="Current observed value")
    absolute_change: Optional[float] = Field(None, description="Numeric difference if quantifiable")
    percentage_change: Optional[float] = Field(None, description="Percentage change if quantifiable")
    currency: Optional[str] = Field(None, description="Currency code if monetary")
    description: str = Field(..., description="Factual description of the change")
    is_dark_pattern: bool = Field(default=False, description="Factual flag: price change is not automatically dark pattern")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="Traceable evidence IDs")
    journey_id: Optional[str] = Field(None, description="Journey identifier establishing continuity")


class IntelligenceAnalysisResponse(BaseModel):
    """Structured output from Intelligence Analysis Layer (Phase B5.7)."""
    pattern_assessments: List[PatternAssessment] = Field(default_factory=list, description="Assessed dark pattern intelligence")
    consumer_consequences: List[ConsumerConsequenceDetail] = Field(default_factory=list, description="Structured consumer consequences")
    historical_changes: List[HistoricalChangeDetail] = Field(default_factory=list, description="Factual historical comparisons")
    supporting_evidence: List[str] = Field(default_factory=list, description="All evidence IDs supporting the analysis")
    requires_context: bool = Field(default=False, description="True if context is insufficient for conclusive pattern analysis")


ContradictionItem.model_rebuild()
TemporalRelationshipItem.model_rebuild()
PatternAssessment.model_rebuild()
ConsumerConsequenceDetail.model_rebuild()
HistoricalChangeDetail.model_rebuild()
IntelligenceAnalysisResponse.model_rebuild()
EvidenceFusionResponse.model_rebuild()


