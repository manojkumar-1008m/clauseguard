"""backend/services/pattern_mapper.py
Transparent, deterministic pattern mapping layer for ClauseGuard Phase 7.1.

Maps interface text into standardized dark pattern taxonomy categories
using multi-signal rule combinations and contextual contradiction guards.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from . import evidence_extractor

# Contradiction / Benign guards: Contexts where isolated keywords are used benignly
BENIGN_CONTRADICTION_PATTERNS = [
    # Upfront pricing transparency
    re.compile(r"(?:(?:fee|charges?|price)\s+(?:is|are)?\s*(?:shown|displayed|itemized|calculated)\s+(?:clearly\s+)?(?:before|prior\s+to)\s+payment)", re.IGNORECASE),
    re.compile(r"(?:total\s+price\s+including\s+all\s+(?:mandatory\s+)?fees\s+is\s+shown)", re.IGNORECASE),
    re.compile(r"(?:all\s+mandatory\s+charges\s+and\s+payment\s+processing\s+fees\s+have\s+been\s+calculated)", re.IGNORECASE),
    re.compile(r"(?:complete\s+price\s+including\s+all\s+mandatory\s+fees\s+is\s+shown)", re.IGNORECASE),
    # Self-serve cancellation transparency
    re.compile(r"(?:cancel\s+(?:your\s+)?subscription\s+(?:at\s+any\s+time\s+)?from\s+account\s+settings)", re.IGNORECASE),
    re.compile(r"(?:cancel\s+anytime\s+(?:from\s+account\s+settings|from\s+dashboard|online))", re.IGNORECASE),
    re.compile(r"(?:toggle\s+auto-renew\s+off\s+in\s+billing\s+preferences)", re.IGNORECASE),
    # Transparent subscription / billing options
    re.compile(r"(?:subscription\s+plan\s+is\s+available\s+for\s+monthly\s+or\s+annual\s+billing)", re.IGNORECASE),
    re.compile(r"(?:trial\s+end\s+date\s+is\s+clearly\s+displayed)", re.IGNORECASE),
    re.compile(r"(?:notify\s+you\s+via\s+email\s+\d+\s+days\s+before\s+[^\.,;]*renews)", re.IGNORECASE),
    # Factual variants / inventory
    re.compile(r"(?:(?:only\s+)?(?:\d+|three|two|four)\s+(?:colors|sizes|variants|models)\s+are\s+currently\s+available)", re.IGNORECASE),
    re.compile(r"(?:displays\s+current\s+inventory\s+levels)", re.IGNORECASE),
    # Symmetric cookie choice
    re.compile(r"(?:customize\s+your\s+cookie\s+preferences\s+or\s+decline)", re.IGNORECASE),
]

# Pattern rules: Multi-signal combinations
PATTERN_RULES = [
    (
        "Subscription Trap",
        [
            re.compile(r"(?:free\s+trial[^\.,;]*automatically\s+renews)", re.IGNORECASE),
            re.compile(r"(?:automatically\s+renews\s+at\s+[₹$€£]?\d+)", re.IGNORECASE),
            re.compile(r"(?:renews\s+automatically\s+(?:at|every))", re.IGNORECASE),
            re.compile(r"(?:trial\s+converts\s+into\s+(?:a\s+)?subscription)", re.IGNORECASE),
            re.compile(r"(?:charged\s+every\s+month\s+after\s+trial)", re.IGNORECASE),
            re.compile(r"(?:auto-renew(?:s|al)?\s+at\s+(?:triple|quadruple|[₹$€£]?\d+))", re.IGNORECASE),
            re.compile(r"(?:recurring\s+(?:billing|charge)\s+without\s+email\s+notice)", re.IGNORECASE),
        ]
    ),
    (
        "Drip Pricing",
        [
            re.compile(r"(?:fee\s+(?:is|will\s+be)\s+revealed\s+after\s+payment)", re.IGNORECASE),
            re.compile(r"(?:fee\s+(?:is|will\s+be)\s+revealed\s+after\s+(?:you\s+enter\s+)?(?:your\s+)?payment\s+details)", re.IGNORECASE),
            re.compile(r"(?:mandatory\s+[^\.,;]*fee\s+(?:will\s+be\s+revealed|added\s+at\s+final|added\s+on\s+final))", re.IGNORECASE),
            re.compile(r"(?:resort\s+fee[^\.,;]*added\s+on\s+final\s+payment)", re.IGNORECASE),
            re.compile(r"(?:additional\s+fee\s+at\s+checkout)", re.IGNORECASE),
            re.compile(r"(?:processing\s+fee\s+added\s+later)", re.IGNORECASE),
            re.compile(r"(?:taxes/fees\s+hidden\s+until\s+later)", re.IGNORECASE),
        ]
    ),
    (
        "Obstruction",
        [
            re.compile(r"(?:to\s+cancel[^\.\?!;]*contact\s+(?:customer\s+)?support\s+by\s+phone)", re.IGNORECASE),
            re.compile(r"(?:to\s+cancel[^\.\?!;]*contact\s+(?:customer\s+)?support)", re.IGNORECASE),
            re.compile(r"(?:contact\s+customer\s+support\s+to\s+cancel)", re.IGNORECASE),
            re.compile(r"(?:cancel(?:ing|lation)?\s+(?:\w+\s+)*requires\s+contacting\s+customer\s+support)", re.IGNORECASE),
            re.compile(r"(?:cancellation\s+requires\s+(?:calling|contacting|phone))", re.IGNORECASE),
            re.compile(r"(?:canceling\s+requires\s+calling)", re.IGNORECASE),
            re.compile(r"(?:cancellation\s+unavailable\s+in\s+account\s+settings)", re.IGNORECASE),
            re.compile(r"(?:must\s+contact\s+representative\s+to\s+cancel)", re.IGNORECASE),
            re.compile(r"(?:cancellation\s+cannot\s+be\s+completed\s+online)", re.IGNORECASE),
            re.compile(r"(?:multiple\s+steps\s+required\s+to\s+cancel)", re.IGNORECASE),
        ]
    ),
    (
        "Sneaking",
        [
            re.compile(r"(?:(?:extended\s+warranty|product|item)\s+has\s+already\s+been\s+selected)", re.IGNORECASE),
            re.compile(r"(?:already\s+selected\s+for\s+your\s+order)", re.IGNORECASE),
            re.compile(r"(?:automatically\s+added\s+(?:to\s+cart|for\s+you|item|product))", re.IGNORECASE),
            re.compile(r"(?:preselected\s+(?:add-on|warranty|item))", re.IGNORECASE),
            re.compile(r"(?:extra\s+protection\s+included(?:\s+by\s+default)?)", re.IGNORECASE),
            re.compile(r"(?:checkbox\s+already\s+selected)", re.IGNORECASE),
            re.compile(r"(?:automatically\s+added\s+to\s+total\s+unless\s+unchecked)", re.IGNORECASE),
        ]
    ),
    (
        "Scarcity",
        [
			re.compile(r"(?:only\s+\d+\s+items?\s+left\s+in\s+stock)", re.IGNORECASE),
            re.compile(r"(?:only\s+(?:\d+|three|two|four|a\s+few)\s+left[^\.,;]*order\s+soon)", re.IGNORECASE),
            re.compile(r"(?:only\s+(?:\d+|three|two|four|a\s+few)\s+left\s*[—–-]\s*buy\s+now)", re.IGNORECASE),
            re.compile(r"(?:only\s+(?:\d+|three|two|four|a\s+few)\s+left\b(?!\s+(?:colors|sizes|variants)))", re.IGNORECASE),
            re.compile(r"(?:hurry!\s*only\s+\d+\s+left)", re.IGNORECASE),
            re.compile(r"(?:limited\s+stock(?:\s*!\s*\d+)?)", re.IGNORECASE),
            re.compile(r"(?:almost\s+sold\s+out)", re.IGNORECASE),
            re.compile(r"(?:low\s+stock\s+alert)", re.IGNORECASE),
            re.compile(r"(?:few\s+remaining)", re.IGNORECASE),
        ]
    ),
    (
        "Urgency",
        [
            re.compile(r"(?:(?:this\s+)?offer\s+expires\s+tonight)", re.IGNORECASE),
            re.compile(r"(?:expires\s+(?:soon|tonight|in\s+\d+\s*(?:minutes|hours)))", re.IGNORECASE),
            re.compile(r"(?:limited\s+time\s*(?:only|offer)?)", re.IGNORECASE),
            re.compile(r"(?:act\s+now(?:\s+before\s+[^\.,;]+)?)", re.IGNORECASE),
            re.compile(r"(?:ends\s+tonight)", re.IGNORECASE),
            re.compile(r"(?:countdown|only\s+\d+\s+minutes\s+left)", re.IGNORECASE),
            re.compile(r"(?:flash\s+sale\s*\|\s*limited\s+time)", re.IGNORECASE),
        ]
    ),
    (
        "Confirm Shaming",
        [
			re.compile(r"(?:no,?\s+i\s+don'?t\s+want\s+to\s+save\s+money)", re.IGNORECASE),
            re.compile(r"(?:no\s+thanks,?\s*i\s+don'?t\s+want\s+to\s+protect\s+my\s+purchase)", re.IGNORECASE),
            re.compile(r"(?:no\s+thanks,?\s*i\s+prefer\s+to\s+pay\s+full\s+price)", re.IGNORECASE),
            re.compile(r"(?:no\s+thanks,?\s*i\s+don'?t\s+care)", re.IGNORECASE),
            re.compile(r"(?:continue\s+without\s+protection)", re.IGNORECASE),
            re.compile(r"(?:decline\s+(?:the\s+)?benefits)", re.IGNORECASE),
            re.compile(r"(?:no,?\s*i\s+hate\s+saving\s+money)", re.IGNORECASE),
            re.compile(r"(?:no,?\s*i\s+want\s+my\s+product\s+unprotected)", re.IGNORECASE),
        ]
    ),
    (
        "Social Proof",
        [
            re.compile(r"(?:(?:thousands|\d+)\s+people\s+are\s+viewing\s+this)", re.IGNORECASE),
            re.compile(r"(?:(?:thousands|\d+)\s+(?:people\s+)?purchased\s+[^\.,;]*)", re.IGNORECASE),
            re.compile(r"(?:someone\s+in\s+[^\.,;]+\s+just\s+bought)", re.IGNORECASE),
            re.compile(r"(?:people\s+have\s+added\s+to\s+cart)", re.IGNORECASE),
            re.compile(r"(?:popular\s+choice|trending\s+now)", re.IGNORECASE),
        ]
    ),
    (
        "Forced Action",
        [
            re.compile(r"(?:must\s+create\s+(?:an\s+)?account\s+before\s+continuing)", re.IGNORECASE),
            re.compile(r"(?:required\s+before\s+continuing)", re.IGNORECASE),
            re.compile(r"(?:cannot\s+continue\s+without)", re.IGNORECASE),
            re.compile(r"(?:mandatory\s+registration)", re.IGNORECASE),
            re.compile(r"(?:must\s+provide\s+information\s+before\s+proceeding)", re.IGNORECASE),
        ]
    ),
    (
        "Misdirection",
        [
            re.compile(r"(?:no\s+thanks\.?\s*i\s+don'?t\s+like\s+free\s+things)", re.IGNORECASE),
            re.compile(r"(?:our\s+best\s+selling\s+[^\.,;]*)", re.IGNORECASE),
        ]
    )
]

def check_contradiction_guards(text: str) -> bool:
    """Return True if the text matches a benign contextual contradiction guard."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    for guard_pat in BENIGN_CONTRADICTION_PATTERNS:
        if guard_pat.search(cleaned):
            return True
    return False

