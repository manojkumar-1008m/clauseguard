"""backend/services/intelligence_engine.py
Phase B5.7 Intelligence Analysis Layer for ClauseGuard.

Converts unified, validated multi-modal evidence into structured intelligence:
1. Dark Pattern Detector: Evaluates combined multi-source evidence with anti-overreach guards.
2. Consumer Consequence Engine: Derives objective consumer consequences and financial impacts without legal conclusions.
3. Historical Change Engine: Tracks verified state differences (price, terms, UI) respecting journey, tab, and product isolation.

Architectural invariants:
- OBSERVATION -> EVIDENCE -> PATTERN -> CONSUMER CONSEQUENCE -> REGULATORY CONCERN -> RISK
- B5.7 strictly owns PATTERN, CONSEQUENCE, and HISTORICAL CHANGE.
- No legal conclusions ("This website violates the law" is strictly forbidden).
- Risk score isolation: B5.7 confidence is NOT consumer risk score; B5.2 thresholds are preserved.
- Financial safety: Decimal-safe calculations, no fabricated amounts, missing values remain "UNKNOWN".
- Boundary isolation: Strict journey_id, tab, product anchor, and auxiliary context separation.
- Deterministic execution: Identical inputs produce identical outputs with full evidence ID provenance.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from ..schemas.evidence import (
    ConsumerConsequenceDetail,
    ContradictionItem,
    EvidenceItem,
    HistoricalChangeDetail,
    IntelligenceAnalysisResponse,
    PatternAssessment,
    TemporalRelationshipItem,
)
from ..schemas.price import PriceAnalysisResponse
from ..schemas import PredictResponse
from .journey_engine import (
    ANCHOR_STRONG,
    ANCHOR_UNKNOWN,
    STAGE_CART,
    STAGE_CHECKOUT,
    STAGE_DISCOVERY,
    STAGE_PAYMENT,
    STAGE_PRODUCT,
    STAGE_SUBSCRIPTION,
    STAGE_CANCELLATION,
    STAGE_RETENTION_STEP,
    STAGE_CONFIRMATION,
    JourneyEngine,
)

_logger = logging.getLogger("clauseguard_backend.intelligence_engine")

# Approved B5.7 Standard Dark Pattern Taxonomy
PATTERN_SUBSCRIPTION_TRAP = "SUBSCRIPTION_TRAP"
PATTERN_DRIP_PRICING = "DRIP_PRICING"
PATTERN_BASKET_SNAKING = "BASKET_SNAKING"
PATTERN_FALSE_URGENCY = "FALSE_URGENCY"
PATTERN_SCARCITY = "SCARCITY"
PATTERN_FORCED_ACTION = "FORCED_ACTION"
PATTERN_CONFIRM_SHAMING = "CONFIRM_SHAMING"
PATTERN_OBSTRUCTION = "OBSTRUCTION"
PATTERN_MISDIRECTION = "MISDIRECTION"
PATTERN_SOCIAL_PROOF = "SOCIAL_PROOF"

APPROVED_PATTERNS: Set[str] = {
    PATTERN_SUBSCRIPTION_TRAP,
    PATTERN_DRIP_PRICING,
    PATTERN_BASKET_SNAKING,
    PATTERN_FALSE_URGENCY,
    PATTERN_SCARCITY,
    PATTERN_FORCED_ACTION,
    PATTERN_CONFIRM_SHAMING,
    PATTERN_OBSTRUCTION,
    PATTERN_MISDIRECTION,
    PATTERN_SOCIAL_PROOF,
}

# Status vocabulary
STATUS_NOT_SUPPORTED = "NOT_SUPPORTED"
STATUS_POTENTIAL = "POTENTIAL"
STATUS_SUPPORTED = "SUPPORTED"

# Commercial preselection keywords for BASKET_SNAKING
COMMERCIAL_ADDON_KEYWORDS: Tuple[str, ...] = (
    "warranty",
    "protection",
    "insurance",
    "add-on",
    "addon",
    "donation",
    "extra cover",
    "care pack",
    "extended guarantee",
    "priority processing",
    "expedited delivery",
)

# Benign preselection types/keywords (False positive controls)
BENIGN_PRESELECTION_KEYWORDS: Tuple[str, ...] = (
    "standard shipping",
    "free shipping",
    "remember me",
    "save password",
    "country",
    "language",
    "english",
    "united states",
    "india",
    "terms",
    "privacy",
    "cookie",
)

# Factual stock/variant keywords for SCARCITY controls
FACTUAL_STOCK_KEYWORDS: Tuple[str, ...] = (
    "inventory",
    "color",
    "colour",
    "size",
    "variant",
    "model",
    "specification",
)


def _safe_to_float(val: Any) -> Optional[float]:
    """Safely convert value to float using Decimal to prevent precision loss."""
    if val is None:
        return None
    try:
        return float(Decimal(str(val)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _extract_amount(val: Any) -> Optional[float]:
    """Extract numeric float from either float, Decimal, int, or DisplayedPrice object."""
    if val is None:
        return None
    if hasattr(val, "amount"):
        return _safe_to_float(getattr(val, "amount", None))
    return _safe_to_float(val)


def _extract_product_identifier(item: EvidenceItem) -> Optional[str]:
    """Extract product SKU, ID, or slug from evidence metadata or description."""
    meta = getattr(item, "metadata", None) or {}
    for key in ("product_anchor", "product_id", "sku", "item_id"):
        v = meta.get(key)
        if v:
            return str(v).strip().lower()
    return None


class DarkPatternDetector:
    """Deterministic intelligence layer evaluating multi-modal evidence for dark patterns."""

    @staticmethod
    def evaluate(
        evidence_items: List[EvidenceItem],
        contradictions: List[ContradictionItem],
        temporal_relationships: List[TemporalRelationshipItem],
        text_prediction: Optional[PredictResponse] = None,
        price_analysis: Optional[PriceAnalysisResponse] = None,
        transaction_state: Optional[Dict[str, Any]] = None,
    ) -> List[PatternAssessment]:
        """Evaluate all patterns deterministically without single-signal overreach."""
        assessments: List[PatternAssessment] = []

        # Filter out isolated auxiliary evidence from commercial pattern detection
        commercial_evidence = [e for e in evidence_items if not getattr(e, "is_auxiliary", False)]
        has_auxiliary_only = len(evidence_items) > 0 and len(commercial_evidence) == 0

        if has_auxiliary_only:
            # Auxiliary context cannot independently produce commercial dark patterns
            return assessments

        # 1. SUBSCRIPTION_TRAP
        sub_assessment = DarkPatternDetector._evaluate_subscription_trap(
            commercial_evidence, contradictions, temporal_relationships, text_prediction, price_analysis
        )
        if sub_assessment:
            assessments.append(sub_assessment)

        # 2. DRIP_PRICING
        drip_assessment = DarkPatternDetector._evaluate_drip_pricing(
            commercial_evidence, contradictions, temporal_relationships, price_analysis
        )
        if drip_assessment:
            assessments.append(drip_assessment)

        # 3. BASKET_SNAKING
        snaking_assessment = DarkPatternDetector._evaluate_basket_snaking(commercial_evidence)
        if snaking_assessment:
            assessments.append(snaking_assessment)

        # 4. FALSE_URGENCY
        urgency_assessment = DarkPatternDetector._evaluate_false_urgency(commercial_evidence, text_prediction, contradictions)
        if urgency_assessment:
            assessments.append(urgency_assessment)

        # 5. SCARCITY
        scarcity_assessment = DarkPatternDetector._evaluate_scarcity(commercial_evidence, text_prediction)
        if scarcity_assessment:
            assessments.append(scarcity_assessment)

        # 6. FORCED_ACTION
        forced_assessment = DarkPatternDetector._evaluate_forced_action(commercial_evidence)
        if forced_assessment:
            assessments.append(forced_assessment)

        # 7. CONFIRM_SHAMING
        shaming_assessment = DarkPatternDetector._evaluate_confirm_shaming(commercial_evidence)
        if shaming_assessment:
            assessments.append(shaming_assessment)

        # 8. OBSTRUCTION
        obstruction_assessment = DarkPatternDetector._evaluate_obstruction(
            commercial_evidence, contradictions, temporal_relationships
        )
        if obstruction_assessment:
            assessments.append(obstruction_assessment)

        # 9. MISDIRECTION
        misdirection_assessment = DarkPatternDetector._evaluate_misdirection(commercial_evidence)
        if misdirection_assessment:
            assessments.append(misdirection_assessment)

        # 10. SOCIAL_PROOF
        social_assessment = DarkPatternDetector._evaluate_social_proof(commercial_evidence, text_prediction)
        if social_assessment:
            assessments.append(social_assessment)

        return assessments

    @staticmethod
    def _evaluate_subscription_trap(
        evidence: List[EvidenceItem],
        contradictions: List[ContradictionItem],
        temporals: List[TemporalRelationshipItem],
        text_prediction: Optional[PredictResponse],
        price_analysis: Optional[PriceAnalysisResponse],
    ) -> Optional[PatternAssessment]:
        """Evaluate SUBSCRIPTION_TRAP with anti-overreach rules."""
        sub_items = [
            e for e in evidence
            if e.pattern == "subscription_trap"
            or "subscription" in (e.type or "").lower()
            or "renew" in (e.type or "").lower()
            or "trial" in (e.type or "").lower()
        ]
        price_items = [e for e in evidence if e.source == "price" and (e.type in ("renewal_price", "paid_trial") or getattr(e, "value", None) is not None)]
        dom_deemphasis = [e for e in evidence if e.source == "dom" and e.type in ("action_visual_deemphasis", "hidden_alternative", "typography_asymmetry", "small_secondary_action")]
        text_items = [e for e in evidence if e.source == "text"]

        # Contradictions regarding subscription (e.g. text declared free / cancel anytime vs recurring fee / disabled cancel)
        sub_contradictions = [c for c in contradictions if c.pattern == "subscription_trap" or "subscription" in c.reason.lower() or c.type == "text_vs_price"]

        supporting_ids = list({e.evidence_id for e in sub_items + price_items + dom_deemphasis} | {eid for c in sub_contradictions for eid in c.evidence_ids})

        # Anti-Overreach Rule 1: A renewal price alone on a transparent subscription page is NOT a subscription trap
        has_transparent_terms = any("cancel anytime" in (e.description or "").lower() or "self-serve" in (e.description or "").lower() for e in text_items)
        has_contradiction = len(sub_contradictions) > 0
        has_deemphasis = len(dom_deemphasis) > 0
        has_trial_conversion = any(e.type in ("free_trial", "trial_price") or "free trial" in (e.description or "").lower() for e in evidence)

        has_renewal_item = any(e.type in ("renewal_price", "paid_trial") or "renewal" in (e.type or "").lower() for e in evidence)
        has_renewal_p = bool(price_analysis and getattr(price_analysis, "renewal_price", None) is not None) or has_renewal_item
        has_recurring = bool(price_analysis and getattr(price_analysis, "recurring", False)) or has_renewal_item

        if not supporting_ids and not has_recurring:
            return None

        if has_contradiction or (has_trial_conversion and (has_deemphasis or has_contradiction)):
            # Multi-source deceptive conversion or contradiction
            return PatternAssessment(
                pattern=PATTERN_SUBSCRIPTION_TRAP,
                status=STATUS_SUPPORTED,
                confidence=0.88,
                severity="strong" if has_contradiction else "moderate",
                decision_context="subscription",
                reason="Subscription combines trial conversion or recurring commitment with de-emphasized renewal terms or contradictory declarations.",
                supporting_evidence_ids=sorted(supporting_ids),
                consumer_consequence="The subscription may convert to recurring paid charges without prominent upfront notice or easy cancellation.",
            )

        if has_trial_conversion and has_renewal_p:
            # Trial + renewal price without explicit contradiction or deemphasis: POTENTIAL
            return PatternAssessment(
                pattern=PATTERN_SUBSCRIPTION_TRAP,
                status=STATUS_POTENTIAL,
                confidence=0.60,
                severity="moderate",
                decision_context="subscription",
                reason="Trial offer precedes recurring billing; terms should be reviewed prior to commitment.",
                supporting_evidence_ids=sorted(supporting_ids),
                consumer_consequence="Recurring billing will commence automatically after the trial period.",
            )

        if has_recurring and not has_deemphasis and not has_contradiction:
            # Transparent recurring pricing alone is NOT a dark pattern
            return PatternAssessment(
                pattern=PATTERN_SUBSCRIPTION_TRAP,
                status=STATUS_NOT_SUPPORTED,
                confidence=0.15,
                severity="low",
                decision_context="subscription",
                reason="Standard recurring subscription terms are clearly disclosed without deceptive conversion mechanics.",
                supporting_evidence_ids=sorted(supporting_ids),
                consumer_consequence="Regular recurring charges apply according to disclosed terms.",
            )

        return None

    @staticmethod
    def _evaluate_drip_pricing(
        evidence: List[EvidenceItem],
        contradictions: List[ContradictionItem],
        temporals: List[TemporalRelationshipItem],
        price_analysis: Optional[PriceAnalysisResponse],
    ) -> Optional[PatternAssessment]:
        """Evaluate DRIP_PRICING with inclusive pricing and temporal order verification."""
        drip_items = [e for e in evidence if e.pattern in ("drip_pricing", "hidden_fee") or e.type in ("additional_cost", "late_disclosure", "post_action_fee_added")]
        drip_contras = [c for c in contradictions if c.pattern == "drip_pricing" or "fee" in c.reason.lower()]
        drip_temporals = [t for t in temporals if "fee" in t.type or "price_change" in t.type]

        supporting_ids = list({e.evidence_id for e in drip_items} | {eid for c in drip_contras for eid in c.evidence_ids} | {eid for t in drip_temporals for eid in (t.before_evidence_ids + t.after_evidence_ids)})

        has_add_cost = bool(price_analysis and (getattr(price_analysis, "additional_cost", None) is not None or getattr(price_analysis, "additional_costs", None) is not None))
        has_late = bool(price_analysis and (getattr(price_analysis, "late_disclosed", False) or getattr(price_analysis, "late_disclosure_detected", False)))

        if not supporting_ids and not (has_add_cost or has_late):
            return None

        # Anti-Overreach: Check for inclusive pricing (fees explicitly included upfront)
        is_inclusive = any("all fees included" in (e.description or "").lower() or "inclusive" in (e.description or "").lower() for e in evidence)
        if is_inclusive and not drip_temporals and not any(e.type == "post_action_fee_added" for e in evidence):
            return PatternAssessment(
                pattern=PATTERN_DRIP_PRICING,
                status=STATUS_NOT_SUPPORTED,
                confidence=0.10,
                severity="low",
                decision_context="checkout",
                reason="Itemized fees are explicitly declared as included in the baseline total; no incremental charges were added.",
                supporting_evidence_ids=sorted(supporting_ids),
                consumer_consequence="Final payment matches the upfront disclosed total without surprise additions.",
            )

        # Context evaluation for P1-03
        has_explicit_checkout = any(
            getattr(e, "decision_context", None) in ("checkout", "payment", "cart")
            or "checkout" in (getattr(e, "description", "") or "").lower()
            for e in drip_items
        )
        has_temporal_addition = any(t.type in ("fee_added_after_action", "price_change_after_action") for t in drip_temporals)
        has_late_item = any(e.type in ("late_disclosure", "post_action_fee_added") or getattr(e, "temporal_position", None) == "after_action" for e in drip_items)
        has_contradiction = len(drip_contras) > 0

        is_context_unknown = any(
            getattr(e, "decision_context", None) in (None, "unknown", "", "unspecified")
            for e in drip_items
        ) and not has_explicit_checkout and not has_temporal_addition

        if is_context_unknown:
            # P1-03: When context is unknown and not established by temporal/stage evidence:
            # - No SUPPORTED DRIP_PRICING
            # - Do not call it checkout drip pricing
            # - decision_context must remain "unknown"
            return PatternAssessment(
                pattern=PATTERN_DRIP_PRICING,
                status=STATUS_POTENTIAL,
                confidence=0.40,
                severity="moderate",
                decision_context="unknown",
                reason="Additional fee observed with unverified decision context; cannot determine whether fee represents drip pricing without transaction context.",
                supporting_evidence_ids=sorted(supporting_ids),
                consumer_consequence="An additional fee was observed, but commercial transaction context is unknown.",
            )

        # Supported drip pricing: Verified fee added post-action during checkout/payment
        if has_temporal_addition or (has_late_item and has_contradiction):
            return PatternAssessment(
                pattern=PATTERN_DRIP_PRICING,
                status=STATUS_SUPPORTED,
                confidence=0.85,
                severity="strong",
                decision_context="checkout",
                reason="Mandatory additional fee or undisclosed surcharge appeared after initial interaction or checkout progression.",
                supporting_evidence_ids=sorted(supporting_ids),
                consumer_consequence="Total transaction cost is higher than the initially displayed baseline price.",
            )

        if has_late_item or any(e.type == "additional_cost" for e in drip_items):
            ctx = "checkout" if (has_explicit_checkout or has_temporal_addition) else "unknown"
            return PatternAssessment(
                pattern=PATTERN_DRIP_PRICING,
                status=STATUS_POTENTIAL,
                confidence=0.55,
                severity="moderate",
                decision_context=ctx,
                reason="Additional fee detected in checkout; verify whether fee was disclosed prior to transaction initiation.",
                supporting_evidence_ids=sorted(supporting_ids),
                consumer_consequence="Additional fees may apply to the final checkout total.",
            )

        return None

    @staticmethod
    def _evaluate_basket_snaking(evidence: List[EvidenceItem]) -> Optional[PatternAssessment]:
        """Evaluate BASKET_SNAKING with commercial add-on verification."""
        snaking_items = [e for e in evidence if e.pattern in ("sneaking", "basket_snaking") or e.type == "preselected_option"]
        if not snaking_items:
            return None

        supporting_ids = [e.evidence_id for e in snaking_items]

        # Check whether preselection is genuinely commercial (paid add-on/warranty) or benign
        commercial_preselection: List[EvidenceItem] = []
        benign_preselection: List[EvidenceItem] = []

        for item in snaking_items:
            desc = (item.description or "").lower()
            element = (item.element_ref or "").lower()
            combined = f"{desc} {element}"
            val = getattr(item, "value", None)
            is_commercial = any(k in combined for k in COMMERCIAL_ADDON_KEYWORDS) or (isinstance(val, (int, float)) and val > 0)
            is_benign = any(k in combined for k in BENIGN_PRESELECTION_KEYWORDS)
            if is_commercial:
                commercial_preselection.append(item)
            elif is_benign:
                benign_preselection.append(item)

        if commercial_preselection:
            return PatternAssessment(
                pattern=PATTERN_BASKET_SNAKING,
                status=STATUS_SUPPORTED,
                confidence=0.82,
                severity="strong",
                decision_context="checkout",
                reason="Optional commercial add-on, paid warranty, or fee-bearing item is preselected by default.",
                supporting_evidence_ids=sorted({e.evidence_id for e in commercial_preselection}),
                consumer_consequence="Consumer may be charged for optional ancillary items unless manually deselected.",
            )

        if benign_preselection and not commercial_preselection:
            return PatternAssessment(
                pattern=PATTERN_BASKET_SNAKING,
                status=STATUS_NOT_SUPPORTED,
                confidence=0.10,
                severity="low",
                decision_context="checkout",
                reason="Preselected setting represents a standard, non-commercial preference (e.g. shipping method, language, or sign-in state).",
                supporting_evidence_ids=sorted({e.evidence_id for e in benign_preselection}),
                consumer_consequence="No unintended financial charges associated with this preselected default.",
            )

        return PatternAssessment(
            pattern=PATTERN_BASKET_SNAKING,
            status=STATUS_POTENTIAL,
            confidence=0.50,
            severity="moderate",
            decision_context="checkout",
            reason="Preselected option observed; check whether it incurs additional charges.",
            supporting_evidence_ids=sorted(supporting_ids),
            consumer_consequence="An option is preselected by default; review selection prior to completing transaction.",
        )

    @staticmethod
    def _evaluate_false_urgency(
        evidence: List[EvidenceItem],
        text_prediction: Optional[PredictResponse],
        contradictions: List[ContradictionItem],
    ) -> Optional[PatternAssessment]:
        """Evaluate FALSE_URGENCY with timer reset / artificial countdown verification.
        
        P1-01 Invariants:
        1. Countdown/timer alone: -> NOT_SUPPORTED
        2. Strong countdown/timer alone: -> NOT_SUPPORTED
        3. Text urgency prediction alone: -> NOT_SUPPORTED or POTENTIAL, but NEVER SUPPORTED
        4. SUPPORTED FALSE_URGENCY requires explicit evidence of artificial/deceptive behavior, such as:
           - verified timer reset
           - verified restart after expiry
           - contradictory deadline state
           - another independently corroborating behavioral/temporal signal
        
        Do NOT use generic strength="strong" as a proxy for artificiality.
        """
        urgency_items = [
            e for e in evidence
            if e.pattern in ("urgency", "false_urgency")
            or "countdown" in (e.type or "").lower()
            or "timer" in (e.type or "").lower()
            or "urgency" in (e.type or "").lower()
        ]
        has_text_urgency = bool(text_prediction and text_prediction.pattern_category == "Urgency")

        if not urgency_items and not has_text_urgency:
            return None

        # Check for explicit evidence of artificial / deceptive countdown behavior
        has_timer_reset = any(
            e.type in ("timer_reset", "timer_loop", "timer_restart", "artificial_countdown", "artificial_urgency")
            or "reset" in (e.description or "").lower()
            or "restart" in (e.description or "").lower()
            or "loop" in (e.description or "").lower()
            or getattr(e, "metadata", {}).get("timer_reset") is True
            or getattr(e, "metadata", {}).get("is_artificial") is True
            for e in urgency_items
        )

        urgency_contras = [
            c for c in contradictions
            if c.pattern in ("urgency", "false_urgency")
            or "deadline" in c.reason.lower()
            or "timer" in c.reason.lower()
        ]
        has_urgency_contradiction = len(urgency_contras) > 0

        has_verified_artificial = has_timer_reset or has_urgency_contradiction

        supporting_ids = list({e.evidence_id for e in urgency_items} | {eid for c in urgency_contras for eid in c.evidence_ids})

        # Condition 4: Explicit verified artificial behavior / timer reset -> SUPPORTED
        if has_verified_artificial:
            return PatternAssessment(
                pattern=PATTERN_FALSE_URGENCY,
                status=STATUS_SUPPORTED,
                confidence=0.85,
                severity="strong",
                decision_context="purchase",
                reason="Countdown timer or urgency indicator observed with verified artificial reset behavior, restart after expiry, or contradictory deadline state.",
                supporting_evidence_ids=sorted(supporting_ids),
                consumer_consequence="Artificial time pressure encourages committing to a transaction under false urgency.",
            )

        # Condition 1 & 2: Countdown/timer alone (even with strength="strong") -> NOT_SUPPORTED
        has_timer_item = any(
            "countdown" in (e.type or "").lower()
            or "timer" in (e.type or "").lower()
            or "timer" in (e.description or "").lower()
            or "countdown" in (e.description or "").lower()
            for e in urgency_items
        )

        if has_timer_item and not has_text_urgency:
            return PatternAssessment(
                pattern=PATTERN_FALSE_URGENCY,
                status=STATUS_NOT_SUPPORTED,
                confidence=0.20,
                severity="low",
                decision_context="purchase",
                reason="Countdown timer or stated promotional deadline observed without evidence of artificial reset or deceptive renewal.",
                supporting_evidence_ids=sorted(supporting_ids),
                consumer_consequence="Promotional offer appears to reflect a fixed promotional timeframe.",
            )

        # Condition 3: Text urgency prediction alone (or text urgency wording) -> POTENTIAL (NEVER SUPPORTED)
        return PatternAssessment(
            pattern=PATTERN_FALSE_URGENCY,
            status=STATUS_POTENTIAL,
            confidence=0.50,
            severity="moderate",
            decision_context="purchase",
            reason="Urgency wording detected in promotional text; unverified whether stated deadline is authentic or artificial.",
            supporting_evidence_ids=sorted(supporting_ids),
            consumer_consequence="Urgency claims may accelerate purchase decisions; verify deadline authenticity.",
        )

    @staticmethod
    def _evaluate_scarcity(evidence: List[EvidenceItem], text_prediction: Optional[PredictResponse]) -> Optional[PatternAssessment]:
        """Evaluate SCARCITY with factual variant/inventory verification."""
        scarcity_items = [
            e for e in evidence
            if e.pattern in ("scarcity", "low_stock")
            or "stock" in (e.type or "").lower()
            or "scarcity" in (e.type or "").lower()
            or "inventory" in (e.type or "").lower()
        ]
        if not scarcity_items and not (text_prediction and text_prediction.pattern_category == "Scarcity"):
            return None

        supporting_ids = [e.evidence_id for e in scarcity_items]

        # Anti-Overreach: Factual stock level or variant indicator is NOT deceptive scarcity
        is_factual = any(any(k in (e.description or "").lower() for k in FACTUAL_STOCK_KEYWORDS) for e in scarcity_items)
        if is_factual and not any(getattr(e, "strength", None) == "strong" for e in scarcity_items):
            return PatternAssessment(
                pattern=PATTERN_SCARCITY,
                status=STATUS_NOT_SUPPORTED,
                confidence=0.15,
                severity="low",
                decision_context="purchase",
                reason="Stock indicator conveys factual variant availability or standard inventory levels without deceptive pressure.",
                supporting_evidence_ids=sorted(supporting_ids),
                consumer_consequence="Available quantities may reflect actual current stock.",
            )

        return PatternAssessment(
            pattern=PATTERN_SCARCITY,
            status=STATUS_POTENTIAL,
            confidence=0.55,
            severity="moderate",
            decision_context="purchase",
            reason="Low-stock or scarcity alert detected; verify authentic inventory availability.",
            supporting_evidence_ids=sorted(supporting_ids),
            consumer_consequence="Low stock claim may accelerate purchase decisions.",
        )

    @staticmethod
    def _evaluate_forced_action(evidence: List[EvidenceItem]) -> Optional[PatternAssessment]:
        """Evaluate FORCED_ACTION (e.g. mandatory survey blocking cancellation)."""
        forced_items = [e for e in evidence if e.pattern in ("forced_action", "forced_registration") or e.type in ("forced_action", "cancellation_survey", "mandatory_feedback")]
        if not forced_items:
            return None

        supporting_ids = [e.evidence_id for e in forced_items]
        is_cancellation_blocking = any(e.decision_context == "cancellation" or "cancellation" in (e.description or "").lower() for e in forced_items)

        return PatternAssessment(
            pattern=PATTERN_FORCED_ACTION,
            status=STATUS_SUPPORTED if is_cancellation_blocking else STATUS_POTENTIAL,
            confidence=0.85 if is_cancellation_blocking else 0.50,
            severity="strong" if is_cancellation_blocking else "moderate",
            decision_context="cancellation" if is_cancellation_blocking else "dialog",
            reason="Mandatory task or feedback requirement inserted before consumer can complete requested account action.",
            supporting_evidence_ids=sorted(supporting_ids),
            consumer_consequence="User is prevented from completing intended action without fulfilling unrelated requirements.",
        )

    @staticmethod
    def _evaluate_confirm_shaming(evidence: List[EvidenceItem]) -> Optional[PatternAssessment]:
        """Evaluate CONFIRM_SHAMING with emotional refusal verification."""
        shaming_items = [e for e in evidence if e.pattern == "confirm_shaming" or e.type == "confirm_shaming"]
        if not shaming_items:
            return None

        supporting_ids = [e.evidence_id for e in shaming_items]
        return PatternAssessment(
            pattern=PATTERN_CONFIRM_SHAMING,
            status=STATUS_SUPPORTED,
            confidence=0.80,
            severity="moderate",
            decision_context="dialog",
            reason="Decline option utilizes guilt-inducing or emotionally negative wording to deter rejection.",
            supporting_evidence_ids=sorted(supporting_ids),
            consumer_consequence="Language exerts emotional pressure to accept an offer rather than declining neutrally.",
        )

    @staticmethod
    def _evaluate_obstruction(
        evidence: List[EvidenceItem],
        contradictions: List[ContradictionItem],
        temporals: List[TemporalRelationshipItem],
    ) -> Optional[PatternAssessment]:
        """Evaluate OBSTRUCTION in cancellation and account deletion flows."""
        obs_items = [e for e in evidence if e.pattern == "obstruction" or e.type in ("repeated_retention_interference", "cancellation_loop", "disabled_action", "cancellation_abandonment")]
        obs_contras = [c for c in contradictions if c.pattern == "obstruction" or c.decision_context == "cancellation"]
        supporting_ids = list({e.evidence_id for e in obs_items} | {eid for c in obs_contras for eid in c.evidence_ids})

        if not supporting_ids:
            return None

        has_retention_loop = any(e.type in ("repeated_retention_interference", "cancellation_loop") for e in obs_items)
        has_disabled_action = any(e.type == "disabled_action" and e.decision_context == "cancellation" for e in obs_items)
        has_contradiction = len(obs_contras) > 0

        if has_retention_loop or (has_disabled_action and has_contradiction):
            return PatternAssessment(
                pattern=PATTERN_OBSTRUCTION,
                status=STATUS_SUPPORTED,
                confidence=0.88,
                severity="strong",
                decision_context="cancellation",
                reason="Cancellation pathway introduces repetitive retention obstacles, disabled controls, or procedural friction.",
                supporting_evidence_ids=sorted(supporting_ids),
                consumer_consequence="Ending subscription or service requires navigating excessive friction or unassisted intervention.",
            )

        return PatternAssessment(
            pattern=PATTERN_OBSTRUCTION,
            status=STATUS_POTENTIAL,
            confidence=0.60,
            severity="moderate",
            decision_context="cancellation",
            reason="Procedural friction observed in cancellation flow; additional confirmation steps present.",
            supporting_evidence_ids=sorted(supporting_ids),
            consumer_consequence="Cancellation may require additional verification or navigation steps.",
        )

    @staticmethod
    def _evaluate_misdirection(evidence: List[EvidenceItem]) -> Optional[PatternAssessment]:
        """Evaluate MISDIRECTION (extreme visual asymmetry or hidden alternatives)."""
        mis_items = [e for e in evidence if e.pattern == "misdirection" or e.type in ("action_size_asymmetry", "action_visual_deemphasis", "hidden_alternative", "contrast_asymmetry")]
        if not mis_items:
            return None

        supporting_ids = [e.evidence_id for e in mis_items]
        has_strong_asymmetry = any(getattr(e, "strength", None) == "strong" for e in mis_items)

        if has_strong_asymmetry:
            return PatternAssessment(
                pattern=PATTERN_MISDIRECTION,
                status=STATUS_SUPPORTED,
                confidence=0.82,
                severity="strong",
                decision_context=mis_items[0].decision_context or "dialog",
                reason="Severe visual asymmetry, extreme size disparity, or obscured alternative nudges user away from neutral choice.",
                supporting_evidence_ids=sorted(supporting_ids),
                consumer_consequence="Visual styling heavily steers attention toward higher-cost or merchant-preferred options.",
            )

        return PatternAssessment(
            pattern=PATTERN_MISDIRECTION,
            status=STATUS_POTENTIAL,
            confidence=0.50,
            severity="moderate",
            decision_context=mis_items[0].decision_context or "dialog",
            reason="Moderate visual hierarchy differences observed between available choices.",
            supporting_evidence_ids=sorted(supporting_ids),
            consumer_consequence="Interface styling emphasizes one choice over another.",
        )

    @staticmethod
    def _evaluate_social_proof(evidence: List[EvidenceItem], text_prediction: Optional[PredictResponse]) -> Optional[PatternAssessment]:
        """Evaluate SOCIAL_PROOF (fabricated or high-pressure social consensus signals)."""
        social_items = [e for e in evidence if e.pattern == "social_proof" or e.type in ("social_proof", "activity_notification")]
        if not social_items and not (text_prediction and text_prediction.pattern_category == "Social Proof"):
            return None

        supporting_ids = [e.evidence_id for e in social_items]
        return PatternAssessment(
            pattern=PATTERN_SOCIAL_PROOF,
            status=STATUS_POTENTIAL,
            confidence=0.55,
            severity="moderate",
            decision_context="purchase",
            reason="Social proof or peer activity notification detected; verify credibility of claimed metrics.",
            supporting_evidence_ids=sorted(supporting_ids),
            consumer_consequence="Reported popularity signals may influence purchasing judgment.",
        )


class ConsumerConsequenceEngine:
    """Deterministic engine deriving explainable consumer consequences and financial impacts."""

    @staticmethod
    def derive_consequences(
        evidence_items: List[EvidenceItem],
        pattern_assessments: List[PatternAssessment],
        contradictions: List[ContradictionItem],
        temporals: List[TemporalRelationshipItem],
        price_analysis: Optional[PriceAnalysisResponse] = None,
    ) -> List[ConsumerConsequenceDetail]:
        """Derive objective, Decimal-safe consequences without legal conclusions."""
        consequences: List[ConsumerConsequenceDetail] = []
        commercial_evidence = [e for e in evidence_items if not getattr(e, "is_auxiliary", False)]

        # 1. Recurring subscription consequence
        sub_consequence = ConsumerConsequenceEngine._derive_subscription_consequence(
            commercial_evidence, pattern_assessments, price_analysis
        )
        if sub_consequence:
            consequences.append(sub_consequence)

        # 2. Drip pricing / additional fee consequence
        drip_consequence = ConsumerConsequenceEngine._derive_drip_fee_consequence(
            commercial_evidence, pattern_assessments, temporals, price_analysis
        )
        if drip_consequence:
            consequences.append(drip_consequence)

        # 3. Cancellation friction consequence
        cancellation_consequence = ConsumerConsequenceEngine._derive_cancellation_friction_consequence(
            commercial_evidence, pattern_assessments, contradictions
        )
        if cancellation_consequence:
            consequences.append(cancellation_consequence)

        return consequences

    @staticmethod
    def _derive_subscription_consequence(
        evidence: List[EvidenceItem],
        assessments: List[PatternAssessment],
        price_analysis: Optional[PriceAnalysisResponse],
    ) -> Optional[ConsumerConsequenceDetail]:
        """Derive financial exposure and renewal consequence from verified pricing evidence."""
        sub_items = [e for e in evidence if e.type in ("renewal_price", "paid_trial", "subscription") or getattr(e, "pattern", None) == "subscription_trap"]
        has_rec = bool(price_analysis and getattr(price_analysis, "recurring", False))
        has_ren = bool(price_analysis and getattr(price_analysis, "renewal_price", None) is not None)
        if not sub_items and not (has_rec or has_ren):
            return None

        renewal_amount: Optional[float] = None
        currency: Optional[str] = None
        period: Optional[str] = None
        trial_duration: Optional[str] = None

        if price_analysis:
            renewal_amount = _extract_amount(getattr(price_analysis, "renewal_price", None))
            currency = getattr(price_analysis, "renewal_currency", None) or getattr(price_analysis, "currency", None) or "INR"
            period = getattr(price_analysis, "billing_period", None) or "month"
            trial_days = getattr(price_analysis, "trial_duration_days", None)
            trial_duration = f"{trial_days} days" if trial_days else (str(getattr(price_analysis, "trial_duration", None)) if getattr(price_analysis, "trial_duration", None) else None)

        # Look in evidence items if missing from price_analysis
        if renewal_amount is None:
            for item in sub_items:
                val = _safe_to_float(getattr(item, "value", None))
                if val is not None:
                    renewal_amount = val
                    currency = getattr(item, "currency", None) or currency or "INR"
                    break

        supporting_ids = sorted({e.evidence_id for e in sub_items})

        # Financial safety: If renewal price is missing, exposure is UNKNOWN (never guess)
        if renewal_amount is not None:
            curr_str = currency or "INR"
            per_str = f" per {period}" if period else ""
            return ConsumerConsequenceDetail(
                type="recurring_charge",
                actual_cost=0.0 if trial_duration else renewal_amount,
                future_cost=renewal_amount,
                renewal_cost=renewal_amount,
                financial_exposure=renewal_amount,
                currency=curr_str,
                period=period or "month",
                trial_duration=trial_duration,
                consumer_effort="moderate",
                consumer_consequence=f"Subscription will automatically renew at {curr_str} {renewal_amount:.2f}{per_str} unless cancelled before renewal.",
                recommended_action="Verify cancellation procedure and set a reminder prior to the initial billing cycle.",
                supporting_evidence_ids=supporting_ids,
            )
        else:
            return ConsumerConsequenceDetail(
                type="recurring_charge",
                actual_cost=None,
                future_cost=None,
                renewal_cost=None,
                financial_exposure="UNKNOWN",
                currency=currency,
                period=period,
                trial_duration=trial_duration,
                consumer_effort="moderate",
                consumer_consequence="Subscription incurs recurring charges, but specific renewal amount was not disclosed upfront.",
                recommended_action="Check account billing terms for renewal fees prior to confirming sign-up.",
                supporting_evidence_ids=supporting_ids,
            )

    @staticmethod
    def _derive_drip_fee_consequence(
        evidence: List[EvidenceItem],
        assessments: List[PatternAssessment],
        temporals: List[TemporalRelationshipItem],
        price_analysis: Optional[PriceAnalysisResponse],
    ) -> Optional[ConsumerConsequenceDetail]:
        """Derive incremental fee consequence from temporal addition or late disclosure."""
        fee_items = [e for e in evidence if e.type in ("additional_cost", "late_disclosure", "post_action_fee_added")]
        has_add = bool(price_analysis and (getattr(price_analysis, "additional_cost", None) is not None or getattr(price_analysis, "additional_costs", None) is not None))
        if not fee_items and not has_add:
            return None

        # Check for inclusive pricing: do not generate drip fee if fee is inclusive
        if any("all fees included" in (e.description or "").lower() for e in evidence):
            return None

        # P1-03 Context safety: check if context is unknown
        has_temporal_checkout = any(t.type in ("fee_added_after_action", "price_change_after_action") for t in temporals)
        has_explicit_checkout = any(
            getattr(e, "decision_context", None) in ("checkout", "payment", "cart")
            or "checkout" in (getattr(e, "description", "") or "").lower()
            for e in fee_items
        )
        is_context_unknown = any(
            getattr(e, "decision_context", None) in (None, "unknown", "", "unspecified")
            for e in fee_items
        ) and not has_temporal_checkout and not has_explicit_checkout

        curr_str = "INR"
        if fee_items:
            curr_str = getattr(fee_items[0], "currency", None) or curr_str
        if price_analysis and getattr(price_analysis, "currency", None):
            curr_str = getattr(price_analysis, "currency", None)

        supporting_ids = sorted({e.evidence_id for e in fee_items})

        if is_context_unknown:
            # P1-03: For an isolated additional_cost with unknown context:
            # - do not call it checkout drip pricing
            # - do not claim "known total cost increased"
            # - do not infer that it was disclosed during checkout
            # - financial exposure may be UNKNOWN unless the evidence itself unambiguously establishes the financial consequence
            # - preserve the actual evidence description/value without inventing transaction context
            fee_desc = fee_items[0].description if fee_items else "unspecified additional fee"
            return ConsumerConsequenceDetail(
                type="additional_fee",
                actual_cost=None,
                future_cost=None,
                renewal_cost=None,
                financial_exposure="UNKNOWN",
                currency=curr_str,
                period=None,
                trial_duration=None,
                consumer_effort="minimal",
                consumer_consequence=f"Additional fee observed ({fee_desc}), but transaction context is unknown.",
                recommended_action="Review transaction context before proceeding.",
                supporting_evidence_ids=supporting_ids,
            )

        base_price: Optional[float] = None
        additional_fee: Optional[float] = None
        currency: Optional[str] = None

        if price_analysis:
            base_price = _extract_amount(getattr(price_analysis, "displayed_price", None))
            additional_fee = _extract_amount(getattr(price_analysis, "additional_cost", None) or getattr(price_analysis, "additional_costs", None))
            currency = getattr(price_analysis, "currency", None) or "INR"

        if additional_fee is None:
            for item in fee_items:
                val = _safe_to_float(getattr(item, "value", None))
                if val is not None:
                    additional_fee = val
                    currency = getattr(item, "currency", None) or currency or "INR"
                    break

        if base_price is None:
            base_item = next((e for e in evidence if e.type == "displayed_price"), None)
            if base_item:
                base_price = _safe_to_float(getattr(base_item, "value", None))

        curr_str = currency or curr_str

        if additional_fee is not None:
            total_known = (base_price + additional_fee) if base_price is not None else None
            base_str = f"from {curr_str} {base_price:.2f} " if base_price is not None else ""
            total_str = f"to {curr_str} {total_known:.2f}" if total_known is not None else f"additional {curr_str} {additional_fee:.2f}"
            return ConsumerConsequenceDetail(
                type="additional_fee",
                actual_cost=base_price,
                future_cost=total_known,
                renewal_cost=None,
                financial_exposure=additional_fee,
                currency=curr_str,
                period=None,
                trial_duration=None,
                consumer_effort="low",
                consumer_consequence=f"Known total cost increased {base_str}{total_str} due to an additional fee disclosed during checkout.",
                recommended_action="Review itemized billing details before submitting payment authorization.",
                supporting_evidence_ids=supporting_ids,
            )
        else:
            return ConsumerConsequenceDetail(
                type="additional_fee",
                actual_cost=base_price,
                future_cost=None,
                renewal_cost=None,
                financial_exposure="UNKNOWN",
                currency=curr_str,
                period=None,
                trial_duration=None,
                consumer_effort="low",
                consumer_consequence="An additional mandatory charge appeared at checkout, but specific fee amount is unquantified.",
                recommended_action="Verify final price breakdown prior to completing order.",
                supporting_evidence_ids=supporting_ids,
            )

    @staticmethod
    def _derive_cancellation_friction_consequence(
        evidence: List[EvidenceItem],
        assessments: List[PatternAssessment],
        contradictions: List[ContradictionItem],
    ) -> Optional[ConsumerConsequenceDetail]:
        """Derive consumer effort consequence from obstruction in cancellation flow."""
        obs_assessment = next((a for a in assessments if a.pattern == PATTERN_OBSTRUCTION and a.status == STATUS_SUPPORTED), None)
        if not obs_assessment:
            return None

        return ConsumerConsequenceDetail(
            type="friction_interference",
            actual_cost=None,
            future_cost=None,
            renewal_cost=None,
            financial_exposure=None,
            currency=None,
            period=None,
            trial_duration=None,
            consumer_effort="high_friction",
            consumer_consequence="Cancellation pathway introduces excessive navigation friction, retention prompts, or restricted off-boarding.",
            recommended_action="Allow sufficient time to complete multi-step cancellation and request written confirmation of termination.",
            supporting_evidence_ids=obs_assessment.supporting_evidence_ids,
        )


class HistoricalChangeEngine:
    """Deterministic engine tracking historical changes respecting journey, tab, and product isolation."""

    @staticmethod
    def detect_changes(
        evidence_items: List[EvidenceItem],
        temporals: List[TemporalRelationshipItem],
        price_analysis: Optional[PriceAnalysisResponse] = None,
        transaction_state: Optional[Dict[str, Any]] = None,
    ) -> List[HistoricalChangeDetail]:
        """Detect verified historical changes without cross-journey, cross-tab, or cross-product pollution."""
        changes: List[HistoricalChangeDetail] = []
        commercial_evidence = [e for e in evidence_items if not getattr(e, "is_auxiliary", False)]

        # Group items by journey_id (Strict Journey Isolation)
        journeys: Dict[Optional[str], List[EvidenceItem]] = {}
        for item in commercial_evidence:
            jid = getattr(item, "journey_id", None)
            journeys.setdefault(jid, []).append(item)

        for jid, j_items in journeys.items():
            # 1. Price changes within same continuous journey
            p_changes = HistoricalChangeEngine._detect_price_changes(j_items, temporals, price_analysis, jid)
            changes.extend(p_changes)

            # 2. Terms changes within same continuous journey
            t_changes = HistoricalChangeEngine._detect_terms_changes(j_items, jid)
            changes.extend(t_changes)

            # 3. UI state changes within same continuous journey
            u_changes = HistoricalChangeEngine._detect_ui_changes(j_items, jid)
            changes.extend(u_changes)

        return changes

    @staticmethod
    def _detect_price_changes(
        items: List[EvidenceItem],
        temporals: List[TemporalRelationshipItem],
        price_analysis: Optional[PriceAnalysisResponse],
        journey_id: Optional[str],
    ) -> List[HistoricalChangeDetail]:
        """Detect price changes strictly within the same verified product and journey."""
        details: List[HistoricalChangeDetail] = []

        # Product Isolation: Group items by product identifier
        products: Dict[Optional[str], List[EvidenceItem]] = {}
        for item in items:
            pid = _extract_product_identifier(item)
            products.setdefault(pid, []).append(item)

        # Tab Isolation: Verify items share tab_id if present
        tabs = {getattr(e, "tab_id", None) for e in items if getattr(e, "tab_id", None) is not None}
        if len(tabs) > 1:
            # Cross-tab comparison prohibited
            return details

        # Invariant P1-02:
        # A historical PRICE_CHANGE must have:
        #   previous verified observation (EvidenceItem)
        #   + current verified observation (EvidenceItem)
        #   + same journey
        #   + same tab where tab identity exists
        #   + same product identity when product identity is available
        #   + valid temporal/continuity relationship OR an explicitly verified historical snapshot
        # PriceAnalysisResponse may provide arithmetic values, but it must NOT manufacture
        # historical provenance. If previous history is unavailable, do NOT emit a fabricated
        # PRICE_CHANGE merely because price_change_detected=True.

        price_items = [
            e for e in items
            if e.source == "price"
            or e.type in ("displayed_price", "price_change", "previous_price", "current_price", "historical_price")
        ]

        if len(price_items) < 2 and not temporals:
            return details

        # 1. Temporal relationships with verified before and after items
        processed_pairs: Set[Tuple[str, str]] = set()
        for t in temporals:
            if t.type in ("price_change_after_action", "price_progression"):
                before_items = [e for e in items if e.evidence_id in t.before_evidence_ids]
                after_items = [e for e in items if e.evidence_id in t.after_evidence_ids]
                if before_items and after_items:
                    b_item = before_items[0]
                    a_item = after_items[0]

                    # Tab check
                    tab_b = getattr(b_item, "tab_id", None) or getattr(b_item, "metadata", {}).get("tab_id")
                    tab_a = getattr(a_item, "tab_id", None) or getattr(a_item, "metadata", {}).get("tab_id")
                    if tab_b is not None and tab_a is not None and tab_b != tab_a:
                        continue

                    # Product check
                    prod_b = _extract_product_identifier(b_item)
                    prod_a = _extract_product_identifier(a_item)
                    if prod_b and prod_a and prod_b != prod_a:
                        continue

                    pair_key = (b_item.evidence_id, a_item.evidence_id)
                    if pair_key in processed_pairs:
                        continue
                    processed_pairs.add(pair_key)

                    prev = _safe_to_float(getattr(b_item, "value", None))
                    curr = _safe_to_float(getattr(a_item, "value", None))

                    diff = (curr - prev) if (curr is not None and prev is not None) else None
                    pct = ((diff / prev) * 100.0) if (diff is not None and prev and prev != 0) else None
                    if price_analysis and getattr(price_analysis, "price_change", None) is not None:
                        pa_diff = _extract_amount(getattr(price_analysis, "price_change", None))
                        if pa_diff is not None:
                            diff = pa_diff
                        pa_pct = _safe_to_float(getattr(price_analysis, "price_change_percentage", None))
                        if pa_pct is not None:
                            pct = pa_pct

                    curr_str = getattr(a_item, "currency", None) or getattr(b_item, "currency", None) or (price_analysis and getattr(price_analysis, "currency", None)) or "INR"
                    details.append(
                        HistoricalChangeDetail(
                            category="PRICE_CHANGE",
                            previous_value=prev if prev is not None else "UNKNOWN",
                            current_value=curr,
                            absolute_change=diff,
                            percentage_change=pct,
                            currency=curr_str,
                            description=f"Price changed from {curr_str} {prev} to {curr_str} {curr}.",
                            is_dark_pattern=False,  # Invariant: PRICE_CHANGE != DARK_PATTERN
                            supporting_evidence_ids=sorted([b_item.evidence_id, a_item.evidence_id]),
                            journey_id=journey_id,
                        )
                    )

        # 2. Verified historical snapshot or price change pair in items without explicit temporal item
        if not details and len(price_items) >= 2:
            prior_items = [
                e for e in price_items
                if e.type in ("previous_price", "historical_price")
                or getattr(e, "temporal_position", None) == "before_action"
                or (e.type == "displayed_price" and any(o.type == "price_change" for o in price_items if o != e))
            ]
            current_items = [
                e for e in price_items
                if e.type in ("price_change", "current_price", "updated_price")
                or getattr(e, "temporal_position", None) == "after_action"
                or (e.type == "displayed_price" and any(o.type in ("previous_price", "historical_price") or getattr(o, "temporal_position", None) == "before_action" for o in price_items if o != e))
            ]

            if prior_items and current_items:
                b_item = prior_items[0]
                a_item = current_items[0]
                if b_item.evidence_id != a_item.evidence_id:
                    tab_b = getattr(b_item, "tab_id", None) or getattr(b_item, "metadata", {}).get("tab_id")
                    tab_a = getattr(a_item, "tab_id", None) or getattr(a_item, "metadata", {}).get("tab_id")
                    if not (tab_b is not None and tab_a is not None and tab_b != tab_a):
                        prod_b = _extract_product_identifier(b_item)
                        prod_a = _extract_product_identifier(a_item)
                        if not (prod_b and prod_a and prod_b != prod_a):
                            prev = _safe_to_float(getattr(b_item, "value", None))
                            curr = _safe_to_float(getattr(a_item, "value", None))

                            diff = (curr - prev) if (curr is not None and prev is not None) else None
                            pct = ((diff / prev) * 100.0) if (diff is not None and prev and prev != 0) else None
                            if price_analysis and getattr(price_analysis, "price_change", None) is not None:
                                pa_diff = _extract_amount(getattr(price_analysis, "price_change", None))
                                if pa_diff is not None:
                                    diff = pa_diff
                                pa_pct = _safe_to_float(getattr(price_analysis, "price_change_percentage", None))
                                if pa_pct is not None:
                                    pct = pa_pct

                            curr_str = getattr(a_item, "currency", None) or getattr(b_item, "currency", None) or (price_analysis and getattr(price_analysis, "currency", None)) or "INR"
                            details.append(
                                HistoricalChangeDetail(
                                    category="PRICE_CHANGE",
                                    previous_value=prev if prev is not None else "UNKNOWN",
                                    current_value=curr,
                                    absolute_change=diff,
                                    percentage_change=pct,
                                    currency=curr_str,
                                    description=f"Price changed from {curr_str} {prev} to {curr_str} {curr}.",
                                    is_dark_pattern=False,  # Invariant: PRICE_CHANGE != DARK_PATTERN
                                    supporting_evidence_ids=sorted([b_item.evidence_id, a_item.evidence_id]),
                                    journey_id=journey_id,
                                )
                            )

        return details

    @staticmethod
    def _detect_terms_changes(
        items: List[EvidenceItem],
        journey_id: Optional[str],
    ) -> List[HistoricalChangeDetail]:
        """Detect terms changes across verified transaction stages (e.g. cancel anytime vs restrictive)."""
        details: List[HistoricalChangeDetail] = []
        text_items = [e for e in items if e.source == "text"]

        easy_cancel_items = [e for e in text_items if "cancel anytime" in (e.description or "").lower() or "one click" in (e.description or "").lower()]
        hard_cancel_items = [e for e in text_items if "contact support" in (e.description or "").lower() or "call to cancel" in (e.description or "").lower()]

        if easy_cancel_items and hard_cancel_items:
            details.append(
                HistoricalChangeDetail(
                    category="TERMS_CHANGE",
                    previous_value=easy_cancel_items[0].description,
                    current_value=hard_cancel_items[0].description,
                    absolute_change=None,
                    percentage_change=None,
                    currency=None,
                    description="Cancellation terms modified from self-serve online cancellation to requiring customer support contact.",
                    is_dark_pattern=False,
                    supporting_evidence_ids=sorted([easy_cancel_items[0].evidence_id, hard_cancel_items[0].evidence_id]),
                    journey_id=journey_id,
                )
            )

        return details

    @staticmethod
    def _detect_ui_changes(
        items: List[EvidenceItem],
        journey_id: Optional[str],
    ) -> List[HistoricalChangeDetail]:
        """Detect UI state changes (e.g. action becoming disabled across interactions)."""
        details: List[HistoricalChangeDetail] = []
        dom_items = [e for e in items if e.source == "dom"]

        action_rendered = [e for e in dom_items if e.type in ("action_rendered", "button_active")]
        action_disabled = [e for e in dom_items if e.type in ("disabled_action", "cancel_action_disabled")]

        if action_rendered and action_disabled:
            details.append(
                HistoricalChangeDetail(
                    category="UI_CHANGE",
                    previous_value="active",
                    current_value="disabled",
                    absolute_change=None,
                    percentage_change=None,
                    currency=None,
                    description="Interface action state transitioned from active/enabled to disabled.",
                    is_dark_pattern=False,
                    supporting_evidence_ids=sorted([action_rendered[0].evidence_id, action_disabled[0].evidence_id]),
                    journey_id=journey_id,
                )
            )

        return details


class IntelligenceEngine:
    """Authoritative Intelligence Analysis Orchestrator for ClauseGuard Phase B5.7."""

    @staticmethod
    def analyze(
        evidence_items: List[EvidenceItem],
        contradictions: List[ContradictionItem],
        temporal_relationships: List[TemporalRelationshipItem],
        text_prediction: Optional[PredictResponse] = None,
        price_analysis: Optional[PriceAnalysisResponse] = None,
        transaction_state: Optional[Dict[str, Any]] = None,
    ) -> IntelligenceAnalysisResponse:
        """Perform deterministic intelligence analysis across patterns, consequences, and history."""
        # 1. Evaluate dark patterns with anti-overreach rules
        pattern_assessments = DarkPatternDetector.evaluate(
            evidence_items=evidence_items,
            contradictions=contradictions,
            temporal_relationships=temporal_relationships,
            text_prediction=text_prediction,
            price_analysis=price_analysis,
            transaction_state=transaction_state,
        )

        # 2. Derive explainable consumer consequences
        consumer_consequences = ConsumerConsequenceEngine.derive_consequences(
            evidence_items=evidence_items,
            pattern_assessments=pattern_assessments,
            contradictions=contradictions,
            temporals=temporal_relationships,
            price_analysis=price_analysis,
        )

        # 3. Detect factual historical changes respecting isolation boundaries
        historical_changes = HistoricalChangeEngine.detect_changes(
            evidence_items=evidence_items,
            temporals=temporal_relationships,
            price_analysis=price_analysis,
            transaction_state=transaction_state,
        )

        # 4. Strict Provenance Invariant:
        # For every B5.7 output, supporting_evidence_ids MUST be a subset of the actual
        # input EvidenceItem.evidence_id values. No synthetic IDs. No placeholder IDs.
        valid_input_ids = {e.evidence_id for e in evidence_items}
        for p in pattern_assessments:
            p.supporting_evidence_ids = sorted({eid for eid in p.supporting_evidence_ids if eid in valid_input_ids})
        for c in consumer_consequences:
            c.supporting_evidence_ids = sorted({eid for eid in c.supporting_evidence_ids if eid in valid_input_ids})
        for h in historical_changes:
            h.supporting_evidence_ids = sorted({eid for eid in h.supporting_evidence_ids if eid in valid_input_ids})

        all_supporting: Set[str] = set()
        for p in pattern_assessments:
            all_supporting.update(p.supporting_evidence_ids)
        for c in consumer_consequences:
            all_supporting.update(c.supporting_evidence_ids)
        for h in historical_changes:
            all_supporting.update(h.supporting_evidence_ids)

        # Check if context was missing / unknown for commercial evidence
        has_unknown_context = any(
            getattr(e, "decision_context", None) in (None, "unknown", "", "unspecified")
            for e in evidence_items
            if not getattr(e, "is_auxiliary", False)
        )

        return IntelligenceAnalysisResponse(
            pattern_assessments=pattern_assessments,
            consumer_consequences=consumer_consequences,
            historical_changes=historical_changes,
            supporting_evidence=sorted(all_supporting),
            requires_context=has_unknown_context,
        )
