"""backend/schemas/__init__.py
Pydantic models for ClauseGuard API request/response payloads.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator

from .price import (
    DisplayedPrice,
    PriceAnalysisRequest,
    PriceAnalysisResponse,
    PriceEntity,
)
from .explanation_context import ExplanationContext
from .ask import AskActiveFinding, AskClauseGuardContext, AskEvidence, AskErrorResponse, AskRequest, AskResponse


class PredictRequest(BaseModel):
    text: str = Field(..., description="The text to analyze for dark patterns")

    @validator("text")
    def non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("`text` must be a non‑empty string")
        if len(v) > 5000:
            raise ValueError("`text` exceeds maximum allowed length (5000 characters)")
        return v


class PredictResponse(BaseModel):
    prediction: int = Field(..., description="Binary prediction 0=not_dark_pattern, 1=potential_dark_pattern")
    label: str = Field(..., description="Human‑readable label")
    confidence: Optional[float] = Field(None, description="Probability of the positive class, if available")
    model_version: str = Field(..., description="Version identifier for the model used")
    requires_context: bool = Field(False, description="Whether additional context is needed for the prediction")
    pattern_category: Optional[str] = Field(None, description="Identified dark pattern taxonomy category")
    evidence: Optional[str] = Field(None, description="Smallest meaningful textual span demonstrating the pattern")
    consumer_consequence: Optional[str] = Field(None, description="Potential consumer consequence")


class HealthResponse(BaseModel):
    status: str = Field(..., description="Overall health status")
    model_loaded: bool = Field(..., description="True if the model was successfully loaded at startup")
    model_version: str = Field(..., description="Model version identifier")


class ModelInfoResponse(BaseModel):
    model_version: str
    algorithm: str
    dataset_version: str
    training_date: str
    python_version: str
    scikit_learn_version: str
    expected_input: str
    output_labels: List[str]
    artifact: Optional[str] = None
    artifact_sha256: Optional[str] = None


class AnalyzeRequest(BaseModel):
    text: Optional[str] = Field(None, description="Raw page or clause text to evaluate")
    price_analysis: Optional[Any] = Field(None, description="Optional price analysis payload")
    dom_evidence: Optional[Union[List[Any], Dict[str, Any], Any]] = Field(default_factory=list)
    behavior_evidence: Optional[Union[List[Any], Dict[str, Any], Any]] = Field(default_factory=list)
    raw_evidence: Optional[Union[List[Any], Dict[str, Any], Any]] = Field(default_factory=list)
    image_evidence: Optional[Union[List[Any], Dict[str, Any], Any]] = Field(default_factory=list)
    jurisdiction: Optional[str] = None
    transaction_date: Optional[str] = None
    entity_type: Optional[str] = None
    member_state: Optional[str] = None

    @validator("text")
    def bounded_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("`text` must be a string")
        if len(v) > 20000:
            raise ValueError("`text` exceeds maximum allowed length (20000 characters)")
        return v


class AnalyzeResponse(BaseModel):
    status: str = Field(default="ok", description="Analysis status")
    risk_score: float = Field(..., description="Canonical risk score on the verified 0-10 ClauseGuard scale")
    score_breakdown: Optional[ScoreBreakdown] = Field(None, description="Canonical explainable risk-score breakdown")
    risk_level: str = Field(..., description="Canonical risk level")
    risk_detected: bool = Field(default=False)
    potential_pattern: Optional[str] = Field(None)
    dark_pattern: Optional[str] = Field(None)
    confidence: Optional[float] = Field(None)
    model_version: str = Field(...)
    evidence_count: int = Field(default=0)
    consumer_gate: Dict[str, Any] = Field(default_factory=dict)
    explanation: Optional[ExplanationResponse] = Field(None)
    explanation_context: Optional[ExplanationContext] = Field(None)
    evidence: List[Any] = Field(default_factory=list)
    context_requirements: Dict[str, bool] = Field(default_factory=dict)
    regulatory_assessment: Optional[Any] = None
    generated_at: Optional[str] = None



class ConsumerRiskGateResult(BaseModel):
    decision: str = Field(default="allow", description="allow, review, block")
    risk_score: float = Field(...)
    risk_level: str = Field(...)
    threshold: float = Field(default=7.0)
    message: str = Field(default="")


from .evidence import (
    ConsumerConsequence,
    EvidenceConflict,
    EvidenceFusionRequest,
    EvidenceFusionResponse,
    EvidenceGroup,
    EvidenceItem,
    FinancialImpact,
    ScoreBreakdown,
)

from .explanation import (
    ConsumerExplanationFinding,
    ExplanationRequest,
    ExplanationResponse,
)


__all__ = [
    "PredictRequest",
    "PredictResponse",
    "HealthResponse",
    "ModelInfoResponse",
    "AnalyzeRequest",
    "AnalyzeResponse",
    "ConsumerRiskGateResult",
    "DisplayedPrice",
    "PriceAnalysisRequest",
    "PriceAnalysisResponse",
    "PriceEntity",
    "EvidenceItem",
    "EvidenceGroup",
    "EvidenceConflict",
    "FinancialImpact",
    "ConsumerConsequence",
    "EvidenceFusionRequest",
    "EvidenceFusionResponse",
    "ConsumerExplanationFinding",
    "ExplanationRequest",
    "ExplanationResponse",
    "ExplanationContext",
    "AskClauseGuardContext",
    "AskActiveFinding",
    "AskEvidence",
    "AskErrorResponse",
    "AskRequest",
    "AskResponse",
]


