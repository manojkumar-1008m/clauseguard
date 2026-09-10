"""backend/schemas/__init__.py
Pydantic models for ClauseGuard API request/response payloads.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, validator

from .price import (
    DisplayedPrice,
    PriceAnalysisRequest,
    PriceAnalysisResponse,
    PriceEntity,
)


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


from .evidence import (
    ConsumerConsequence,
    EvidenceConflict,
    EvidenceFusionRequest,
    EvidenceFusionResponse,
    EvidenceGroup,
    EvidenceItem,
    FinancialImpact,
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
]


