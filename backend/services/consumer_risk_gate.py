"""Canonical consumer risk gate for the verified 0-10 ClauseGuard risk scale."""

from __future__ import annotations

from typing import Any, Dict


class ConsumerRiskGate:
    """Decide whether a risk score is allowed, needs review, or should be blocked."""

    def __init__(self, actionable_threshold: float = 5.0):
        self.actionable_threshold = float(actionable_threshold)

    def _determine_level(self, score: float) -> str:
        if score >= 8.0:
            return "CRITICAL"
        if score >= 5.0:
            return "HIGH"
        if score >= 3.0:
            return "MEDIUM"
        return "LOW"

    def evaluate(self, result: Any) -> Dict[str, Any]:
        score = 0.0
        if hasattr(result, "risk_score"):
            score = float(getattr(result, "risk_score"))
        elif isinstance(result, dict):
            score = float(result.get("risk_score", 0.0))

        normalized = max(0.0, min(10.0, score))
        requires_context = bool(getattr(result, "requires_context", False)) if not isinstance(result, dict) else bool(result.get("requires_context", False))
        risk_detected = bool(getattr(result, "risk_detected", False)) if not isinstance(result, dict) else bool(result.get("risk_detected", False))
        intelligence = getattr(result, "intelligence_analysis", None) if not isinstance(result, dict) else result.get("intelligence_analysis")
        assessments = getattr(intelligence, "pattern_assessments", []) if intelligence is not None else []
        if isinstance(intelligence, dict):
            assessments = intelligence.get("pattern_assessments", [])
        if assessments and all((getattr(item, "status", item.get("status") if isinstance(item, dict) else None) == "NOT_SUPPORTED") for item in assessments):
            return {
                "decision": "SUPPRESSED",
                "risk_score": round(normalized, 2),
                "risk_level": self._determine_level(normalized),
                "actionable": False,
                "message": "The available findings were not supported by sufficient evidence.",
            }
        if requires_context:
            return {
                "decision": "POTENTIAL",
                "risk_score": round(normalized, 2),
                "risk_level": self._determine_level(normalized),
                "actionable": False,
                "message": "Additional context is required; no actionable risk decision was inferred.",
            }
        if not risk_detected:
            return {
                "decision": "CLEAR",
                "risk_score": round(normalized, 2),
                "risk_level": self._determine_level(normalized),
                "actionable": False,
                "message": "No actionable risk signal was detected.",
            }
        level = self._determine_level(normalized)
        if normalized >= self.actionable_threshold:
            decision = "ACTIONABLE_RISK"
            message = "Supported consumer-risk evidence warrants protective review."
        else:
            decision = "POTENTIAL"
            message = "A potential signal was observed but does not meet the actionable threshold."

        return {
            "decision": decision,
            "risk_score": round(normalized, 2),
            "risk_level": level,
            "actionable_threshold": self.actionable_threshold,
            "actionable": decision == "ACTIONABLE_RISK",
            "message": message,
        }