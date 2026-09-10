"""backend/schemas/regulatory.py
Structured Pydantic schemas for ClauseGuard Phase B5.8 — Regulatory Check layer.
Enforces non-legal conclusion invariants, structured status taxonomy, and traceable provenance.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from .evidence import EvidenceItem, IntelligenceAnalysisResponse, PatternAssessment


RegulatoryStatusType = Literal["NOT_APPLICABLE", "POTENTIALLY_RELEVANT", "SUPPORTED", "UNKNOWN", "UNSUPPORTED_RULE"]
ApplicabilityType = Literal["APPLICABLE", "NOT_APPLICABLE", "UNKNOWN"]


class RegulatoryFinding(BaseModel):
    """Structured regulatory finding matching validated evidence and patterns against authoritative rules.
    
    CRITICAL INVARIANT:
    Must NOT contain definitive legal conclusions (e.g. 'This website violates the law' or 'Illegal').
    All findings express potential regulatory concern, applicability conditions, and evidence traceability.
    """
    finding_id: str = Field(..., description="Deterministic unique finding identifier")
    jurisdiction: str = Field(..., description="Jurisdiction code (e.g. 'IN', 'EU', 'US', 'UK', 'UNKNOWN')")
    jurisdiction_confidence: float = Field(default=0.0, description="Confidence in jurisdiction resolution (0.0 to 1.0)")
    regulation_id: str = Field(..., description="Authoritative regulation identifier (e.g. 'IN_CCPA_DP_2023')")
    rule_id: str = Field(..., description="Specific rule or clause identifier (e.g. 'IN_CCPA_DRIP_PRICING')")
    rule_name: str = Field(..., description="Human-readable rule name")
    pattern: str = Field(..., description="Associated dark pattern category (e.g. DRIP_PRICING, SUBSCRIPTION_TRAP)")
    status: RegulatoryStatusType = Field(..., description="Status: NOT_APPLICABLE, POTENTIALLY_RELEVANT, SUPPORTED, UNKNOWN, UNSUPPORTED_RULE")
    applicability: ApplicabilityType = Field(..., description="Temporal and jurisdictional applicability")
    effective_from: Optional[str] = Field(None, description="ISO date string from which regulation became effective")
    effective_to: Optional[str] = Field(None, description="ISO date string until which regulation was effective (or None)")
    confidence: float = Field(default=0.0, description="Regulatory applicability confidence (distinct from model confidence)")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="IDs of supporting evidence items (must be valid)")
    supporting_assessment_ids: List[str] = Field(default_factory=list, description="IDs or keys of supporting pattern assessments")
    explanation: str = Field(..., description="Explainable description avoiding legal assertions")
    source: str = Field(..., description="Authoritative statutory/regulatory citation")
    rule_version: str = Field(default="1.0.0", description="Version of the registry rule")
    regulated_entity_type: Optional[str] = Field(None, description="Regulated entity type (e.g. ONLINE_PLATFORM, TRADER)")
    service_scope: Optional[str] = Field(None, description="Service scope requirement")
    requires_entity_scope: bool = Field(default=False, description="Whether specific entity scope must be verified")
    authority_type: Optional[str] = Field(None, description="Authority classification (e.g. EU_DIRECTIVE, EU_REGULATION, GENERAL_CONSUMER_PROTECTION_AUTHORITY)")
    requires_member_state_mapping: bool = Field(default=False, description="Whether directive requires national Member State transposition mapping")
    mapping_type: Optional[str] = Field(None, description="Mapping nature (e.g. SPECIFIC_STATUTORY_PROHIBITION, POTENTIAL_APPLICABILITY)")


class RegulatoryCheckRequest(BaseModel):
    """Request payload for Regulatory Check evaluation."""
    intelligence_analysis: Optional[IntelligenceAnalysisResponse] = Field(None, description="Output from Phase B5.7 Intelligence Analysis")
    raw_evidence: List[EvidenceItem] = Field(default_factory=list, description="Input evidence items for provenance verification")
    jurisdiction: Optional[str] = Field(None, description="Explicit jurisdiction code if known (e.g. 'IN', 'EU', 'US', 'UK')")
    transaction_date: Optional[str] = Field(None, description="ISO 8601 date string of transaction (e.g. '2024-05-15')")
    journey_id: Optional[str] = Field(None, description="Journey boundary identifier")
    product_id: Optional[str] = Field(None, description="Product anchor identifier")
    tab_id: Optional[str] = Field(None, description="Browser tab identifier")
    include_non_applicable: bool = Field(True, description="Whether to include NOT_APPLICABLE findings")
    entity_type: Optional[str] = Field(None, description="Entity type of website/service (e.g. 'ONLINE_PLATFORM', 'TRADER', 'UNKNOWN')")
    member_state: Optional[str] = Field(None, description="Specific EU Member State code if resolved (e.g. 'DE', 'FR', 'IT')")


class RegulatoryCheckResponse(BaseModel):
    """Structured response from Regulatory Check layer."""
    findings: List[RegulatoryFinding] = Field(default_factory=list, description="Deterministic regulatory findings")
    jurisdiction_resolved: Optional[str] = Field(None, description="Resolved jurisdiction code or 'UNKNOWN'")
    jurisdiction_confidence: float = Field(default=0.0, description="Confidence in jurisdiction resolution")
    supported_rule_registry: bool = Field(default=True, description="Whether the resolved jurisdiction is supported by the configured rule registry")
    rule_available: bool = Field(default=True, description="Whether configured rules exist for this resolved jurisdiction")
    requires_jurisdiction: bool = Field(default=False, description="True if jurisdiction could not be resolved from context")
    requires_date: bool = Field(default=False, description="True if transaction date was missing for date-dependent rules")
    supporting_evidence: List[str] = Field(default_factory=list, description="Collation of all supporting evidence IDs")
    limitation: Optional[str] = Field(None, description="Explains scope and registry coverage limitations")


RegulatoryFinding.model_rebuild()
RegulatoryCheckRequest.model_rebuild()
RegulatoryCheckResponse.model_rebuild()
