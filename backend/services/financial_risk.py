"""Isolated, explainable Financial Risk calculator.

The calculator consumes verified financial fields already produced by the
Price Analyzer, Evidence Fusion, and Intelligence layers. Missing values and
the string ``UNKNOWN`` are not converted to zero; they make no measurable
contribution and are reported in the result.

The component weights are design values, not learned values:

* verified exposure: up to 50 points;
* recurring or renewal commitment: up to 20 points;
* verified additional fee: up to 15 points;
* verified positive price increase: up to 15 points.

Each monetary amount uses the transparent saturation curve
``amount / (amount + 1000)``. The reference amount is a scoring scale only;
currencies are never converted or compared across records.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any, Dict, List, Optional, Tuple


MAX_FINANCIAL_RISK = 100.0
EXPOSURE_REFERENCE_AMOUNT = 1000.0
EXPOSURE_WEIGHT = 50.0
RECURRING_WEIGHT = 20.0
ADDITIONAL_FEE_WEIGHT = 15.0
PRICE_INCREASE_WEIGHT = 15.0
RECURRING_STRUCTURE_POINTS = 5.0
PRICE_CHANGE_REFERENCE_PERCENTAGE = 100.0

_MISSING = object()
_PRICE_CHANGE_CATEGORIES = {"PRICE_CHANGE", "RENEWAL_CHANGE", "FEE_CHANGE"}


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


def _positive_max(values: Iterable[Any]) -> Optional[float]:
    numbers = [number for value in values if (number := _number(value)) is not None and number > 0]
    return max(numbers) if numbers else None


def _positive_change(source: Any) -> Tuple[Optional[float], Optional[float]]:
    absolute_change = _number(_value(source, "price_change", _MISSING))
    if absolute_change is None:
        absolute_change = _number(_value(source, "absolute_change", _MISSING))

    percentage_change = _number(_value(source, "price_change_percentage", _MISSING))
    if percentage_change is None:
        percentage_change = _number(_value(source, "percentage_change", _MISSING))

    if absolute_change is None:
        previous = _number(_value(source, "previous_price", _MISSING))
        current = _number(_value(source, "current_price", _MISSING))
        if previous is None:
            previous = _number(_value(source, "previous_value", _MISSING))
        if current is None:
            current = _number(_value(source, "current_value", _MISSING))
        if previous is not None and current is not None:
            absolute_change = current - previous

    return (
        absolute_change if absolute_change is not None and absolute_change > 0 else None,
        percentage_change if percentage_change is not None and percentage_change > 0 else None,
    )


def _amount_factor(amount: Optional[float]) -> float:
    if amount is None:
        return 0.0
    return amount / (amount + EXPOSURE_REFERENCE_AMOUNT)


def _first_numeric(*values: Any) -> Optional[float]:
    for value in values:
        number = _number(value)
        if number is not None:
            return number
    return None


def calculate_financial_risk(
    financial_impact: Any = None,
    consumer_consequence: Any = None,
    historical_changes: Iterable[Any] = (),
    price_analysis: Any = None,
) -> Dict[str, Any]:
    """Calculate a deterministic Financial Risk score from existing outputs."""
    contributing_factors: List[Dict[str, Any]] = []
    reasons: List[str] = []
    total_score = 0.0

    exposure = _positive_max(
        (
            _value(consumer_consequence, "financial_exposure"),
            _value(consumer_consequence, "future_cost"),
            _value(consumer_consequence, "renewal_cost"),
            _value(consumer_consequence, "actual_cost"),
            _value(financial_impact, "known_total"),
            _value(price_analysis, "known_total"),
        )
    )
    if exposure is not None:
        score = EXPOSURE_WEIGHT * _amount_factor(exposure)
        contributing_factors.append({"factor": "verified_exposure", "score": round(score, 2), "amount": exposure})
        reasons.append(f"Verified financial exposure of {exposure:g} contributed {score:.2f} points.")
        total_score += score

    renewal_amount = _positive_max(
        (
            _value(consumer_consequence, "renewal_cost"),
            _value(financial_impact, "renewal_price"),
            _value(price_analysis, "renewal_price"),
        )
    )
    recurring_signal = bool(
        _value(price_analysis, "recurring", False)
        or _value(price_analysis, "renewal_price_detected", False)
        or _value(consumer_consequence, "type") == "recurring_charge"
        or renewal_amount is not None
    )
    if recurring_signal:
        amount_points = (RECURRING_WEIGHT - RECURRING_STRUCTURE_POINTS) * _amount_factor(renewal_amount)
        score = RECURRING_STRUCTURE_POINTS + amount_points
        contributing_factors.append({"factor": "recurring_or_renewal", "score": round(score, 2), "amount": renewal_amount})
        if renewal_amount is None:
            reasons.append(
                "A recurring or renewal commitment was verified, but its amount was missing; "
                f"only {RECURRING_STRUCTURE_POINTS:.2f} structural points were applied."
            )
        else:
            reasons.append(f"Verified recurring or renewal amount of {renewal_amount:g} contributed {score:.2f} points.")
        total_score += score

    additional_fee = _positive_max(
        (
            _value(financial_impact, "additional_cost"),
            _value(price_analysis, "additional_cost"),
            _value(price_analysis, "additional_costs"),
            _value(consumer_consequence, "financial_exposure")
            if _value(consumer_consequence, "type") == "additional_fee"
            else None,
        )
    )
    additional_percentage = _positive_max(
        (
            _value(financial_impact, "additional_cost_percentage"),
            _value(price_analysis, "additional_cost_percentage"),
        )
    )
    additional_signal = bool(
        additional_fee is not None
        or _value(price_analysis, "additional_cost_detected", False)
        or _value(consumer_consequence, "type") == "additional_fee"
    )
    if additional_signal:
        amount_points = 10.0 * _amount_factor(additional_fee)
        percentage_points = 5.0 * min(1.0, (additional_percentage or 0.0) / PRICE_CHANGE_REFERENCE_PERCENTAGE)
        score = amount_points + percentage_points
        if score > 0.0:
            contributing_factors.append({"factor": "additional_fee", "score": round(score, 2), "amount": additional_fee, "percentage": additional_percentage})
            reasons.append(f"Verified additional fee data contributed {score:.2f} points.")
            total_score += score
        else:
            reasons.append("An additional fee was detected without a verified amount or percentage; no fee points were assigned.")

    change_amounts: List[float] = []
    change_percentages: List[float] = []
    for source in (financial_impact, price_analysis):
        amount, percentage = _positive_change(source)
        if amount is not None:
            change_amounts.append(amount)
        if percentage is not None:
            change_percentages.append(percentage)
    for change in historical_changes or ():
        if _value(change, "category") in _PRICE_CHANGE_CATEGORIES:
            amount, percentage = _positive_change(change)
            if amount is not None:
                change_amounts.append(amount)
            if percentage is not None:
                change_percentages.append(percentage)

    price_change_amount = max(change_amounts) if change_amounts else None
    price_change_percentage = max(change_percentages) if change_percentages else None
    if price_change_amount is not None or price_change_percentage is not None:
        score = 10.0 * _amount_factor(price_change_amount)
        score += 5.0 * min(1.0, (price_change_percentage or 0.0) / PRICE_CHANGE_REFERENCE_PERCENTAGE)
        contributing_factors.append({"factor": "verified_price_increase", "score": round(score, 2), "amount": price_change_amount, "percentage": price_change_percentage})
        reasons.append(f"Verified positive price-change data contributed {score:.2f} points.")
        total_score += score

    risk_score = round(max(0.0, min(MAX_FINANCIAL_RISK, total_score)), 2)
    reasons.append("Missing financial values and UNKNOWN exposure were not treated as zero; they received no measurable points.")
    return {
        "risk_score": risk_score,
        "contributing_factors": contributing_factors,
        "reasons": reasons,
    }