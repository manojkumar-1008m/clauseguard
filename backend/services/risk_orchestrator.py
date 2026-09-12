"""Orchestration layer for the independent Risk Engine components."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional

from ..schemas.evidence import (
    ConsumerConsequenceDetail,
    FinancialImpact,
    HistoricalChangeDetail,
    PatternAssessment,
)
from ..schemas.price import PriceAnalysisResponse
from ..schemas.regulatory import RegulatoryCheckResponse
from .dark_pattern_risk import calculate_dark_pattern_risk
from .financial_risk import calculate_financial_risk
from .historical_risk import calculate_historical_risk
from .overall_risk import calculate_overall_risk
from .regulatory_risk import calculate_regulatory_risk
from .transparency_risk import calculate_transparency_risk


def _value(source: Any, field: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(field, default)
    return getattr(source, field, default)


def _numeric(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _select_primary_consequence(
    consequences: Optional[Sequence[ConsumerConsequenceDetail]],
) -> Optional[ConsumerConsequenceDetail]:
    """Select one consequence deterministically for singular risk calculators.

    Priority is: highest numeric financial exposure; otherwise highest future
    or renewal cost; otherwise highest consumer effort/friction; otherwise the
    first consequence. This is an orchestration policy only and does not alter
    the existing Financial or Transparency Risk scoring logic.
    """
    items = list(consequences or [])
    if not items:
        return None

    with_exposure = [
        (index, consequence, _numeric(_value(consequence, "financial_exposure")))
        for index, consequence in enumerate(items)
    ]
    numeric_exposure = [item for item in with_exposure if item[2] is not None]
    if numeric_exposure:
        return max(numeric_exposure, key=lambda item: (item[2], -item[0]))[1]

    with_future_cost = []
    for index, consequence in enumerate(items):
        future_cost = _numeric(_value(consequence, "future_cost"))
        renewal_cost = _numeric(_value(consequence, "renewal_cost"))
        cost = max(
            (value for value in (future_cost, renewal_cost) if value is not None),
            default=None,
        )
        with_future_cost.append((index, consequence, cost))
    numeric_future_cost = [item for item in with_future_cost if item[2] is not None]
    if numeric_future_cost:
        return max(numeric_future_cost, key=lambda item: (item[2], -item[0]))[1]

    effort_rank = {
        "minimal": 0,
        "low": 1,
        "moderate": 2,
        "high_friction": 3,
    }
    with_effort = [
        (
            index,
            consequence,
            effort_rank.get(str(_value(consequence, "consumer_effort", "")).lower(), -1),
        )
        for index, consequence in enumerate(items)
    ]
    known_effort = [item for item in with_effort if item[2] >= 0]
    if known_effort:
        return max(known_effort, key=lambda item: (item[2], -item[0]))[1]

    return items[0]


def calculate_complete_risk(
    pattern_assessments: Optional[List[PatternAssessment]] = None,
    financial_impact: Optional[FinancialImpact] = None,
    consumer_consequences: Optional[List[ConsumerConsequenceDetail]] = None,
    price_analysis: Optional[PriceAnalysisResponse] = None,
    regulatory_response: Optional[RegulatoryCheckResponse] = None,
    historical_changes: Optional[List[HistoricalChangeDetail]] = None,
) -> Dict[str, Any]:
    """Run the five independent calculators and aggregate their results."""
    selected_consequence = _select_primary_consequence(consumer_consequences)

    dark_pattern_risk = calculate_dark_pattern_risk(pattern_assessments or [])
    financial_risk = calculate_financial_risk(
        financial_impact=financial_impact,
        consumer_consequence=selected_consequence,
        historical_changes=historical_changes or [],
        price_analysis=price_analysis,
    )
    transparency_risk = calculate_transparency_risk(selected_consequence)

    if regulatory_response is None:
        regulatory_risk = {
            "risk_score": None,
            "contributing_factors": [],
            "reasons": [
                "Regulatory data was unavailable; no regulatory risk contribution was inferred."
            ],
        }
    else:
        regulatory_risk = calculate_regulatory_risk(regulatory_response)

    historical_risk = calculate_historical_risk(historical_changes or [])
    overall_risk = calculate_overall_risk(
        dark_pattern_risk=dark_pattern_risk,
        financial_risk=financial_risk,
        transparency_risk=transparency_risk,
        regulatory_risk=regulatory_risk,
        historical_risk=historical_risk,
    )

    return {
        "dark_pattern_risk": dark_pattern_risk,
        "financial_risk": financial_risk,
        "transparency_risk": transparency_risk,
        "regulatory_risk": regulatory_risk,
        "historical_risk": historical_risk,
        "overall_risk": overall_risk,
    }