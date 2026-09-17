"""Schemas for the evidence-grounded Ask ClauseGuard explanation path."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class AskEvidence(BaseModel):
    evidence_id: str = Field(..., min_length=1, max_length=80)
    source: str = Field(..., min_length=1, max_length=40)
    type: str = Field(..., min_length=1, max_length=100)
    pattern: Optional[str] = Field(None, max_length=100)
    description: str = Field("", max_length=1500)
    strength: Optional[str] = Field(None, max_length=20)
    model_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    provenance: Optional[str] = Field(None, max_length=200)
    route: Optional[str] = Field(None, max_length=500)
    decision_context: Optional[str] = Field(None, max_length=80)
    temporal_position: Optional[str] = Field(None, max_length=40)
    event_indices: List[int] = Field(default_factory=list, max_length=50)
    element_ref: Optional[str] = Field(None, max_length=200)
    bounding_box: Optional[Dict[str, Any]] = None
    frame_id: Optional[str] = Field(None, max_length=100)
    value: Optional[Any] = None
    currency: Optional[str] = Field(None, max_length=20)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> str:
        return str(value or "").replace("\x00", "")[:1500]


class AskActiveFinding(BaseModel):
    """The deterministic finding currently selected by the canonical analysis."""
    pattern: str = Field(..., min_length=1, max_length=100)
    status: Optional[str] = Field(None, max_length=40)
    description: Optional[str] = Field(None, max_length=1500)
    why_it_matters: Optional[str] = Field(None, max_length=1500)
    recommended_action: Optional[str] = Field(None, max_length=1000)
    evidence_ids: List[str] = Field(default_factory=list, max_length=20)


class AskClauseGuardContext(BaseModel):
    """Allowlisted, read-only snapshot of the canonical post-gate result."""
    request_id: Optional[str] = Field(None, max_length=100)
    page_id: Optional[str] = Field(None, max_length=200)
    journey_id: Optional[str] = Field(None, max_length=200)
    route: Optional[str] = Field(None, max_length=500)
    decision_context: Optional[str] = Field(None, max_length=80)
    risk_level: str = Field("LOW", max_length=30)
    risk_score: float = Field(0.0, ge=0.0, le=10.0)
    gate_decision: str = Field("CLEAR", max_length=40)
    actionable: bool = False
    requires_context: bool = False
    risk_detected: bool = False
    primary_pattern: Optional[str] = Field(None, max_length=100)
    active_finding: Optional[AskActiveFinding] = None
    detected_patterns: List[str] = Field(default_factory=list, max_length=20)
    evidence: List[AskEvidence] = Field(default_factory=list, max_length=20)
    consequences: List[str] = Field(default_factory=list, max_length=10)
    financial_exposure: Optional[Any] = None
    consumer_effort: Optional[str] = Field(None, max_length=100)
    recommended_action: Optional[str] = Field(None, max_length=1000)
    regulatory_context: Optional[Dict[str, Any]] = None
    temporal_context: List[str] = Field(default_factory=list, max_length=20)
    contradiction_context: List[str] = Field(default_factory=list, max_length=20)
    provenance: List[Dict[str, Any]] = Field(default_factory=list, max_length=20)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_metadata: Optional[Dict[str, Any]] = None
    available_questions: List[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def cap_nested_context(self) -> "AskClauseGuardContext":
        for field_name in ("regulatory_context", "model_metadata"):
            value = getattr(self, field_name)
            if value is not None and len(str(value)) > 5000:
                raise ValueError(f"{field_name} is too large")
        return self


class AskRequest(BaseModel):
    request_id: Optional[str] = Field(None, max_length=100)
    question: str = Field(..., min_length=1, max_length=2000)
    context: AskClauseGuardContext
    current_page_id: Optional[str] = Field(None, max_length=200)
    current_journey_id: Optional[str] = Field(None, max_length=200)
    context_generated_at: Optional[datetime] = None
    conversation_history: List[str] = Field(default_factory=list, max_length=10)
    prefer_local_llm: bool = False

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        value = " ".join(value.replace("\x00", "").split())
        if not value:
            raise ValueError("`question` must not be empty")
        return value

    @model_validator(mode="after")
    def validate_context_identity(self) -> "AskRequest":
        if self.current_page_id and self.context.page_id and self.current_page_id != self.context.page_id:
            raise ValueError("context page does not match current page")
        if self.current_journey_id and self.context.journey_id and self.current_journey_id != self.context.journey_id:
            raise ValueError("context journey does not match current journey")
        if len(self.context.model_dump_json()) > 30000:
            raise ValueError("context exceeds maximum allowed size")
        return self


class AskResponse(BaseModel):
    request_id: str
    answer: str = Field(..., max_length=8000)
    intent: str
    answer_class: str
    grounded: bool
    evidence_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    requires_context: bool = False
    provider: str = "deterministic"
    model: str = "deterministic-templates"
    # Phase 4.4: decoder LLM traceability fields
    model_used: Optional[str] = None
    checkpoint_sha256: Optional[str] = None
    fallback_used: bool = False
    error_code: Optional[str] = None
    response_mode: Optional[str] = None


class AskErrorPayload(BaseModel):
    code: str
    message: str
    request_id: str


class AskErrorResponse(BaseModel):
    error: AskErrorPayload
