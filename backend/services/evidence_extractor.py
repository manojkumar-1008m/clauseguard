"""backend/services/evidence_extractor.py
Deterministic evidence extraction service for ClauseGuard Phase 7.1.

Extracts the smallest meaningful textual span from user-facing interface text
that provides evidence for a detected potential dark pattern.
"""
from __future__ import annotations

import re
from typing import Optional

# Targeted extraction patterns per taxonomy category
EVIDENCE_PATTERNS = {
    "Subscription Trap": [
        re.compile(r"(?:automatically renews?(?:\s+at\s+[₹$€£]?\d+(?:[\.,]\d+)?)?(?:\s*/\s*(?:month|year|week|day))?)", re.IGNORECASE),
        re.compile(r"(?:renews?(?:\s+automatically)?(?:\s+at\s+[₹$€£]?\d+(?:[\.,]\d+)?)?(?:\s*/\s*(?:month|year|week|day))?)", re.IGNORECASE),
        re.compile(r"(?:recurring\s+(?:charge|billing)(?:\s+of\s+[₹$€£]?\d+)?)", re.IGNORECASE),
        re.compile(r"(?:charged\s+every\s+(?:month|year|week))", re.IGNORECASE),
        re.compile(r"(?:auto-renew(?:al)?(?:\s+at\s+[₹$€£]?\d+)?)", re.IGNORECASE),
        re.compile(r"(?:trial\s+(?:converts|renews|auto-renews))", re.IGNORECASE),
    ],
    "Drip Pricing": [
        re.compile(r"(?:(?:processing|service|convenience|mandatory|resort)\s+fee\s+(?:is|will be)\s+revealed(?:\s+after\s+[^\.,;]+)?)", re.IGNORECASE),
        re.compile(r"(?:fee\s+(?:is|will be)\s+revealed\s+after\s+[^\.,;]+)", re.IGNORECASE),
        re.compile(r"(?:fee\s+added\s+(?:at\s+checkout|on\s+final\s+payment[^\.,;]*))", re.IGNORECASE),
        re.compile(r"(?:mandatory\s+[^\.,;]*fee\s+added[^\.,;]*)", re.IGNORECASE),
        re.compile(r"(?:additional\s+fee\s+at\s+checkout)", re.IGNORECASE),
    ],
    "Obstruction": [
        re.compile(r"(?:(?:to\s+cancel[^\.\?!;]*|cancellation\s+requires[^\.\?!;]*|canceling\s+requires[^\.\?!;]*)contact(?:ing)?\s+customer\s+support(?:\s+by\s+phone)?)", re.IGNORECASE),
        re.compile(r"(?:contact(?:\s+customer)?\s+support\s+to\s+cancel)", re.IGNORECASE),
        re.compile(r"(?:cancellation\s+requires\s+(?:calling|contacting|phone)[^\.\?!;]*)", re.IGNORECASE),
        re.compile(r"(?:cancel(?:ing)?\s+requires\s+contacting\s+customer\s+support[^\.\?!;]*)", re.IGNORECASE),
        re.compile(r"(?:must\s+call\s+[^\.\?!;]*\s+to\s+cancel)", re.IGNORECASE),
        re.compile(r"(?:cancellation\s+unavailable\s+in\s+account\s+settings)", re.IGNORECASE),
    ],
    "Sneaking": [
        re.compile(r"(?:(?:extended\s+warranty|item|protection|product)\s+has\s+already\s+been\s+selected[^\.,;]*)", re.IGNORECASE),
        re.compile(r"(?:already\s+been\s+selected\s+for\s+your\s+order)", re.IGNORECASE),
        re.compile(r"(?:automatically\s+added\s+(?:to\s+your\s+cart|for\s+you)[^\.,;]*)", re.IGNORECASE),
        re.compile(r"(?:preselected\s+(?:add-on|warranty|item))", re.IGNORECASE),
        re.compile(r"(?:extra\s+protection\s+included(?:\s+by\s+default)?)", re.IGNORECASE),
        re.compile(r"(?:checkbox\s+already\s+selected)", re.IGNORECASE),
    ],
    "Scarcity": [
        re.compile(r"(?:only\s+(?:\d+|three|two|four|a\s+few)\s+left(?:[^\.,;]*in\s+stock)?)", re.IGNORECASE),
        re.compile(r"(?:limited\s+stock(?:\s*!\s*\d+[^\.,;]*)?)", re.IGNORECASE),
        re.compile(r"(?:almost\s+sold\s+out)", re.IGNORECASE),
        re.compile(r"(?:low\s+stock\s+alert[^\.,;]*)", re.IGNORECASE),
        re.compile(r"(?:few\s+remaining)", re.IGNORECASE),
    ],
    "Urgency": [
        re.compile(r"(?:(?:this\s+)?offer\s+expires\s+tonight)", re.IGNORECASE),
        re.compile(r"(?:expires\s+(?:soon|tonight|in\s+\d+\s*(?:minutes|hours)))", re.IGNORECASE),
        re.compile(r"(?:limited\s+time\s*(?:only|offer)?)", re.IGNORECASE),
        re.compile(r"(?:act\s+now(?:\s+before\s+[^\.,;]+)?)", re.IGNORECASE),
        re.compile(r"(?:ends\s+tonight)", re.IGNORECASE),
        re.compile(r"(?:flash\s+sale[^\.,;]*)", re.IGNORECASE),
    ],
    "Confirm Shaming": [
        re.compile(r"(?:no\s+thanks,?\s*(?:i\s+don'?t\s+want\s+to\s+protect\s+my\s+purchase|i\s+don'?t\s+care|i\s+hate\s+saving)?)", re.IGNORECASE),
        re.compile(r"(?:i\s+prefer\s+to\s+(?:lose|pay\s+full\s+price)[^\.,;]*)", re.IGNORECASE),
        re.compile(r"(?:continue\s+without\s+protection)", re.IGNORECASE),
        re.compile(r"(?:decline\s+(?:offer|benefits|protection)[^\.,;]*)", re.IGNORECASE),
        re.compile(r"(?:no,?\s*i\s+want\s+my\s+product\s+unprotected)", re.IGNORECASE),
    ],
    "Social Proof": [
        re.compile(r"(?:(?:\d+|thousands)\s+people\s+are\s+viewing\s+this)", re.IGNORECASE),
        re.compile(r"(?:(?:\d+|thousands)\s+people\s+purchased[^\.,;]*)", re.IGNORECASE),
        re.compile(r"(?:someone\s+in\s+[^\.,;]+\s+just\s+bought[^\.,;]*)", re.IGNORECASE),
        re.compile(r"(?:popular\s+choice|trending\s+now)", re.IGNORECASE),
    ],
    "Forced Action": [
        re.compile(r"(?:must\s+create\s+(?:an\s+)?account\s+before\s+continuing)", re.IGNORECASE),
        re.compile(r"(?:required\s+before\s+continuing)", re.IGNORECASE),
        re.compile(r"(?:cannot\s+continue\s+without[^\.,;]*)", re.IGNORECASE),
        re.compile(r"(?:mandatory\s+registration[^\.,;]*)", re.IGNORECASE),
    ],
    "Misdirection": [
        re.compile(r"(?:no\s+thanks\.?\s*i\s+don'?t\s+like\s+free\s+things)", re.IGNORECASE),
        re.compile(r"(?:our\s+best\s+selling\s+[^\.,;]*)", re.IGNORECASE),
    ]
}

def extract_evidence_span(text: str, category: Optional[str]) -> Optional[str]:
    """Extract the smallest meaningful textual span supporting the detected pattern."""
    if not text or not category or category == "None":
        return None

    cleaned_text = re.sub(r"\s+", " ", text).strip()

    # 1. Look for targeted category-specific regex patterns
    patterns = EVIDENCE_PATTERNS.get(category, [])
    for pat in patterns:
        match = pat.search(cleaned_text)
        if match:
            span = match.group(0).strip()
            # Clean trailing punctuation
            span = re.sub(r"[\.,;:\-\s]+$", "", span)
            return span

    # 2. Fallback: split text into clauses/sentences and pick the most relevant clause
    clauses = re.split(r"[\.\?!;\n]+", cleaned_text)
    for clause in clauses:
        c_clean = clause.strip()
        if len(c_clean) > 5:
            # Check if any category pattern matches this clause
            for pat in patterns:
                if pat.search(c_clean):
                    return c_clean

    # 3. If no specific span found, return first sentence or up to 80 chars
    first_sentence = re.split(r"[\.\?!;\n]+", cleaned_text)[0].strip()
    return first_sentence if first_sentence else cleaned_text[:80]
