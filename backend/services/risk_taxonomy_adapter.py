"""Compatibility adapter for supported Vision/evidence pattern labels."""
from __future__ import annotations

from typing import Any, Dict, Optional


CANONICAL_INTELLIGENCE_PATTERNS = frozenset(
    {
        "SUBSCRIPTION_TRAP",
        "DRIP_PRICING",
        "BASKET_SNAKING",
        "FALSE_URGENCY",
        "SCARCITY",
        "FORCED_ACTION",
        "CONFIRM_SHAMING",
        "OBSTRUCTION",
        "MISDIRECTION",
        "SOCIAL_PROOF",
    }
)

CONFIRMED_VISION_TO_CANONICAL: Dict[str, str] = {
    "countdown_timer": "FALSE_URGENCY",
    "limited_time_message": "FALSE_URGENCY",
    "low_stock_message": "SCARCITY",
    "post_action_fee_added": "DRIP_PRICING",
    "fake_countdown_structure": "FALSE_URGENCY",
}


def adapt_pattern(pattern: Any) -> Dict[str, Optional[str]]:
    """Translate one supported source label without inventing a mapping."""
    source_pattern = str(pattern).strip() if pattern is not None else ""
    normalized = source_pattern.lower()
    canonical_pattern = CONFIRMED_VISION_TO_CANONICAL.get(normalized)
    if canonical_pattern:
        return {
            "source_pattern": source_pattern,
            "canonical_pattern": canonical_pattern,
            "status": "SUPPORTED",
            "reason": "Explicit Vision/evidence-to-Intelligence mapping is supported by repository logic.",
        }

    canonical_candidate = source_pattern.upper()
    if canonical_candidate in CANONICAL_INTELLIGENCE_PATTERNS:
        return {
            "source_pattern": source_pattern,
            "canonical_pattern": canonical_candidate,
            "status": "SUPPORTED",
            "reason": "Pattern is already a canonical Intelligence category.",
        }

    return {
        "source_pattern": source_pattern,
        "canonical_pattern": None,
        "status": "UNSUPPORTED",
        "reason": "No explicit repository-supported taxonomy mapping exists for this pattern.",
    }