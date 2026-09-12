"""Isolated calculator for explainable dark-pattern risk contributions."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Dict, List

from .risk_rules import CANONICAL_PATTERN_SEVERITY, PATTERN_SEVERITY, calculate_pattern_score
from .risk_taxonomy_adapter import adapt_pattern


MAX_DARK_PATTERN_RISK = 100.0


def _assessment_value(assessment: Any, field: str) -> Any:
    """Read a field from a PatternAssessment object or dictionary."""
    if isinstance(assessment, Mapping):
        return assessment[field]
    return getattr(assessment, field)


def calculate_dark_pattern_risk(
    assessments: Iterable[Any],
) -> Dict[str, Any]:
    """Calculate a capped score from existing PatternAssessment values.

    This is a dark-pattern score only; it is not a legal conclusion or an
    overall system risk score. Unknown patterns or rule values raise an error
    so configuration mismatches remain visible and deterministic.
    """
    contributing_patterns: List[Dict[str, Any]] = []
    reasons: List[str] = []
    total_score = 0.0

    for assessment in assessments:
        pattern = _assessment_value(assessment, "pattern")
        status = _assessment_value(assessment, "status")
        confidence = _assessment_value(assessment, "confidence")
        severity = _assessment_value(assessment, "severity")
        adaptation = adapt_pattern(pattern)
        if adaptation["status"] != "SUPPORTED":
            reasons.append(
                f"{pattern} contributed 0.00 points: {adaptation['reason']}"
            )
            continue

        if pattern in PATTERN_SEVERITY:
            scoring_pattern = pattern
        elif adaptation["canonical_pattern"] in CANONICAL_PATTERN_SEVERITY:
            scoring_pattern = adaptation["canonical_pattern"]
        else:
            reasons.append(
                f"{pattern} maps to {adaptation['canonical_pattern']} but has no configured "
                "Risk Engine weight; it contributed 0.00 points."
            )
            continue

        score = calculate_pattern_score(scoring_pattern, status, severity, confidence)

        if score <= 0.0:
            continue

        rounded_score = round(score, 2)
        contributing_patterns.append(
            {
                "pattern": pattern,
                "score": rounded_score,
                "status": status,
                "severity": severity,
                "confidence": max(0.0, min(1.0, confidence)),
            }
        )
        assessment_reason = _assessment_value(assessment, "reason")
        reason = (
            f"{pattern} contributed {rounded_score:.2f} points "
            f"(status={status}, severity={severity}, confidence={confidence})."
        )
        if assessment_reason:
            reason += f" Assessment: {assessment_reason}"
        reasons.append(reason)
        total_score += score

    risk_score = round(max(0.0, min(MAX_DARK_PATTERN_RISK, total_score)), 2)
    if not reasons:
        reasons.append("No supported or potential dark-pattern assessment contributed to the score.")

    return {
        "risk_score": risk_score,
        "contributing_patterns": contributing_patterns,
        "reasons": reasons,
    }