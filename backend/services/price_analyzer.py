"""backend/services/price_analyzer.py
Service-layer monetary entity extractor, cost-type classifier, and financial relationship analyzer
for ClauseGuard Price & Cost Analyzer (Phase 8.1, 8.2, 8.3).
Provides deterministic financial calculations, multi-currency safety, and explicit total preservation.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ..schemas.price import DisplayedPrice, PriceAnalysisResponse, PriceEntity

_logger = logging.getLogger("clauseguard_backend.price_analyzer")

# Normalized mapping from raw currency symbols/tokens to ISO 4217 standard codes
CURRENCY_NORM = {
    "₹": "INR",
    "rs": "INR",
    "rs.": "INR",
    "inr": "INR",
    "$": "USD",
    "us$": "USD",
    "us $": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
}

# Prefix currency regex: e.g. ₹999, Rs. 999, INR 999, $29.99, US$29.99, €19, £49.99
PREFIX_PATTERN = re.compile(
    r'(?P<prefix>'
    r'US\s*\$|'
    r'USD\b|'
    r'INR\b|'
    r'Rs\b\.?|'
    r'EUR\b|'
    r'GBP\b|'
    r'[₹$€£]'
    r')\s*'
    r'(?P<amount>\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)'
    r'(?!\d|[.,]\d|\s*%)',
    re.IGNORECASE,
)

# Suffix currency regex: e.g. 499 INR, 999 Rs., 29.99 USD, 19 EUR, 49.99 GBP
SUFFIX_PATTERN = re.compile(
    r'(?<![\d$₹€£])'
    r'(?P<amount>\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)'
    r'\s*'
    r'(?P<suffix>'
    r'US\s*\$|'
    r'USD\b|'
    r'INR\b|'
    r'Rs\b\.?|'
    r'EUR\b|'
    r'GBP\b|'
    r'[₹$€£]'
    r')'
    r'(?!\d|[.,]\d|\s*%)',
    re.IGNORECASE,
)

# Deterministic fee patterns (ordered from specific to general)
FEE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("processing_fee", re.compile(r'\b(?:processing\s+(?:fee|charge|cost)|processing)\b', re.IGNORECASE)),
    ("platform_fee", re.compile(r'\b(?:platform\s+(?:fee|charge|cost))\b', re.IGNORECASE)),
    ("service_fee", re.compile(r'\b(?:service\s+(?:fee|charge|cost))\b', re.IGNORECASE)),
    ("booking_fee", re.compile(r'\b(?:booking\s+(?:fee|charge|cost)|convenience\s*&\s*booking\s+fee)\b', re.IGNORECASE)),
    ("convenience_fee", re.compile(r'\b(?:convenience\s+(?:fee|charge|cost))\b', re.IGNORECASE)),
    ("shipping_fee", re.compile(r'\b(?:shipping\s+(?:fee|charge|cost)|shipping)\b', re.IGNORECASE)),
    ("delivery_fee", re.compile(r'\b(?:delivery\s+(?:fee|charge|cost)|delivery)\b', re.IGNORECASE)),
    ("handling_fee", re.compile(r'\b(?:handling\s+(?:fee|charge|cost))\b', re.IGNORECASE)),
    ("protection_fee", re.compile(r'\b(?:(?:extended\s+)?protection(?:\s+(?:fee|plan))?|add\s+protection(?:\s+for)?)\b', re.IGNORECASE)),
    ("tax", re.compile(r'\b(?:gst|sales\s+tax|tax(?:es)?|vat)\b', re.IGNORECASE)),
    ("add_on", re.compile(r'\b(?:add\s+warranty|warranty|extra\s+baggage|premium\s+support|add-on)\b', re.IGNORECASE)),
    ("other_fee", re.compile(r'\b(?:transaction\s+fee|installation\s+fee|additional\s+fee|other\s+fee|cancellation\s+fee|fees?)\b', re.IGNORECASE)),
]

FEE_TYPES = {
    "processing_fee", "platform_fee", "service_fee", "booking_fee",
    "convenience_fee", "shipping_fee", "delivery_fee", "handling_fee",
    "protection_fee", "tax", "add_on", "other_fee"
}

TOTAL_PATTERN = re.compile(r'\b(?:grand\s+total|total|amount\s+payable|you\s+pay|final\s+price|net\s+amount)\b', re.IGNORECASE)
DISCOUNT_BEFORE_PATTERN = re.compile(r'\b(?:save|discount(?:\s+of)?|savings(?:\s+of)?|cashback(?:\s+of)?)\b', re.IGNORECASE)
DISCOUNT_AFTER_PATTERN = re.compile(r'^\s*(?:off|discount|cashback)\b', re.IGNORECASE)

BASE_PRICE_PATTERN = re.compile(
    r'\b(?:ticket\s+costs?|costs?|product\s+costs?|service\s+costs?|flight\s+costs?|'
    r'price\s+is|price:|priced\s+at|product\s+price|item\s+price|regular\s+price|standard\s+price|'
    r'starting\s+(?:price|at)|starts?\s+at|start\s+from|listed\s+price|displayed\s+price|base\s+price|base\s+fare)\b|'
    r'[-—–:]\s*$',
    re.IGNORECASE
)

ORIGINAL_PRICE_PATTERN = re.compile(r'\b(?:was|original\s+price|originally|list\s+price|mrp)\b', re.IGNORECASE)
SALE_PRICE_PATTERN = re.compile(r'\b(?:now|sale\s+price|deal\s+price|offer\s+price|discounted\s+price|special\s+price)\b', re.IGNORECASE)

SUBSCRIPTION_PATTERN = re.compile(r'(?:/(?:month|mo|year|yr|annum)|per\s+(?:month|year|annum)|monthly|annually|yearly|subscription)\b', re.IGNORECASE)
RENEWAL_PATTERN = re.compile(r'\b(?:then|renews?(?:\s+at|\s+for)?|after\s+(?:trial|free\s+trial)|renewal(?:\s+price)?)\b', re.IGNORECASE)
TRIAL_PATTERN = re.compile(r'\b(?:free\s+trial|trial|try\s+for)\b', re.IGNORECASE)

# Phase 8.4: Normalized billing period patterns (day, week, month, year)
PERIOD_PATTERNS = [
    ("month", re.compile(r'(?:/(?:month|mo)\b|(?:\b(?:per|every|each)\s+months?\b)|\bmonthly\b)', re.IGNORECASE)),
    ("year", re.compile(r'(?:/(?:year|yr|annum)\b|(?:\b(?:per|every|each)\s+(?:years?|annum)\b)|\b(?:annually|annual|yearly)\b)', re.IGNORECASE)),
    ("week", re.compile(r'(?:/(?:week|wk)\b|(?:\b(?:per|every|each)\s+weeks?\b)|\bweekly\b)', re.IGNORECASE)),
    ("day", re.compile(r'(?:/(?:day)\b|(?:\b(?:per|every|each)\s+days?\b)|\bdaily\b)', re.IGNORECASE)),
]

NON_RECURRING_PATTERN = re.compile(
    r'\b(?:today|one-time(?:\s+payment|\s+fee)?|single\s+payment|setup\s+fee)\b',
    re.IGNORECASE
)

RECURRING_KEYWORDS = re.compile(
    r'\b(?:renews?(?:\s+at|\s+for)?|renewal|subscription|auto-renew(?:al)?|recurring|per\s+(?:month|year|week|day|mo|yr|annum))\b',
    re.IGNORECASE
)

# Explicit trial patterns and duration extraction
TRIAL_DURATION_PATTERNS = [
    re.compile(r'\b(?P<days>\d+)[- ]day\s+(?:free\s+)?trial\b', re.IGNORECASE),
    re.compile(r'\bfree\s+(?P<days>\d+)[- ]day\s+trial\b', re.IGNORECASE),
    re.compile(r'\bfree\s+trial\s+(?:for|of)\s+(?P<days>\d+)\s+days?\b', re.IGNORECASE),
    re.compile(r'\bfree\s+for\s+(?P<days>\d+)\s+days?\b', re.IGNORECASE),
    re.compile(r'\btrial(?:\s+period)?\s+(?:for|of)\s+(?P<days>\d+)\s+days?\b', re.IGNORECASE),
    re.compile(r'\b(?P<days>\d+)[- ]day\s+trial(?:\s+period)?\b', re.IGNORECASE),
]

FREE_TRIAL_PATTERN = re.compile(
    r'\b(?:free\s+trial|free\s+\d+[- ]day\s+trial|\d+[- ]day\s+free\s+trial|free\s+for\s+\d+\s+days?|free\s+trial\s+period)\b',
    re.IGNORECASE
)


# Multi-stage promotional duration patterns
PROMO_MONTHS_PATTERNS = [
    re.compile(r'\b(?:first|initial|introductory)\s+(\d+)\s+months?\b', re.IGNORECASE),
    re.compile(r'\b(?:first|initial|introductory)\s+month\b', re.IGNORECASE),
    re.compile(r'\bfor\s+(?:the\s+)?first\s+(\d+)\s+months?\b', re.IGNORECASE),
    re.compile(r'\bfor\s+(?:the\s+)?first\s+month\b', re.IGNORECASE),
    re.compile(r'\bfor\s+(\d+)\s+months?\b', re.IGNORECASE),
]

PROMO_DAYS_PATTERNS = [
    re.compile(r'\b(?:first|initial|introductory)\s+(\d+)\s+days?\b', re.IGNORECASE),
    re.compile(r'\bfor\s+(?:the\s+)?first\s+(\d+)\s+days?\b', re.IGNORECASE),
    re.compile(r'\bfor\s+(\d+)\s+days?\b', re.IGNORECASE),
]

SETUP_FEE_PATTERN = re.compile(r'\bsetup\s+fee\b', re.IGNORECASE)



def _normalize_currency(raw: str) -> str:
    """Normalize raw currency symbol or code to standard 3-letter currency code."""
    cleaned = re.sub(r'\s+', ' ', raw.strip().lower())
    return CURRENCY_NORM.get(cleaned, cleaned.upper())


def _normalize_amount(raw: str) -> float:
    """Convert amount string with potential comma separators to float."""
    cleaned = raw.replace(",", "").strip()
    return float(cleaned)


def _to_decimal(val: float | int) -> Decimal:
    """Convert float/int to Decimal safely via string representation."""
    return Decimal(str(val))


def _clean_float(dec: Decimal) -> float:
    """Clean Decimal to standard 2-decimal rounded float without floating-point artifacts."""
    return float(dec.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _extract_sentence_context(text: str, start: int, end: int, max_length: int = 300) -> str:
    """Extract the sentence or immediate context surrounding a match span without returning entire webpage."""
    left = start
    while left > 0:
        c = text[left - 1]
        if c in "\n\r":
            break
        if c in ".!?" and left < start:
            if left < len(text) and text[left].isspace():
                prev_text = text[:left - 1].rstrip()
                prev_word = prev_text.split()[-1] if prev_text else ""
                if prev_word.lower() not in ["rs", "mr", "mrs", "dr", "vs", "etc", "no", "vol"]:
                    break
        if start - left >= max_length // 2:
            while left < start and not text[left].isspace():
                left += 1
            break
        left -= 1

    right = end
    while right < len(text):
        c = text[right]
        if c in "\n\r":
            break
        if c in ".!?":
            if right + 1 == len(text) or text[right + 1].isspace():
                right += 1
                break
        if right - end >= max_length // 2:
            while right > end and not text[right].isspace():
                right -= 1
            break
        right += 1

    ctx = text[left:right].strip()
    return ctx if ctx else text[start:end]


def _find_split_point(between: str) -> int:
    """Find split point between two adjacent price entities."""
    p_idx = -1
    for p in [',', ';', '.']:
        idx = between.find(p)
        if idx != -1 and (p_idx == -1 or idx < p_idx):
            p_idx = idx
    if p_idx != -1:
        return p_idx

    conj_match = re.search(r'\b(?:or|and|plus)\b|\+', between, re.IGNORECASE)
    if conj_match:
        return conj_match.start()

    return len(between) // 2


def _is_additional_cost(cost_type: str) -> bool:
    """Check if a cost type classification represents an additional fee or cost."""
    return cost_type in FEE_TYPES or cost_type == "setup_fee"


def _compute_sentence_index(text: str, start: int) -> int:
    """Compute 0-based sentence index of match position in text."""
    prefix = text[:start]
    # Remove common abbreviations with periods to avoid false sentence counts
    cleaned = re.sub(r'\b(?:Rs|Mr|Mrs|Dr|vs|etc|no|vol)\.', '', prefix, flags=re.IGNORECASE)
    terminators = re.findall(r'(?<=\S)[.!?\n]+(?=\s|$)', cleaned)
    return len(terminators)


def _is_price_alternative(text: str, entities: List[PriceEntity]) -> bool:
    """Determine if entities represent mutually exclusive alternative options."""
    if any(e.relationship_type == "alternative" for e in entities):
        return True
    if len(entities) > 1:
        if re.search(r'\b(?:or|either)\b', text, re.IGNORECASE):
            return True
        if re.search(r'\b(?:choose\s+between|select\s+between|between)\b', text, re.IGNORECASE) and re.search(r'\band\b', text, re.IGNORECASE):
            return True
        if re.search(r'\b(?:standard|premium|basic|pro|starter|enterprise)\b', text, re.IGNORECASE) and re.search(r'\b(?:for|tier|plan|option)\b', text, re.IGNORECASE):
            return True
    return False


def _calculate_price_change(prev_price: float, curr_price: float) -> Tuple[float, float]:
    """Calculate deterministic price change amount and percentage using Decimal arithmetic."""
    prev_d = _to_decimal(prev_price)
    curr_d = _to_decimal(curr_price)
    diff_d = curr_d - prev_d
    p_change = _clean_float(diff_d)
    p_pct = _clean_float((diff_d / prev_d) * Decimal(100)) if prev_d > 0 else 0.0
    return p_change, p_pct


def _detect_price_change(
    text: str,
    raw_matches: List[Tuple[int, int, Optional[str], float, str]],
) -> Optional[Tuple[int, int]]:
    """Detect an explicit price change pair (i, i+1) in text."""
    n = len(raw_matches)
    if n < 2:
        return None

    for i in range(n - 1):
        start_i = raw_matches[i][0]
        end_i = raw_matches[i][1]
        start_next = raw_matches[i + 1][0]
        end_next = raw_matches[i + 1][1]
        between = text[end_i:start_next].strip().lower()
        before_i = text[max(0, start_i - 50):start_i].strip().lower()

        # Alternative pricing explicitly ruled out
        if re.search(r'\b(?:or|either)\b', between):
            continue

        # Trigger 1: from X to Y (e.g. "Price increased from ₹999 to ₹1299", "Price reduced from ₹999 to ₹799")
        is_from_to = bool(
            re.search(r'\b(?:from|rose\s+from|increased\s+from|reduced\s+from|decreased\s+from|changed\s+from|went\s+from|hiked\s+from|dropped\s+from)\b', before_i)
            and re.search(r'^\s*to\b|\bto\b', between)
        )

        # Trigger 2: previously X, now Y (e.g. "Previously ₹799, now ₹999.")
        is_prev_now = bool(
            re.search(r'\b(?:previously|formerly|earlier)\b', before_i)
            and re.search(r'\b(?:now|currently)\b', between)
        )

        # Trigger 3: was X ... now renews at Y (e.g. "Your subscription was ₹999/month and now renews at ₹1299/month.")
        is_was_now_renew = bool(
            re.search(r'\b(?:was|subscription\s+was)\b', before_i)
            and re.search(r'\b(?:and\s+)?now\s+(?:renews?(?:\s+at)?|is)\b|\bnow\s+renews?(?:\s+at)?\b', between)
        )

        # Trigger 4: explicit Previous price / Current price labels.
        is_labeled_change = bool(
            re.search(r'\bprevious\s+price\s*:', before_i)
            and re.search(r'\bcurrent\s+price\s*:', between)
        )

        if is_from_to or is_prev_now or is_was_now_renew or is_labeled_change:
            return (i, i + 1)

    return None


def _detect_late_disclosure(
    base_ent: Optional[PriceEntity],
    fee_ents: List[PriceEntity],
    has_unspecified_fee: bool,
    text: str = "",
) -> Tuple[Optional[bool], Optional[int], Optional[int]]:
    """Determine whether an additional cost was late-disclosed after the initial displayed price."""
    initial_price_pos: Optional[int] = None
    add_cost_pos: Optional[int] = None

    if base_ent and base_ent.character_start is not None:
        initial_price_pos = base_ent.character_start

    # Filter out inclusive fees (e.g. "including a ₹79 fee" or "inclusive of ₹79 fee")
    non_inclusive_fees = [
        e for e in fee_ents
        if e.relationship_type != "included_fee"
        and not (text and re.search(r'\b(?:including|includes|inclusive\s+of|inclusive)\b', text[max(0, (e.character_start or 0) - 35):e.character_start or 0], re.IGNORECASE))
    ]

    if non_inclusive_fees:
        earliest_fee = min(non_inclusive_fees, key=lambda e: e.character_start if e.character_start is not None else 999999)
        if earliest_fee.character_start is not None:
            add_cost_pos = earliest_fee.character_start

        if initial_price_pos is not None and add_cost_pos is not None:
            late_disclosed = (add_cost_pos > initial_price_pos)
            return late_disclosed, initial_price_pos, add_cost_pos
        return True, initial_price_pos, add_cost_pos

    if fee_ents and not non_inclusive_fees:
        # All fees were explicitly disclosed as inclusive alongside the price
        return False, initial_price_pos, None

    if has_unspecified_fee:
        return False, initial_price_pos, None

    return None, initial_price_pos, None


def _classify_and_link_entities(
    text: str,
    raw_matches: List[Tuple[int, int, Optional[str], float, str]],
) -> List[Tuple[str, Optional[str], Optional[int], Optional[str], bool]]:
    """Classify cost types, semantic relationships, billing periods, and recurring flags."""
    n = len(raw_matches)
    initial: List[Tuple[str, Optional[str], Optional[str], bool]] = []

    # Check promotional durations in text
    promo_months: Optional[int] = None
    for p in PROMO_MONTHS_PATTERNS:
        m_p = p.search(text)
        if m_p:
            promo_months = int(m_p.group(1)) if m_p.groups() and m_p.group(1) else 1
            break

    promo_days: Optional[int] = None
    for p in PROMO_DAYS_PATTERNS:
        m_p = p.search(text)
        if m_p:
            promo_days = int(m_p.group(1)) if m_p.groups() and m_p.group(1) else None
            break

    change_pair = _detect_price_change(text, raw_matches)

    for i, (start, end, _, _, orig_txt) in enumerate(raw_matches):
        if i > 0:
            prev_end = raw_matches[i - 1][1]
            between_prev = text[prev_end:start]
            split_p = _find_split_point(between_prev)
            left_boundary = prev_end + split_p
        else:
            left_boundary = max(0, start - 45)

        if i + 1 < n:
            next_start = raw_matches[i + 1][0]
            between_next = text[end:next_start]
            split_n = _find_split_point(between_next)
            right_boundary = end + split_n
        else:
            right_boundary = min(len(text), end + 45)

        before_window = text[left_boundary:start].strip()
        after_window = text[end:right_boundary].strip()
        local_window = text[max(0, start - 30):min(len(text), end + 30)].strip()
        b_clean = re.sub(r'[,:;]+$', '', before_window)

        # 0. Check recurring & billing period for this entity
        b_period = None
        is_rec = False
        if not NON_RECURRING_PATTERN.search(local_window):
            for p_name, pat in PERIOD_PATTERNS:
                if pat.search(after_window) or pat.search(before_window):
                    b_period = p_name
                    is_rec = True
                    break
            if not is_rec and RECURRING_KEYWORDS.search(local_window):
                is_rec = True

        # Check explicit price change pair
        if change_pair is not None:
            if i == change_pair[0]:
                initial.append(("previous_price", "price_change_to", b_period, is_rec))
                continue
            elif i == change_pair[1]:
                initial.append(("current_price", "price_change_from", b_period, is_rec))
                continue

        # 1. Setup Fee
        if SETUP_FEE_PATTERN.search(local_window):
            initial.append(("setup_fee", "additional_cost", None, False))
            continue

        # 2. Explicit Total
        if TOTAL_PATTERN.search(before_window) or re.search(r'^\s*total\b', after_window, re.IGNORECASE):
            initial.append(("total_price", "final_total", b_period, is_rec))
            continue

        # 3. Discount Amount
        if DISCOUNT_BEFORE_PATTERN.search(b_clean) and not re.search(r'\b(?:on|over|above)\s*$', b_clean, re.IGNORECASE):
            initial.append(("discount_amount", "discount", b_period, False))
            continue
        if DISCOUNT_AFTER_PATTERN.search(after_window):
            initial.append(("discount_amount", "discount", b_period, False))
            continue

        # 4. Original Price vs Sale Price
        if ORIGINAL_PRICE_PATTERN.search(before_window) or re.search(r'^\s*(?:original\s+price|originally|mrp)\b', after_window, re.IGNORECASE):
            initial.append(("original_price", "original_for_discount", b_period, is_rec))
            continue
        if SALE_PRICE_PATTERN.search(before_window) or re.search(r'^\s*(?:sale\s+price|deal\s+price|offer\s+price|special\s+price)\b', after_window, re.IGNORECASE):
            initial.append(("sale_price", "discounted_from", b_period, is_rec))
            continue

        # 5. Trial price
        if re.search(r'\b(?:free\s+trial|trial)\b', orig_txt, re.IGNORECASE) or re.search(r'\btrial\b', before_window, re.IGNORECASE) or re.search(r'\btrial\b', after_window, re.IGNORECASE):
            initial.append(("trial_price", "trial_offer", b_period, is_rec))
            continue

        # 6. Renewal price
        if re.search(r'\b(?:renews?(?:\s+at|\s+for)?|renewal|then)\b', before_window, re.IGNORECASE) or re.search(r'\b(?:renews?(?:\s+at|\s+for)?|renewal)\b', after_window, re.IGNORECASE):
            initial.append(("renewal_price", "renews_from", b_period, True))
            continue

        # 7. Promotional / Initial price (e.g. "First 3 months ₹199, then ₹799/month" or "₹99 for the first month")
        if (promo_months is not None or promo_days is not None) and i == 0 and n > 1:
            if b_period is None and promo_months is not None:
                b_period = "month"
            initial.append(("initial_price", "trial_offer", b_period, True))
            continue

        # Explicit fee labels take precedence over a nearby base-price label.
        label_before_entity = text[max(0, start - 60):start]
        if re.search(r'\badditional\s+fee\b', label_before_entity, re.IGNORECASE):
            initial.append(("other_fee", "additional_cost", b_period, False))
            continue

        # 8. Base Price from keywords (e.g. "Base price is ₹999/month")
        if BASE_PRICE_PATTERN.search(before_window) or BASE_PRICE_PATTERN.search(after_window):
            initial.append(("base_price", "base_cost", b_period, is_rec))
            continue

        # 9. Subscription price
        if is_rec:
            initial.append(("subscription_price", "recurring_cost", b_period, True))
            continue

        # 10. Base Price when followed by additive/subtractive operator or unpriced fee disclosure
        if re.search(r'^(?:\s*(?:\+|plus|less|minus)\b|\+)', after_window, re.IGNORECASE):
            initial.append(("base_price", "base_cost", b_period, is_rec))
            continue
        if re.search(r'^(?:\s*\.|\s*,\s*)?\s*(?:taxes?\s+(?:and\s+fees?\s+)?apply|taxes?\s+(?:and\s+charges?\s+)?extra|taxes?\s+excluded|exclusive\s+of\s+taxes?|fees?\s+apply)\b', after_window, re.IGNORECASE):
            initial.append(("base_price", "base_cost", b_period, is_rec))
            continue
        after_same_sentence = re.split(r'[.!?\n]', after_window)[0]
        if re.search(r'^\s*(?:including|inclusive\s+of|includes)\s+(?:all\s+)?(?:taxes?|shipping|fees?|charges?|gst|vat)\b', after_same_sentence, re.IGNORECASE):
            initial.append(("base_price", "base_cost", b_period, is_rec))
            continue

        # 11. Fees & Taxes
        fee_found = None
        is_inclusive_fee = bool(re.search(r'\b(?:including|includes|inclusive\s+of|inclusive)\b', before_window, re.IGNORECASE))
        for cost_type, pat in FEE_PATTERNS:
            if pat.search(before_window):
                fee_found = cost_type
                break
            elif after_same_sentence.strip() and pat.search(after_same_sentence):
                # If after_same_sentence starts with 'including' or 'inclusive of'
                # e.g. "₹999 including all taxes" or "₹499 including shipping"
                # The entity itself is NOT a tax or shipping fee! It is the base price!
                if re.search(r'^\s*(?:including|inclusive\s+of|includes|with\s+(?:all\s+)?taxes)\b', after_same_sentence, re.IGNORECASE):
                    continue
                fee_found = cost_type
                break
        if fee_found:
            rel = "included_fee" if is_inclusive_fee else "additional_cost"
            initial.append((fee_found, rel, b_period, False))
            continue

        initial.append(("unknown", None, b_period, is_rec))

    # Second pass: establish inter-entity links and contextual relationships
    results: List[Tuple[str, Optional[str], Optional[int], Optional[str], bool]] = []
    base_idx: Optional[int] = None
    orig_idx: Optional[int] = None
    sale_idx: Optional[int] = None

    for i, (ctype, _, _, _) in enumerate(initial):
        if ctype == "base_price" and base_idx is None:
            base_idx = i
        elif ctype == "original_price" and orig_idx is None:
            orig_idx = i
        elif ctype == "sale_price" and sale_idx is None:
            sale_idx = i

    # If first entity is followed by "+ fee" or "less discount" or general fee
    if n >= 2:
        for i in range(n - 1):
            between = text[raw_matches[i][1]:raw_matches[i + 1][0]].strip().lower()
            if initial[i][0] == "unknown" and (_is_additional_cost(initial[i + 1][0]) or initial[i + 1][0].endswith(("_fee", "tax", "add_on"))):
                initial[i] = ("base_price", "base_cost", initial[i][2], initial[i][3])
                if base_idx is None:
                    base_idx = i
            elif ("less" in between or "minus" in between) and initial[i][0] == "unknown" and initial[i + 1][0] == "discount_amount":
                initial[i] = ("base_price", "base_cost", initial[i][2], initial[i][3])
                if base_idx is None:
                    base_idx = i

    # Build final tuple (cost_type, relationship_type, related_entity_index, billing_period, recurring)
    for i, (ctype, rel_type, b_period, is_rec) in enumerate(initial):
        related_index: Optional[int] = None

        # Link price change pair
        if change_pair is not None:
            if i == change_pair[0]:
                results.append((ctype, rel_type, change_pair[1], b_period, is_rec))
                continue
            elif i == change_pair[1]:
                results.append((ctype, rel_type, change_pair[0], b_period, is_rec))
                continue

        # Check for alternative price conjunction ("or", "either", "between ... and ...", tier plans)
        is_alt_pair = False
        if i + 1 < n:
            between = text[raw_matches[i][1]:raw_matches[i + 1][0]].strip().lower()
            before_i = text[max(0, raw_matches[i][0] - 50):raw_matches[i][0]].strip().lower()
            if re.search(r'\b(?:or|either)\b', between):
                is_alt_pair = True
            elif re.search(r'\b(?:choose\s+between|between)\b', before_i) and re.search(r'\band\b', between):
                is_alt_pair = True
            elif re.search(r'\b(?:standard|premium|basic|pro)\b', text[raw_matches[i][1]:raw_matches[i + 1][1]].lower()):
                is_alt_pair = True

        if is_alt_pair:
            rel_type = "alternative"
            related_index = i + 1
        elif i > 0 and results and results[i - 1][1] == "alternative":
            rel_type = "alternative"
            related_index = i - 1

        # Link renewal price to trial or initial price
        elif ctype == "renewal_price":
            for j in range(i):
                if initial[j][0] in ("trial_price", "initial_price"):
                    rel_type = "renews_from"
                    related_index = j
                    break

        # Link fees to base price if present
        elif (ctype.endswith(("_fee", "tax", "add_on")) or _is_additional_cost(ctype)) and base_idx is not None and base_idx != i:
            if rel_type != "included_fee":
                rel_type = "additional_cost"
            related_index = base_idx

        # Link original and sale price
        elif ctype == "original_price" and sale_idx is not None:
            rel_type = "original_for_discount"
            related_index = sale_idx
        elif ctype == "sale_price" and orig_idx is not None:
            rel_type = "discounted_from"
            related_index = orig_idx

        # Link total price to base price
        elif ctype == "total_price":
            rel_type = "final_total"
            if base_idx is not None:
                related_index = base_idx

        results.append((ctype, rel_type, related_index, b_period, is_rec))

    # Link preceding trial/initial price entity to renewal entity
    for i, (ctype, rel_type, rel_idx, b_period, is_rec) in enumerate(results):
        if ctype in ("trial_price", "initial_price") and rel_idx is None:
            for j in range(i + 1, n):
                if results[j][0] == "renewal_price":
                    results[i] = (ctype, "trial_offer", j, b_period, is_rec)
                    break

    return results


def _build_response_dict(
    displayed_price: Optional[DisplayedPrice] = None,
    additional_costs: Optional[float] = None,
    additional_cost: Optional[float] = None,
    explicit_total: Optional[float] = None,
    calculated_subtotal: Optional[float] = None,
    known_total: Optional[float] = None,
    total_source: Optional[str] = None,
    price_difference: Optional[float] = None,
    additional_cost_percentage: Optional[float] = None,
    discount_amount: Optional[float] = None,
    discount_percentage: Optional[float] = None,
    is_alternative_pricing: bool = False,
    trial_price: Optional[float] = None,
    trial_currency: Optional[str] = None,
    trial_duration_days: Optional[int] = None,
    initial_price: Optional[float] = None,
    initial_currency: Optional[str] = None,
    later_price: Optional[float] = None,
    renewal_price: Optional[float] = None,
    renewal_currency: Optional[str] = None,
    currency: Optional[str] = None,
    billing_period: Optional[str] = None,
    recurring: bool = False,
    promotion_duration_days: Optional[int] = None,
    promotion_duration_months: Optional[int] = None,
    price_change_percentage: Optional[float] = None,
    previous_price: Optional[float] = None,
    previous_currency: Optional[str] = None,
    current_price: Optional[float] = None,
    current_currency: Optional[str] = None,
    price_change: Optional[float] = None,
    price_change_detected: bool = False,
    price_changed: Optional[bool] = None,
    price_change_direction: Optional[str] = None,
    late_disclosed: Optional[bool] = None,
    late_disclosure_detected: Optional[bool] = None,
    additional_cost_detected: Optional[bool] = None,
    renewal_price_detected: Optional[bool] = None,
    initial_price_position: Optional[int] = None,
    additional_cost_position: Optional[int] = None,
) -> Dict[str, Any]:
    """Helper to build PriceAnalysisResponse dict with guaranteed Phase 8.5 consistency."""
    add_c = additional_costs if additional_costs is not None else additional_cost
    add_detected = (add_c is not None and add_c > 0) if additional_cost_detected is None else additional_cost_detected
    late_detected = (late_disclosed is True) if late_disclosure_detected is None else late_disclosure_detected
    chg_detected = price_change_detected or (price_changed is True)
    ren_detected = (renewal_price is not None) if renewal_price_detected is None else renewal_price_detected

    if price_change_direction is None and chg_detected:
        if price_change is not None:
            if price_change > 0:
                price_change_direction = "increase"
            elif price_change < 0:
                price_change_direction = "decrease"
        elif later_price is not None and initial_price is not None:
            if later_price > initial_price:
                price_change_direction = "increase"
            elif later_price < initial_price:
                price_change_direction = "decrease"

    return {
        "displayed_price": displayed_price,
        "additional_costs": add_c,
        "additional_cost": add_c,
        "explicit_total": explicit_total,
        "calculated_subtotal": calculated_subtotal,
        "known_total": known_total,
        "total_source": total_source,
        "price_difference": price_difference,
        "additional_cost_percentage": additional_cost_percentage,
        "discount_amount": discount_amount,
        "discount_percentage": discount_percentage,
        "is_alternative_pricing": is_alternative_pricing,
        "trial_price": trial_price,
        "trial_currency": trial_currency,
        "trial_duration_days": trial_duration_days,
        "initial_price": initial_price,
        "initial_currency": initial_currency,
        "later_price": later_price,
        "renewal_price": renewal_price,
        "renewal_currency": renewal_currency,
        "currency": currency,
        "billing_period": billing_period,
        "recurring": recurring,
        "promotion_duration_days": promotion_duration_days,
        "promotion_duration_months": promotion_duration_months,
        "price_change_percentage": price_change_percentage,
        "previous_price": previous_price,
        "previous_currency": previous_currency,
        "current_price": current_price,
        "current_currency": current_currency,
        "price_change": price_change,
        "price_change_detected": chg_detected,
        "price_changed": chg_detected,
        "price_change_direction": price_change_direction,
        "late_disclosed": late_disclosed,
        "late_disclosure_detected": late_detected,
        "additional_cost_detected": add_detected,
        "renewal_price_detected": ren_detected,
        "initial_price_position": initial_price_position,
        "additional_cost_position": additional_cost_position,
    }


def _calculate_financial_summary(
    text: str,
    entities: List[PriceEntity],
) -> Dict[str, Any]:
    """Calculate deterministic financial relationship and cost metrics (Phase 8.3, 8.4, 8.5)."""
    n = len(entities)

    # Check promotional durations from text
    promo_months: Optional[int] = None
    for p in PROMO_MONTHS_PATTERNS:
        m_p = p.search(text)
        if m_p:
            promo_months = int(m_p.group(1)) if m_p.groups() and m_p.group(1) else 1
            break

    promo_days: Optional[int] = None
    for p in PROMO_DAYS_PATTERNS:
        m_p = p.search(text)
        if m_p:
            promo_days = int(m_p.group(1)) if m_p.groups() and m_p.group(1) else None
            break

    # Check trial duration from text
    trial_dur: Optional[int] = None
    is_non_monetary_trial_neg = bool(re.search(r'\b(?:return\s+period|warranty|password|version\s+launched)\b', text, re.IGNORECASE))
    if not is_non_monetary_trial_neg:
        for p in TRIAL_DURATION_PATTERNS:
            m_dur = p.search(text)
            if m_dur:
                trial_dur = int(m_dur.group("days"))
                break

    if n == 0:
        return _build_response_dict(
            promotion_duration_days=promo_days,
            promotion_duration_months=promo_months,
            trial_duration_days=trial_dur if not is_non_monetary_trial_neg else None,
        )

    # 1. Multi-currency safety
    currencies = {e.currency for e in entities if e.currency}
    has_multi_curr = len(currencies) > 1

    # 2. Alternative pricing check
    is_alt = _is_price_alternative(text, entities)

    # 3. Phase 8.4 recurring, trial, and base entity extraction
    base_ent = next((e for e in entities if e.type == "base_price"), None)
    trial_ent = next((e for e in entities if e.type == "trial_price"), None)
    trial_price = trial_ent.amount if trial_ent else None
    trial_currency = trial_ent.currency if trial_ent else None

    initial_ent = next((e for e in entities if e.type == "initial_price"), None)
    initial_price = initial_ent.amount if initial_ent else None
    initial_currency = initial_ent.currency if initial_ent else None

    renewal_ent = next((e for e in entities if e.type == "renewal_price"), None)
    renewal_price = renewal_ent.amount if renewal_ent else None
    renewal_currency = renewal_ent.currency if renewal_ent else None

    # Billing period and recurring resolution
    overall_billing_period = None
    overall_recurring = False

    if renewal_ent:
        overall_billing_period = renewal_ent.billing_period
        overall_recurring = renewal_ent.recurring
    elif initial_ent:
        overall_billing_period = initial_ent.billing_period
        overall_recurring = initial_ent.recurring
    else:
        sub_ent = next((e for e in entities if e.type == "subscription_price"), None)
        if sub_ent:
            overall_billing_period = sub_ent.billing_period
            overall_recurring = sub_ent.recurring

    # Check for text-level recurring billing when renewal amount is unstated
    if renewal_price is None and re.search(r'\b(?:regular\s+monthly\s+pricing|monthly\s+subscription)\b', text, re.IGNORECASE):
        overall_recurring = True
        overall_billing_period = "month"

    # Any recurring entity sets recurring flag
    if any(e.recurring for e in entities):
        overall_recurring = True

    # If alternative pricing with multiple distinct billing periods, overall billing period is ambiguous
    alt_periods = {e.billing_period for e in entities if e.billing_period}
    if is_alt and len(alt_periods) > 1:
        overall_billing_period = None

    # Price difference and percentage for promotional -> renewal
    promo_diff: Optional[float] = None
    promo_pct: Optional[float] = None
    if initial_price is not None and renewal_price is not None:
        promo_diff, promo_pct = _calculate_price_change(initial_price, renewal_price)

    # Primary currency
    primary_currency = None
    if not has_multi_curr and len(currencies) == 1:
        primary_currency = next(iter(currencies))

    # If multi-currency or alternative pricing, isolate and do not combine totals
    if has_multi_curr or is_alt:
        return _build_response_dict(
            displayed_price=None,
            is_alternative_pricing=is_alt,
            trial_price=trial_price,
            trial_currency=trial_currency,
            trial_duration_days=trial_dur,
            initial_price=initial_price,
            initial_currency=initial_currency,
            later_price=renewal_price,
            renewal_price=renewal_price,
            renewal_currency=renewal_currency,
            currency=primary_currency,
            billing_period=overall_billing_period,
            recurring=overall_recurring,
            promotion_duration_days=promo_days,
            promotion_duration_months=promo_months,
            late_disclosed=False if is_alt else None,
            price_change_detected=False,
        )

    # Phase 8.5: Explicit Price Change Detection (e.g. "Price increased from ₹999 to ₹1299")
    prev_ent = next((e for e in entities if e.type == "previous_price"), None)
    curr_ent = next((e for e in entities if e.type == "current_price"), None)

    if prev_ent and curr_ent:
        p_change, p_pct = _calculate_price_change(prev_ent.amount, curr_ent.amount)
        change_detected = (p_change != 0.0)

        displayed = DisplayedPrice(amount=curr_ent.amount, currency=curr_ent.currency) if curr_ent.currency else None
        ren_price = curr_ent.amount if (curr_ent.recurring or "renew" in text.lower()) else None
        ren_curr = curr_ent.currency if ren_price else None

        direction = "increase" if p_change > 0 else ("decrease" if p_change < 0 else None)
        diff = abs(p_change) if change_detected else 0.0

        return _build_response_dict(
            displayed_price=displayed,
            price_difference=diff,
            is_alternative_pricing=False,
            initial_price=prev_ent.amount,
            initial_currency=prev_ent.currency,
            later_price=curr_ent.amount,
            renewal_price=ren_price,
            renewal_currency=ren_curr,
            currency=curr_ent.currency or primary_currency,
            billing_period=curr_ent.billing_period or prev_ent.billing_period or overall_billing_period,
            recurring=curr_ent.recurring or prev_ent.recurring or overall_recurring,
            price_change_percentage=p_pct,
            previous_price=prev_ent.amount,
            previous_currency=prev_ent.currency,
            current_price=curr_ent.amount,
            current_currency=curr_ent.currency,
            price_change=p_change,
            price_change_detected=change_detected,
            price_change_direction=direction,
            late_disclosed=False,
            initial_price_position=prev_ent.character_start,
        )

    # Promotional / Multi-stage subscriptions (e.g. "First 3 months ₹199, then ₹799/month")
    if initial_ent and renewal_ent:
        displayed = DisplayedPrice(amount=initial_ent.amount, currency=initial_ent.currency) if initial_ent.currency else None
        diff = promo_diff if promo_diff is not None else (_clean_float(_to_decimal(renewal_price) - _to_decimal(initial_price)) if renewal_price and initial_price else None)
        change_detected = bool(diff and diff != 0)
        direction = "increase" if (diff and diff > 0) else ("decrease" if (diff and diff < 0) else None)
        return _build_response_dict(
            displayed_price=displayed,
            price_difference=abs(diff) if diff is not None else None,
            is_alternative_pricing=False,
            trial_price=trial_price,
            trial_currency=trial_currency,
            trial_duration_days=trial_dur,
            initial_price=initial_price,
            initial_currency=initial_currency,
            later_price=renewal_price,
            renewal_price=renewal_price,
            renewal_currency=renewal_currency,
            currency=primary_currency,
            billing_period=overall_billing_period,
            recurring=overall_recurring,
            promotion_duration_days=promo_days,
            promotion_duration_months=promo_months,
            price_change_percentage=promo_pct,
            previous_price=initial_price,
            previous_currency=initial_currency,
            current_price=renewal_price,
            current_currency=renewal_currency,
            price_change=diff,
            price_change_detected=change_detected,
            price_change_direction=direction,
            late_disclosed=False,
            initial_price_position=initial_ent.character_start,
        )

    # Trial + Renewal subscriptions (e.g. "7-day free trial, then ₹999/month")
    if trial_ent or renewal_ent:
        displayed = None
        if base_ent and base_ent.currency:
            displayed = DisplayedPrice(amount=base_ent.amount, currency=base_ent.currency)
        elif trial_ent and trial_ent.amount > 0 and trial_ent.currency:
            displayed = DisplayedPrice(amount=trial_ent.amount, currency=trial_ent.currency)
        else:
            displayed = None

        trial_diff = None
        trial_pct = None
        trial_change_detected = False
        trial_direction = None
        if trial_ent and trial_ent.amount > 0 and renewal_price is not None:
            trial_diff, trial_pct = _calculate_price_change(trial_ent.amount, renewal_price)
            trial_change_detected = True
            trial_direction = "increase" if trial_diff > 0 else ("decrease" if trial_diff < 0 else None)

        return _build_response_dict(
            displayed_price=displayed,
            price_difference=abs(trial_diff) if trial_diff is not None else None,
            is_alternative_pricing=False,
            trial_price=trial_price,
            trial_currency=trial_currency,
            trial_duration_days=trial_dur,
            initial_price=initial_price,
            initial_currency=initial_currency,
            later_price=renewal_price,
            renewal_price=renewal_price,
            renewal_currency=renewal_currency,
            currency=primary_currency,
            billing_period=overall_billing_period,
            recurring=overall_recurring,
            promotion_duration_days=promo_days,
            promotion_duration_months=promo_months,
            price_change_percentage=trial_pct,
            previous_price=trial_ent.amount if (trial_ent and trial_ent.amount > 0) else None,
            previous_currency=trial_ent.currency if (trial_ent and trial_ent.amount > 0) else None,
            current_price=renewal_price if (trial_ent and trial_ent.amount > 0) else None,
            current_currency=renewal_currency if (trial_ent and trial_ent.amount > 0) else None,
            price_change=trial_diff,
            price_change_detected=trial_change_detected,
            price_change_direction=trial_direction,
            late_disclosed=False,
            initial_price_position=trial_ent.character_start if (trial_ent and trial_ent.character_start is not None) else (base_ent.character_start if base_ent else None),
        )

    # 4. Missing / Incomplete fee check (e.g. "+ shipping" without numeric amount)
    unspecified_match = re.search(
        r'(?:(?:\+|plus)\s+(?:a\s+)?(?:standard\s+)?(?:shipping|delivery|taxes?|gst|fees?|charges?|handling|processing)|(?:taxes?|fees?|charges?)\s+(?:and\s+(?:fees?|charges?)\s+)?(?:apply|applies|extra|excluded))\b',
        text,
        re.IGNORECASE,
    )
    has_unspecified_fee = False
    if unspecified_match:
        kw = unspecified_match.group(0).lower()
        fee_present = any(
            any(name in kw for name in ["shipping", "delivery", "tax", "gst", "processing", "handling", "fee", "charge"])
            and _is_additional_cost(e.type)
            for e in entities
        )
        if not fee_present:
            has_unspecified_fee = True

    if has_unspecified_fee:
        displayed = DisplayedPrice(amount=base_ent.amount, currency=base_ent.currency) if (base_ent and base_ent.currency) else None
        return _build_response_dict(
            displayed_price=displayed,
            is_alternative_pricing=False,
            currency=primary_currency,
            billing_period=overall_billing_period,
            recurring=overall_recurring,
            promotion_duration_days=promo_days,
            promotion_duration_months=promo_months,
            late_disclosed=False,
            initial_price_position=base_ent.character_start if base_ent else None,
        )

    # 5. Discounts: Original price vs Sale price
    orig_ent = next((e for e in entities if e.type == "original_price"), None)
    sale_ent = next((e for e in entities if e.type == "sale_price"), None)

    if orig_ent and sale_ent:
        orig_d = _to_decimal(orig_ent.amount)
        sale_d = _to_decimal(sale_ent.amount)
        diff_d = orig_d - sale_d
        disc_amt = _clean_float(diff_d) if diff_d > 0 else 0.0
        disc_pct = _clean_float((diff_d / orig_d) * Decimal(100)) if orig_d > 0 and diff_d > 0 else None
        return _build_response_dict(
            displayed_price=DisplayedPrice(amount=sale_ent.amount, currency=sale_ent.currency) if sale_ent.currency else None,
            price_difference=disc_amt,
            discount_amount=disc_amt,
            discount_percentage=disc_pct,
            is_alternative_pricing=False,
            currency=primary_currency,
            billing_period=overall_billing_period,
            recurring=overall_recurring,
            promotion_duration_days=promo_days,
            promotion_duration_months=promo_months,
            late_disclosed=False,
            initial_price_position=orig_ent.character_start,
        )

    # 6. Discounts: Base / Original price less discount amount
    disc_ent = next((e for e in entities if e.type == "discount_amount"), None)
    if (base_ent or orig_ent) and disc_ent:
        primary = base_ent or orig_ent
        primary_d = _to_decimal(primary.amount)
        disc_d = _to_decimal(disc_ent.amount)
        tot_d = primary_d - disc_d
        disc_amt = _clean_float(disc_d)
        disc_pct = _clean_float((disc_d / primary_d) * Decimal(100)) if primary_d > 0 else None
        tot = _clean_float(tot_d)
        return _build_response_dict(
            displayed_price=DisplayedPrice(amount=primary.amount, currency=primary.currency) if primary.currency else None,
            calculated_subtotal=tot,
            known_total=tot,
            total_source="computed",
            price_difference=disc_amt,
            discount_amount=disc_amt,
            discount_percentage=disc_pct,
            is_alternative_pricing=False,
            currency=primary_currency,
            billing_period=overall_billing_period,
            recurring=overall_recurring,
            promotion_duration_days=promo_days,
            promotion_duration_months=promo_months,
            late_disclosed=False,
            initial_price_position=primary.character_start,
        )

    # 7. Additional fees + Base price + Explicit total + Standalone price
    explicit_total_ent = next((e for e in entities if e.type == "total_price"), None)
    all_fee_ents = [e for e in entities if _is_additional_cost(e.type)]

    inclusive_fee_ents = [
        e for e in all_fee_ents
        if e.relationship_type == "included_fee"
        or re.search(r'\b(?:including|includes|inclusive\s+of|inclusive)\b', text[max(0, (e.character_start or 0) - 35):e.character_start or 0], re.IGNORECASE)
    ]
    fee_ents = [e for e in all_fee_ents if e not in inclusive_fee_ents]

    # If single entity without fees, totals, or discounts, check if text establishes displayed price
    if base_ent is None and len(entities) == 1 and not all_fee_ents and explicit_total_ent is None:
        e0 = entities[0]
        if not _is_additional_cost(e0.type) and e0.type not in ("total_price", "discount_amount", "trial_price", "renewal_price", "previous_price", "current_price"):
            if e0.type == "base_price" or re.search(r'[-—–:]\s*$', text[:e0.character_start or 0].strip()):
                base_ent = e0

    if base_ent and base_ent.currency:
        base_d = _to_decimal(base_ent.amount)
        displayed = DisplayedPrice(amount=base_ent.amount, currency=base_ent.currency)
    else:
        base_d = None
        displayed = None

    if fee_ents:
        fee_sum_d = sum(_to_decimal(e.amount) for e in fee_ents)
        additional_costs = _clean_float(fee_sum_d)
    else:
        fee_sum_d = Decimal(0)
        additional_costs = None

    explicit_total = explicit_total_ent.amount if explicit_total_ent else None

    calculated_subtotal = None
    if base_d is not None and fee_ents:
        calculated_subtotal = _clean_float(base_d + fee_sum_d)
    elif base_d is not None and not fee_ents and inclusive_fee_ents:
        calculated_subtotal = _clean_float(base_d)

    known_total = None
    total_source = None

    if explicit_total is not None:
        known_total = explicit_total
        total_source = "explicit"
    elif calculated_subtotal is not None:
        known_total = calculated_subtotal
        total_source = "computed"
    elif base_d is not None and not fee_ents and not all_fee_ents:
        known_total = _clean_float(base_d)
        total_source = "computed"

    price_diff = None
    if base_d is not None and known_total is not None:
        price_diff = _clean_float(_to_decimal(known_total) - base_d)
    elif additional_costs is not None:
        price_diff = additional_costs

    add_pct = None
    if base_d is not None and base_d > 0 and additional_costs is not None:
        add_pct = _clean_float((_to_decimal(additional_costs) / base_d) * Decimal(100))

    # If standalone subscription price entity exists
    sub_ent = next((e for e in entities if e.type == "subscription_price"), None)
    if displayed is None and sub_ent and sub_ent.currency and not all_fee_ents and explicit_total is None:
        displayed = DisplayedPrice(amount=sub_ent.amount, currency=sub_ent.currency)

    # Late disclosure determination
    late_disclosed, init_pos, fee_pos = _detect_late_disclosure(base_ent, all_fee_ents, has_unspecified_fee, text)

    return _build_response_dict(
        displayed_price=displayed,
        additional_costs=additional_costs,
        explicit_total=explicit_total,
        calculated_subtotal=calculated_subtotal,
        known_total=known_total,
        total_source=total_source,
        price_difference=price_diff,
        additional_cost_percentage=add_pct,
        is_alternative_pricing=False,
        currency=primary_currency,
        billing_period=overall_billing_period,
        recurring=overall_recurring,
        promotion_duration_days=promo_days,
        promotion_duration_months=promo_months,
        late_disclosed=late_disclosed,
        initial_price_position=init_pos,
        additional_cost_position=fee_pos,
    )


class PriceAnalyzer:
    """Service for extracting explicit monetary entities, classifying cost types, and calculating totals."""

    def analyze(self, text: str) -> PriceAnalysisResponse:
        """Analyze text, extract monetary entities, classify cost types, and compute financial metrics."""
        if not text or not text.strip():
            return PriceAnalysisResponse(source="price", entities=[])

        raw_matches: List[Tuple[int, int, Optional[str], float, str]] = []

        # Find prefix matches (e.g. ₹499, $29.99)
        for m in PREFIX_PATTERN.finditer(text):
            raw_curr = m.group("prefix")
            raw_amt = m.group("amount")
            full_match = m.group(0)

            # Security: Reject if the matched digits are part of a payment-card number
            digits_only = re.sub(r'\D', '', full_match)
            if len(digits_only) >= 13:
                continue

            curr = _normalize_currency(raw_curr)
            amt = _normalize_amount(raw_amt)
            raw_matches.append((m.start(), m.end(), curr, amt, full_match))

        # Find suffix matches (e.g. 499 INR, 999 Rs.) that do not overlap with prefix matches
        for m in SUFFIX_PATTERN.finditer(text):
            if any(m.start() < end and m.end() > start for start, end, _, _, _ in raw_matches):
                continue
            raw_curr = m.group("suffix")
            raw_amt = m.group("amount")
            full_match = m.group(0)

            digits_only = re.sub(r'\D', '', full_match)
            if len(digits_only) >= 13:
                continue

            curr = _normalize_currency(raw_curr)
            amt = _normalize_amount(raw_amt)
            raw_matches.append((m.start(), m.end(), curr, amt, full_match))

        # Check for explicit free trial without numeric digits (Section 19: treat free -> ₹0 trial price)
        is_non_monetary_trial_neg = bool(re.search(r'\b(?:return\s+period|warranty|password|version\s+launched)\b', text, re.IGNORECASE))
        m_free = FREE_TRIAL_PATTERN.search(text)
        if m_free and not is_non_monetary_trial_neg:
            has_overlap = any(m_free.start() < end and m_free.end() > start for start, end, _, _, _ in raw_matches)
            if not has_overlap:
                default_curr = raw_matches[0][2] if raw_matches else None
                raw_matches.append((m_free.start(), m_free.end(), default_curr, 0.0, m_free.group(0)))

        # Sort by appearance order in text
        raw_matches.sort(key=lambda x: x[0])

        # Classify cost types and semantic relationships
        classifications = _classify_and_link_entities(text, raw_matches)

        entities: List[PriceEntity] = []
        for idx, ((start, end, currency, amount, original_text), (cost_type, rel_type, rel_idx, b_period, is_rec)) in enumerate(zip(raw_matches, classifications)):
            context = _extract_sentence_context(text, start, end)
            sent_idx = _compute_sentence_index(text, start)
            entities.append(
                PriceEntity(
                    amount=amount,
                    currency=currency,
                    original_text=original_text,
                    context=context,
                    type=cost_type,
                    relationship_type=rel_type,
                    related_entity_index=rel_idx,
                    billing_period=b_period,
                    recurring=is_rec,
                    character_start=start,
                    character_end=end,
                    entity_index=idx,
                    position_start=start,
                    position_end=end,
                    sentence_index=sent_idx,
                    disclosure_order=idx,
                )
            )

        # Financial summary and cost calculations (Phase 8.3, 8.4, 8.5)
        summary = _calculate_financial_summary(text, entities)

        # Security: Do not log full input text
        _logger.info("Price analysis complete: extracted %d monetary entities", len(entities))

        return PriceAnalysisResponse(
            source="price",
            entities=entities,
            **summary,
        )

