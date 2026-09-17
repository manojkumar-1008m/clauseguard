"""Verified, read-only context passed from deterministic analysis toward explanation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExplanationContext(BaseModel):
    """Explanation input; it has no field or capability for risk determination."""

    risk_result: Dict[str, Any] = Field(default_factory=dict)
    pattern: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    evidence_descriptions: List[str] = Field(default_factory=list)
    consequence: Optional[str] = None
    financial_exposure: Optional[Any] = None
    consumer_effort: Optional[str] = None
    recommended_action: Optional[str] = None
    decision_context: Optional[str] = None
    regulatory_assessment: Optional[Dict[str, Any]] = None
    requires_context: bool = False
    provenance: List[Dict[str, Any]] = Field(default_factory=list)