def map_pattern(
    text: str,
    model_pred: int,
    confidence: Optional[float] = None,
    requires_context: bool = False
) -> Tuple[Optional[str], Optional[str], bool]:
    """Map text to a dark pattern category and extract evidence span.

    Returns:
        (pattern_category, evidence_span, is_benign_override)
    """
    if not text or not text.strip():
        return None, None, False

    # 1. Check if surrounding context contradicts dark pattern intent
    if check_contradiction_guards(text):
        return None, None, True

    # 2. Check if rule matches any category
    detected_cat = None
    for cat_name, patterns in PATTERN_RULES:
        for pat in patterns:
            if pat.search(text):
                detected_cat = cat_name
                break
        if detected_cat:
            break

    # If an explicit high-confidence rule matched, confirm potential dark pattern
    if detected_cat:
        evidence = evidence_extractor.extract_evidence_span(text, detected_cat)
        return detected_cat, evidence, False

    # 3. If model predicted positive, but no specific category matched
    if model_pred == 1 and not requires_context and (confidence is None or confidence >= 0.65):
        evidence = evidence_extractor.extract_evidence_span(text, "Other")
        return "Other", evidence, False

    # Otherwise benign / context required
    return None, None, False


# Terms & Conditions specific pattern rules
TERMS_RULES = [
    (
        "Unilateral Terms Modification",
        [
            re.compile(r"(?:(?:modify|change|update)\s+these\s+terms\s+(?:at\s+any\s+time\s+)?without\s+(?:prior\s+)?notice)", re.IGNORECASE),
            re.compile(r"(?:right\s+to\s+modify|sole\s+discretion\s+to\s+(?:change|modify))\s+these\s+terms", re.IGNORECASE),
            re.compile(r"(?:continued\s+use\s+(?:of\s+[^\.,;]+\s+)?constitutes\s+acceptance\s+of\s+(?:any\s+)?modified\s+terms)", re.IGNORECASE),
        ]
    ),
    (
        "Arbitration & Class Action Waiver",
        [
            re.compile(r"(?:binding\s+(?:individual\s+)?arbitration|waive\s+any\s+right\s+to\s+(?:a\s+)?jury\s+trial)", re.IGNORECASE),
            re.compile(r"(?:class\s+action\s+waiver|waive\s+(?:the\s+)?right\s+to\s+participate\s+in\s+a\s+class\s+action)", re.IGNORECASE),
            re.compile(r"(?:disputes?\s+must\s+be\s+resolved\s+on\s+an\s+individual\s+basis)", re.IGNORECASE),
        ]
    ),
    (
        "Auto-Renewal Terms Clause",
        [
            re.compile(r"(?:subscription\s+will\s+automatically\s+renew\s+unless\s+cancelled)", re.IGNORECASE),
            re.compile(r"(?:recurring\s+subscription\s+fee\s+will\s+be\s+(?:automatically\s+)?billed)", re.IGNORECASE),
            re.compile(r"(?:billed\s+on\s+a\s+recurring\s+basis\s+until\s+you\s+cancel)", re.IGNORECASE),
        ]
    ),
    (
        "Cancellation Penalty or Non-Refundable Fee",
        [
            re.compile(r"(?:early\s+termination\s+fee|cancellation\s+penalty)", re.IGNORECASE),
            re.compile(r"(?:fees?\s+(?:are|is)\s+strictly\s+non-refundable)", re.IGNORECASE),
            re.compile(r"(?:no\s+refunds?\s+(?:or\s+credits?\s+)?for\s+partial\s+(?:months?|billing\s+periods?))", re.IGNORECASE),
        ]
    ),
]

