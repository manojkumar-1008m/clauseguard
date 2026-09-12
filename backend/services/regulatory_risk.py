"""Isolated translation of regulatory findings into Regulatory Risk."""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any, Dict, List


MAX_REGULATORY_RISK = 100.0
UNKNOWN_RISK_CAP = 10.0

STATUS_BASE_POINTS = {
    "SUPPORTED": 60.0,
    "POTENTIALLY_RELEVANT": 30.0,
    "UNKNOWN": 0.0,
    "NOT_APPLICABLE": 0.0,
    "UNSUPPORTED_RULE": 0.0,
}

CONFIDENCE_POINTS = 15.0
JURISDICTION_POINTS = 15.0
TRACEABILITY_POINTS = 10.0


def _value(source: Any, field: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(field, default)
    return getattr(source, field, default)


def _bounded(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return max(0.0, min(1.0, number))


def _applicability_factor(applicability: Any) -> float:
    if applicability == "APPLICABLE":
        return 1.0
    if applicability == "UNKNOWN":
        return 0.5
    return 0.0


def _jurisdiction_factor(finding: Any) -> float:
    jurisdiction = str(_value(finding, "jurisdiction", "UNKNOWN")).strip().upper()
    if jurisdiction == "UNKNOWN":
        return 0.0
    return _bounded(_value(finding, "jurisdiction_confidence", 0.0))


def _traceability_factor(finding: Any) -> float:
    has_evidence = bool(_value(finding, "supporting_evidence_ids", []))
    has_assessments = bool(_value(finding, "supporting_assessment_ids", []))
    if has_evidence and has_assessments:
        return 1.0
    if has_evidence or has_assessments:
        return 0.5
    return 0.0


def _findings(value: Any) -> List[Any]:
    if value is None:
        return []
    response_findings = _value(value, "findings", None)
    if response_findings is not None:
        return list(response_findings)
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
        return list(value)
    return []


def calculate_regulatory_risk(regulatory_response_or_findings: Any = None) -> Dict[str, Any]:
    """Calculate a deterministic 0-100 score from existing regulatory findings.

    This function translates existing regulatory output only. It does not
    create rules, determine applicability, or make legal conclusions.
    """
    factors: List[Dict[str, Any]] = []
    reasons: List[str] = []
    total_score = 0.0

    for finding in _findings(regulatory_response_or_findings):
        status = _value(finding, "status", "UNKNOWN")
        applicability = _value(finding, "applicability", "UNKNOWN")
        confidence = _bounded(_value(finding, "confidence", 0.0))
        jurisdiction_factor = _jurisdiction_factor(finding)
        applicability_factor = _applicability_factor(applicability)
        traceability_factor = _traceability_factor(finding)

        if status in ("NOT_APPLICABLE", "UNSUPPORTED_RULE"):
            reasons.append(f"Finding {_value(finding, 'finding_id', '<unknown>')} contributed 0.00 points because it is {status}.")
            continue

        if status == "UNKNOWN":
            score = min(
                UNKNOWN_RISK_CAP,
                5.0 * confidence * jurisdiction_factor * applicability_factor
                + 5.0 * confidence * applicability_factor * traceability_factor,
            )
            if score > 0.0:
                factors.append(
                    {
                        "factor": "regulatory_uncertainty",
                        "finding_id": _value(finding, "finding_id"),
                        "score": round(score, 2),
                        "status": status,
                    }
                )
                total_score += score
            reasons.append(
                f"Finding {_value(finding, 'finding_id', '<unknown>')} indicates regulatory relevance could not be confirmed; "
                f"it contributed {score:.2f} uncertainty points and was capped below confirmed findings."
            )
            continue

        base_points = STATUS_BASE_POINTS.get(status, 0.0)
        if base_points == 0.0:
            reasons.append(f"Finding {_value(finding, 'finding_id', '<unknown>')} has an unrecognized status and contributed 0.00 points.")
            continue

        score = (
            base_points * confidence * jurisdiction_factor * applicability_factor * traceability_factor
            + CONFIDENCE_POINTS * confidence * jurisdiction_factor * applicability_factor * traceability_factor
            + JURISDICTION_POINTS * confidence * jurisdiction_factor * applicability_factor * traceability_factor
            + TRACEABILITY_POINTS * traceability_factor
        )
        score = min(MAX_REGULATORY_RISK, max(0.0, score))
        if score > 0.0:
            factors.append(
                {
                    "factor": "regulatory_finding",
                    "finding_id": _value(finding, "finding_id"),
                    "score": round(score, 2),
                    "status": status,
                    "confidence": confidence,
                    "jurisdiction_confidence": jurisdiction_factor,
                    "applicability": applicability,
                    "traceability_factor": traceability_factor,
                }
            )
            total_score += score
        label = "supported regulatory finding" if status == "SUPPORTED" else "potential regulatory concern"
        reasons.append(
            f"Finding {_value(finding, 'finding_id', '<unknown>')} was treated as a {label} "
            f"and contributed {score:.2f} points after confidence, jurisdiction, applicability, and provenance factors."
        )

    risk_score = round(max(0.0, min(MAX_REGULATORY_RISK, total_score)), 2)
    if not _findings(regulatory_response_or_findings):
        reasons.append("No regulatory findings were supplied; the Regulatory Risk score is 0.00.")

    return {
        "risk_score": risk_score,
        "contributing_factors": factors,
        "reasons": reasons,
    }