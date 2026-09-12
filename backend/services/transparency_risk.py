"""Isolated Consumer-Consequence and transparency risk calculator.

This component scores how clearly a consequence is presented and how much
consumer effort or future commitment it describes. It does not calculate
financial exposure and does not make legal conclusions.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, List


MAX_TRANSPARENCY_RISK = 100.0

EFFORT_SCORES = {
    "minimal": 5.0,
    "low": 10.0,
    "moderate": 25.0,
    "high_friction": 40.0,
}

FUTURE_COMMITMENT_SCORE = 10.0
RECURRING_COMMITMENT_SCORE = 20.0
MISSING_EFFORT_SCORE = 3.0
MISSING_CONSEQUENCE_SCORE = 3.0
UNKNOWN_OUTCOME_SCORE = 4.0

_HIGH_SEVERITY_WORDING = (
    "unknown",
    "unverified",
    "not disclosed",
    "without prominent",
    "hidden",
    "later",
    "surprise",
    "unclear",
    "may be higher",
    "without easy cancellation",
    "extra steps",
    "contacting customer support",
)


def _value(source: Any, field: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(field, default)
    return getattr(source, field, default)


def _has_value(value: Any) -> bool:
    return value is not None and value != ""


def _has_numeric_value(value: Any) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _consequence_severity(consequence_type: Any, wording: str) -> tuple[float, str]:
    if any(term in wording for term in _HIGH_SEVERITY_WORDING):
        return 30.0, "unclear or delayed consequence wording"
    if consequence_type == "friction_interference":
        return 24.0, "cancellation or choice friction consequence"
    if consequence_type in {"recurring_charge", "additional_fee", "price_change"}:
        return 18.0, f"material {consequence_type} consequence"
    if wording:
        return 5.0, "clearly described consequence"
    return 0.0, "missing consequence wording"


def calculate_transparency_risk(consequence: Any = None) -> Dict[str, Any]:
    """Calculate a deterministic score from one ConsumerConsequenceDetail."""
    if consequence is None:
        return {
            "risk_score": 0.0,
            "contributing_factors": [],
            "reasons": [
                "No consumer consequence was supplied; no transparency or consequence risk was assessed."
            ],
        }

    contributing_factors: List[Dict[str, Any]] = []
    reasons: List[str] = []
    total_score = 0.0
    effort = _value(consequence, "consumer_effort")
    consequence_type = _value(consequence, "type")
    wording_value = _value(consequence, "consumer_consequence")
    wording = wording_value.lower() if isinstance(wording_value, str) else ""

    if effort in EFFORT_SCORES:
        score = EFFORT_SCORES[effort]
        contributing_factors.append({"factor": "consumer_effort", "score": score, "value": effort})
        reasons.append(f"Consumer effort '{effort}' contributed {score:.2f} points.")
        total_score += score
    else:
        reasons.append(
            f"Consumer effort was unavailable or unrecognized ({effort!r}); "
            f"{MISSING_EFFORT_SCORE:.2f} uncertainty points were applied."
        )
        contributing_factors.append(
            {"factor": "missing_effort_information", "score": MISSING_EFFORT_SCORE, "value": effort}
        )
        total_score += MISSING_EFFORT_SCORE

    severity_score, severity_reason = _consequence_severity(consequence_type, wording)
    if severity_score:
        contributing_factors.append(
            {"factor": "consequence_transparency", "score": severity_score, "type": consequence_type}
        )
        reasons.append(f"The consequence represents {severity_reason} and contributed {severity_score:.2f} points.")
        total_score += severity_score
    else:
        reasons.append(
            f"Consumer consequence wording was unavailable; {MISSING_CONSEQUENCE_SCORE:.2f} uncertainty points were applied."
        )
        contributing_factors.append(
            {"factor": "missing_consequence_information", "score": MISSING_CONSEQUENCE_SCORE}
        )
        total_score += MISSING_CONSEQUENCE_SCORE

    renewal_present = _has_numeric_value(_value(consequence, "renewal_cost"))
    future_present = _has_numeric_value(_value(consequence, "future_cost"))
    recurring_type = consequence_type == "recurring_charge"
    recurring_period = recurring_type and _has_value(_value(consequence, "period"))
    trial_present = _has_value(_value(consequence, "trial_duration"))

    if renewal_present or recurring_type or recurring_period:
        score = RECURRING_COMMITMENT_SCORE
        commitment_reason = "recurring or renewal obligation"
    elif (future_present and consequence_type != "additional_fee") or trial_present:
        score = FUTURE_COMMITMENT_SCORE
        commitment_reason = "future commitment or trial transition"
    else:
        score = 0.0
        commitment_reason = "no future commitment was identified"

    if score:
        contributing_factors.append({"factor": "future_commitment", "score": score, "type": consequence_type})
        reasons.append(f"A {commitment_reason} contributed {score:.2f} points.")
        total_score += score
    else:
        reasons.append("No future commitment or renewal implication was identified; no commitment points were applied.")

    outcome = _value(consequence, "financial_exposure")
    outcome_uncertain = outcome == "UNKNOWN" or (
        consequence_type in {"recurring_charge", "additional_fee"}
        and not _has_value(outcome)
    )
    missing_information_score = 0.0
    if outcome_uncertain:
        missing_information_score += UNKNOWN_OUTCOME_SCORE
        reasons.append(
            f"The consequence outcome was unavailable or UNKNOWN; {UNKNOWN_OUTCOME_SCORE:.2f} uncertainty points were applied."
        )

    if missing_information_score:
        contributing_factors.append(
            {
                "factor": "missing_or_uncertain_information",
                "score": missing_information_score,
            }
        )
        total_score += missing_information_score

    risk_score = round(max(0.0, min(MAX_TRANSPARENCY_RISK, total_score)), 2)
    return {
        "risk_score": risk_score,
        "contributing_factors": contributing_factors,
        "reasons": reasons,
    }