# Privacy specific pattern rules
PRIVACY_RULES = [
    (
        "Third-Party Data Sharing",
        [
            re.compile(r"(?:share\s+(?:your\s+)?(?:personal\s+)?(?:data|information)\s+with\s+third\s+parties)", re.IGNORECASE),
            re.compile(r"(?:share\s+(?:your\s+)?data\s+with\s+(?:advertising|marketing)\s+partners)", re.IGNORECASE),
            re.compile(r"(?:disclose\s+(?:your\s+)?information\s+to\s+(?:affiliates|partners|sponsors))", re.IGNORECASE),
            re.compile(r"(?:third-party\s+partners\s+may\s+collect\s+information)", re.IGNORECASE),
        ]
    ),
    (
        "Personal Data Sale Disclosure",
        [
            re.compile(r"(?:sell\s+(?:or\s+share\s+)?your\s+personal\s+information)", re.IGNORECASE),
            re.compile(r"(?:sale\s+of\s+personal\s+data)", re.IGNORECASE),
            re.compile(r"(?:disclose\s+personal\s+information\s+for\s+commercial\s+purposes)", re.IGNORECASE),
        ]
    ),
    (
        "Extensive Tracking Disclosure",
        [
            re.compile(r"(?:track\s+your\s+activity\s+across\s+(?:other\s+)?(?:websites|apps|services))", re.IGNORECASE),
            re.compile(r"(?:collect\s+precise\s+geolocation\s+(?:data|information))", re.IGNORECASE),
            re.compile(r"(?:cross-device\s+tracking)", re.IGNORECASE),
        ]
    ),
]


