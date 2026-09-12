"""Isolated design rules for dark-pattern risk contributions.

These weights are configurable design values, not learned values or legal
determinations. This module does not calculate an overall system risk score.
"""
from __future__ import annotations

from typing import Dict


PATTERN_SEVERITY: Dict[str, float] = {
    "activity_message": 20,
    "countdown_timer": 35,
    "limited_time_message": 30,
    "low_stock_message": 30,
    "high_demand_message": 30,
    "default_choice": 40,
    "attention_distraction": 25,
    "nagging": 35,
    "disguised_ads": 40,
    "gamification": 25,
}

# Deterministic Risk Engine design weights for canonical Intelligence patterns.
# These are not learned values or legal severity determinations.
CANONICAL_PATTERN_SEVERITY: Dict[str, float] = {
    "SUBSCRIPTION_TRAP": 40,
    "DRIP_PRICING": 40,
    "BASKET_SNAKING": 35,
    "FALSE_URGENCY": 35,
    "SCARCITY": 30,
    "FORCED_ACTION": 40,
    "CONFIRM_SHAMING": 30,
    "OBSTRUCTION": 40,
    "MISDIRECTION": 30,
    "SOCIAL_PROOF": 25,
}

STATUS_FACTORS: Dict[str, float] = {
    "SUPPORTED": 1.00,
    "POTENTIAL": 0.60,
    "NOT_SUPPORTED": 0.00,
}

SEVERITY_FACTORS: Dict[str, float] = {
    "strong": 1.00,
    "moderate": 0.65,
    "low": 0.30,
}


def calculate_pattern_score(
    pattern: str,
    status: str,
    severity: str,
    confidence: float,
) -> float:
    """Calculate one isolated dark-pattern score contribution.

    Confidence is bounded to the inclusive range [0, 1]. Unknown rule keys
    raise KeyError so configuration errors remain visible and deterministic.
    """
    bounded_confidence = max(0.0, min(1.0, confidence))
    if pattern in PATTERN_SEVERITY:
        base_severity = PATTERN_SEVERITY[pattern]
    else:
        base_severity = CANONICAL_PATTERN_SEVERITY[pattern]

    return (
        base_severity
        * STATUS_FACTORS[status]
        * SEVERITY_FACTORS[severity]
        * bounded_confidence
    )