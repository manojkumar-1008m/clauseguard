"""Isolated aggregator for the five independent Risk Engine components."""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Dict, List, Optional


MAX_OVERALL_RISK = 100.0

COMPONENT_WEIGHTS = {
    "dark_pattern_risk": 0.30,
    "financial_risk": 0.25,
    "transparency_risk": 0.20,
    "regulatory_risk": 0.15,
    "historical_risk": 0.10,
}


def _value(source: Any, field: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(field, default)
    return getattr(source, field, default)


def _score(component: Any) -> Optional[float]:
    value = component if isinstance(component, (int, float)) else _value(component, "risk_score")
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(0.0, min(MAX_OVERALL_RISK, number))


def _component_reasons(component: Any) -> List[str]:
    reasons = _value(component, "reasons", [])
    if reasons is None:
        return []
    if isinstance(reasons, str):
        return [reasons]
    return [str(reason) for reason in reasons]


def _risk_level(score: float) -> str:
    if score <= 20.0:
        return "VERY_LOW"
    if score <= 40.0:
        return "LOW"
    if score <= 60.0:
        return "MODERATE"
    if score <= 80.0:
        return "HIGH"
    return "VERY_HIGH"


def calculate_overall_risk(
    dark_pattern_risk: Any = None,
    financial_risk: Any = None,
    transparency_risk: Any = None,
    regulatory_risk: Any = None,
    historical_risk: Any = None,
) -> Dict[str, Any]:
    """Aggregate existing component outputs without recalculating their risk."""
    components = {
        "dark_pattern_risk": dark_pattern_risk,
        "financial_risk": financial_risk,
        "transparency_risk": transparency_risk,
        "regulatory_risk": regulatory_risk,
        "historical_risk": historical_risk,
    }
    component_scores: Dict[str, Optional[float]] = {}
    weighted_contributions: Dict[str, float] = {}
    reasons: List[str] = []
    weighted_total = 0.0

    for component_name, weight in COMPONENT_WEIGHTS.items():
        component = components[component_name]
        score = _score(component)
        component_scores[component_name] = score
        contribution = (score or 0.0) * weight
        weighted_contributions[component_name] = round(contribution, 2)
        weighted_total += contribution

        if score is None:
            reasons.append(
                f"{component_name} did not provide a numeric risk_score; "
                "its weighted contribution was 0.00 and no risk was inferred."
            )
        else:
            reasons.append(
                f"{component_name} score {score:.2f} × weight {weight:.2f} "
                f"contributed {contribution:.2f}."
            )

        for component_reason in _component_reasons(component):
            reasons.append(f"{component_name}: {component_reason}")

    overall_score = round(max(0.0, min(MAX_OVERALL_RISK, weighted_total)), 2)
    return {
        "overall_score": overall_score,
        "risk_level": _risk_level(overall_score),
        "component_scores": component_scores,
        "weighted_contributions": weighted_contributions,
        "reasons": reasons,
    }