def map_all_patterns(text: str) -> List[Dict[str, Any]]:
    """Deterministically scan text and extract ALL matching pattern findings across categories.

    Returns a list of finding dictionaries:
    [
        {
            "category": "Subscription Trap",
            "pattern": "subscription_trap",
            "type": "subscription_trap",
            "evidence": "... matched excerpt ...",
            "strength": "strong" | "moderate",
            "source": "text" | "terms" | "privacy",
            "severity": "high" | "medium" | "low",
        },
        ...
    ]
    """
    if not text or not text.strip():
        return []

    findings: List[Dict[str, Any]] = []
    seen_categories: set = set()

    # 1. Dark pattern interface rules (source="text")
    for cat_name, patterns in PATTERN_RULES:
        if cat_name in seen_categories:
            continue
        for pat in patterns:
            match = pat.search(text)
            if match:
                snippet = text[max(0, match.start() - 20):min(len(text), match.end() + 20)].strip()
                # Check benign contradiction guards against the local excerpt
                if check_contradiction_guards(snippet):
                    continue

                evidence = evidence_extractor.extract_evidence_span(text, cat_name) or match.group(0)
                pat_key = cat_name.lower().replace(" ", "_")
                severity = "high" if cat_name in ("Subscription Trap", "Drip Pricing", "Obstruction") else "medium"
                findings.append({
                    "category": cat_name,
                    "pattern": pat_key,
                    "type": pat_key,
                    "evidence": evidence,
                    "strength": "strong" if severity == "high" else "moderate",
                    "source": "text",
                    "severity": severity,
                })
                seen_categories.add(cat_name)
                break

    # 2. Terms rules (source="terms")
    for cat_name, patterns in TERMS_RULES:
        if cat_name in seen_categories:
            continue
        for pat in patterns:
            match = pat.search(text)
            if match:
                evidence = match.group(0)
                pat_key = cat_name.lower().replace(" ", "_").replace("&", "and")
                findings.append({
                    "category": cat_name,
                    "pattern": pat_key,
                    "type": pat_key,
                    "evidence": evidence,
                    "strength": "moderate",
                    "source": "terms",
                    "severity": "medium",
                })
                seen_categories.add(cat_name)
                break

    # 3. Privacy rules (source="privacy")
    for cat_name, patterns in PRIVACY_RULES:
        if cat_name in seen_categories:
            continue
        for pat in patterns:
            match = pat.search(text)
            if match:
                evidence = match.group(0)
                pat_key = cat_name.lower().replace(" ", "_")
                findings.append({
                    "category": cat_name,
                    "pattern": pat_key,
                    "type": pat_key,
                    "evidence": evidence,
                    "strength": "moderate",
                    "source": "privacy",
                    "severity": "medium",
                })
                seen_categories.add(cat_name)
                break

    return findings
