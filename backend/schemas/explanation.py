"""backend/schemas/explanation.py
Pydantic schemas for ClauseGuard Phase 8.7 Consumer Explanation & Action Engine.
Transforms structured evidence from Evidence Fusion into transparent,
consumer-facing explanations, consequence summaries, and recommended actions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .evidence import EvidenceFusionRequest, EvidenceFusionResponse


class ConsumerExplanationFinding(BaseModel):
    """An individual, prioritized consumer-facing explanation finding."""
    finding_id: str = Field(..., description="Deterministic finding identifier (e.g. F001, F002)")
    type: str = Field(..., description="Explanation type: subscription_risk, additional_fee, late_disclosure, price_change, urgency, scarcity, etc.")
    title: str = Field(..., description="Concise, non-alarming title (WHAT WE FOUND)")
    summary: str = Field(..., description="User-friendly summary of the finding")
    consumer_consequence: Optional[str] = Field(None, description="Explanation of why it matters to the consumer (WHY IT MATTERS)")
    financial_consequence: Optional[str] = Field(None, description="Quantified financial impact if applicable (FINANCIAL IMPACT)")
    recommended_action: str = Field(..., description="Specific, practical step for the consumer (WHAT YOU CAN DO)")
    evidence_ids: List[str] = Field(default_factory=list, description="Associated EvidenceItem identifiers for traceability")
    pattern: Optional[str] = Field(None, description="Normalized pattern taxonomy if applicable")
    priority: int = Field(default=6, description="Priority rank (1=financial consequence, 2=recurring, 3=mandatory fee, 4=late disclosure, 5=UI manipulation, 6=informational)")
    requires_context: bool = Field(default=False, description="True if this finding requires additional context")
    evidence_summary: List[str] = Field(default_factory=list, description="Bullet points of concrete evidence supporting this finding")


class ExplanationRequest(BaseModel):
    """Request schema for generating consumer explanations."""
    fusion_response: Optional[EvidenceFusionResponse] = Field(None, description="Pre-computed EvidenceFusionResponse")
    text: Optional[str] = Field(None, description="Raw input text to analyze across full pipeline")
    fusion_request: Optional[EvidenceFusionRequest] = Field(None, description="Raw fusion request payload")


class ExplanationResponse(BaseModel):
    """Complete user-facing explanation and action payload."""
    source: str = Field(default="consumer_explanation", description="Origin service identifier")
    risk_status: str = Field(..., description="'no_strong_signal', 'risk_detected', 'financial_notice', or 'context_required'")
    title: str = Field(..., description="Primary headline: WHAT WE FOUND")
    summary: str = Field(..., description="Concise explanation of the overall transaction risk")
    evidence_summary: List[str] = Field(default_factory=list, description="Bulleted list of concrete evidence facts")
    consumer_consequence: Optional[str] = Field(None, description="Consumer consequence: WHY IT MATTERS")
    financial_consequence: Optional[str] = Field(None, description="Financial impact: WHAT COULD IT COST")
    recommended_action: str = Field(..., description="Practical next step: WHAT YOU CAN DO")
    evidence_ids: List[str] = Field(default_factory=list, description="All supporting evidence IDs")
    pattern: Optional[str] = Field(None, description="Primary detected pattern if applicable")
    requires_context: bool = Field(default=False, description="True if overall evaluation requires more context")
    confidence: Optional[float] = Field(None, description="Evidence-backed confidence rating")
    disclaimer: Optional[str] = Field(None, description="Compact disclaimer for risk findings")
    findings: List[ConsumerExplanationFinding] = Field(default_factory=list, description="Prioritized list of individual findings")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Machine-readable metadata for frontend rendering")
