"""Isolated Historical / Behavioral Change Risk calculator."""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any, Dict, List, Optional


MAX_HISTORICAL_RISK = 100.0
MATERIALITY_MAX_POINTS = 40.0
DARK_PATTERN_POINTS = 20.0
EVIDENCE_POINTS = 10.0
ABSOLUTE_CHANGE_REFERENCE = 1000.0

CATEGORY_POINTS = {
    "RENEWAL_CHANGE": 30.0,
    "CANCELLATION_CHANGE": 30.0,
    "FEE_CHANGE": 25.0,
    "TERMS_CHANGE": 25.0,
    "PRICE_CHANGE": 15.0,
    "UI_CHANGE": 10.0,
}


def _value(source: Any, field: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(field, default)
    return getattr(source, field, default)


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _changes(value: Any) -> List[Any]:
    if value is None:
        return []
    wrapped = _value(value, "historical_changes", None)
    if wrapped is not None:
        return list(wrapped)
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
        return list(value)
    return [value]


def _materiality(change: Any) -> tuple[float, str]:
    percentage = _number(_value(change, "percentage_change"))
    if percentage is not None:
        factor = min(1.0, abs(percentage) / 100.0)
        return MATERIALITY_MAX_POINTS * factor, f"verified percentage change of {percentage:g}%"

    absolute = _number(_value(change, "absolute_change"))
    if absolute is not None:
        amount = abs(absolute)
        factor = amount / (amount + ABSOLUTE_CHANGE_REFERENCE) if amount else 0.0
        return MATERIALITY_MAX_POINTS * factor, f"verified absolute change of {absolute:g}"

    return 0.0, "no verified percentage or absolute change was available"


def calculate_historical_risk(historical_changes: Any = None) -> Dict[str, Any]:
    """Calculate a deterministic 0-100 score from existing historical changes."""
    changes = _changes(historical_changes)
    if not changes:
        return {
            "risk_score": 0.0,
            "contributing_factors": [],
            "reasons": [
                "No historical changes were supplied; the Historical / Behavioral Change Risk score is 0.00."
            ],
        }

    contributing_factors: List[Dict[str, Any]] = []
    reasons: List[str] = []
    total_score = 0.0

    for index, change in enumerate(changes, start=1):
        category = str(_value(change, "category", "UNKNOWN")).strip().upper()
        materiality_score, materiality_reason = _materiality(change)
        category_score = CATEGORY_POINTS.get(category, 0.0)
        dark_pattern_score = DARK_PATTERN_POINTS if _value(change, "is_dark_pattern", False) is True else 0.0
        evidence_ids = _value(change, "supporting_evidence_ids", []) or []
        evidence_score = EVIDENCE_POINTS if bool(evidence_ids) else 0.0
        change_score = materiality_score + category_score + dark_pattern_score + evidence_score

        factor_scores = {
            "materiality": round(materiality_score, 2),
            "category_impact": round(category_score, 2),
            "verified_dark_pattern": round(dark_pattern_score, 2),
            "evidence_traceability": round(evidence_score, 2),
        }
        for factor, score in factor_scores.items():
            if score > 0.0:
                contributing_factors.append(
                    {
                        "factor": factor,
                        "change_index": index,
                        "category": category,
                        "score": score,
                    }
                )

        reasons.append(
            f"Change {index} ({category}) contributed {change_score:.2f} points: "
            f"{materiality_reason}; category impact {category_score:.2f}; "
            f"explicit dark-pattern relationship {dark_pattern_score:.2f}; "
            f"evidence traceability {evidence_score:.2f}."
        )
        if _number(_value(change, "percentage_change")) is None and _number(_value(change, "absolute_change")) is None:
            reasons.append(
                f"Change {index} had no verified magnitude, so no materiality points were inferred."
            )
        if not evidence_ids:
            reasons.append(
                f"Change {index} had no supporting evidence IDs, so it was not treated as fully traceable."
            )
        total_score += change_score

    risk_score = round(max(0.0, min(MAX_HISTORICAL_RISK, total_score)), 2)
    if total_score > MAX_HISTORICAL_RISK:
        reasons.append("The combined historical-change contribution was capped at 100.00 points.")

    return {
        "risk_score": risk_score,
        "contributing_factors": contributing_factors,
        "reasons": reasons,
    }