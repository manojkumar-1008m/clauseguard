"""backend/services/consequence_engine.py
Consumer consequence generation engine for ClauseGuard Phase 7.1.

Translates detected potential dark pattern categories and supporting evidence
into objective, non-legal consumer risk explanations.
"""
from __future__ import annotations

import re
from typing import Optional

BASE_CONSEQUENCES = {
    "Subscription Trap": (
        "The subscription may renew automatically and result in recurring charges "
        "unless cancelled before the renewal date."
    ),
    "Drip Pricing": (
        "The final amount may be higher than the initially displayed price "
        "because an additional fee is disclosed later in the checkout process."
    ),
    "Obstruction": (
        "Cancellation may require extra steps or contacting customer support "
        "instead of being available directly from account settings."
    ),
    "Sneaking": (
        "An additional product or service may be included automatically "
        "unless the user manually removes or disables it."
    ),
    "Scarcity": (
        "The wording may create psychological pressure to purchase quickly "
        "based on limited-availability messaging."
    ),
    "Urgency": (
        "The wording may pressure the user to make a decision quickly "
        "before an approaching or arbitrary deadline."
    ),
    "Confirm Shaming": (
        "The decline option uses emotionally negative language that may pressure "
        "the user to accept an unwanted offer."
    ),
    "Social Proof": (
        "The message may use claimed popularity or other-user activity "
        "to influence the purchasing decision."
    ),
    "Misdirection": (
        "The wording may make one option easier to choose or make an alternative "
        "choice less clear or less accessible."
    ),
    "Forced Action": (
        "The user may be required to provide information or perform an action "
        "before being permitted to proceed."
    ),
    "Other": (
        "The text contains phrasing that may potentially nudge or pressure user choices."
    )
}

def generate_consequence(pattern_category: Optional[str], evidence: Optional[str] = None) -> Optional[str]:
    """Generate a potential consumer consequence from category and extracted evidence."""
    if not pattern_category or pattern_category == "None":
        return None

    base_text = BASE_CONSEQUENCES.get(pattern_category, BASE_CONSEQUENCES["Other"])

    # Interpolate specific price/cadence if found in evidence for Subscription Trap
    if pattern_category == "Subscription Trap" and evidence:
        price_match = re.search(r"([₹$€£]\s*\d+(?:[\.,]\d+)?)", evidence)
        cadence_match = re.search(r"/(?:month|year|week)", evidence, re.IGNORECASE)
        if price_match and cadence_match:
            return f"The subscription may renew automatically and result in a recurring {price_match.group(1)} charge."
        elif price_match:
            return f"The subscription may renew automatically and result in a recurring {price_match.group(1)} charge."

    return base_text
