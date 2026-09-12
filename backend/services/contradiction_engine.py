"""backend/services/contradiction_engine.py
Phase B5.3 Deterministic Contradiction Engine for Multi-Modal Evidence.

Detects semantic incompatibility between observable sources:
- Text vs DOM (e.g. text declares easy cancellation vs DOM disabled/deemphasized action)
- Text vs Behavior (e.g. text declares one-click cancel vs repeated retention prompts)
- Text vs Price (e.g. text declares all fees included vs additional fee detected)
- Price Before vs After (e.g. financial state changed after user action)
- DOM vs Behavior (e.g. DOM cancel appears available vs behavior dead-ends/abandonment)
- Image vs Text (e.g. text normal urgency vs image countdown timer)

Guarantees:
- Semantic incompatibility required (corroborating facts like ₹999 text + ₹999 price are NOT contradictions).
- Context and route boundaries strictly respected (unrelated pages/contexts never contradict).
- Bounded risk escalation (max 2.0 total contradiction contribution).
- No fabricated ML probabilities.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from ..schemas import PredictResponse
from ..schemas.evidence import ContradictionItem, EvidenceGroup, EvidenceItem, CONTEXT_FAMILY_MAP
from ..schemas.price import PriceAnalysisResponse
from .journey_engine import JourneyEngine

_logger = logging.getLogger("clauseguard_backend.contradiction_engine")

MAX_CONTRADICTION_SCORE_CONTRIBUTION: float = 2.0

CONTRADICTION_SEVERITY_WEIGHTS: Dict[str, float] = {
    "weak": 0.5,
    "moderate": 1.0,
    "strong": 1.5,
}

# Explicit declaration keywords for easy cancellation
EASY_CANCEL_KEYWORDS: Tuple[str, ...] = (
    "cancel anytime",
    "cancel easily",
    "easy to cancel",
    "cancel in one click",
    "one-click cancel",
    "one click cancel",
    "cancel with one click",
    "cancel without penalty",
    "no commitment",
    "cancel online anytime",
    "instant cancel",
    "instant cancellation",
    "simple cancel",
    "simple cancellation",
)

# Explicit declaration keywords for fee inclusion
ALL_FEES_INCLUDED_KEYWORDS: Tuple[str, ...] = (
    "all fees included",
    "no hidden fees",
    "no hidden costs",
    "all-inclusive",
    "inclusive of all taxes",
    "no extra charges",
    "no additional fees",
    "zero hidden fees",
    "no surprise fees",
)

# Explicit declaration keywords for one-time payment
ONE_TIME_PAYMENT_KEYWORDS: Tuple[str, ...] = (
    "one-time payment",
    "single payment",
    "no recurring charge",
    "one time fee",
    "one-time charge",
    "pay once",
    "no subscription",
)

# Explicit declaration keywords for free offer
FREE_OFFER_KEYWORDS: Tuple[str, ...] = (
    "100% free",
    "completely free",
    "free trial without commitment",
    "always free",
    "no cost ever",
)

# Explicit declaration keywords for opt-out availability
OPT_OUT_AVAILABLE_KEYWORDS: Tuple[str, ...] = (
    "opt-out anytime",
    "opt-out available",
    "you can opt out",
    "reject anytime",
    "decline anytime",
    "opt out at any time",
)


def _get_context_family(context: Optional[str]) -> str:
    if not context:
        return "unknown_family"
    return CONTEXT_FAMILY_MAP.get(str(context).strip().lower(), "unknown_family")


def _are_contexts_compatible(ctx_a: Optional[str], ctx_b: Optional[str]) -> bool:
    """Check if two contexts belong to the same compatible decision family."""
    if not ctx_a or not ctx_b:
        return True
    fam_a = _get_context_family(ctx_a)
    fam_b = _get_context_family(ctx_b)
    if fam_a == "unknown_family" or fam_b == "unknown_family":
        # Unknown contexts do not automatically correlate or contradict unless routes match
        return False
    return fam_a == fam_b


def _are_routes_compatible(route_a: Optional[str], route_b: Optional[str]) -> bool:
    """Check if two routes represent the same page or related step."""
    if not route_a or not route_b:
        return True  # Route not specified, defer to context
    r_a = route_a.strip().lower()
    r_b = route_b.strip().lower()
    if r_a == r_b:
        return True
    # Sub-paths or query variations within same base
    base_a = r_a.split("?")[0].rstrip("/")
    base_b = r_b.split("?")[0].rstrip("/")
    return base_a == base_b or base_a.startswith(base_b) or base_b.startswith(base_a)


def _check_session_compatibility(item_a: EvidenceItem, item_b: EvidenceItem) -> bool:
    """Ensure two items do not originate from explicitly different sessions."""
    meta_a = item_a.metadata or {}
    meta_b = item_b.metadata or {}
    sess_a = meta_a.get("session_id")
    sess_b = meta_b.get("session_id")
    if sess_a and sess_b and sess_a != sess_b:
        return False
    return True


def _check_boundary_compatibility(item_a: EvidenceItem, item_b: EvidenceItem) -> bool:
    """Check boundary compatibility with B5.4 journey gating and B5.1-B5.3 fallback.

    Rules:
    - Auxiliary evidence items NEVER participate in commercial contradictions (Part 12).
    - If both items have journey_id, they MUST match (Part 18).
    - If either lacks journey_id, fallback to legacy B5.1-B5.3 context, route, and session checks.
    """
    if getattr(item_a, "is_auxiliary", False) or getattr(item_b, "is_auxiliary", False):
        return False

    j_a = getattr(item_a, "journey_id", None)
    j_b = getattr(item_b, "journey_id", None)
    if j_a is not None and j_b is not None:
        if j_a != j_b:
            return False
        stage_a = getattr(item_a, "journey_stage", None)
        stage_b = getattr(item_b, "journey_stage", None)
        trans_class = JourneyEngine.classify_stage_transition(stage_a, stage_b)
        if trans_class == "IMPOSSIBLE":
            return False
        if trans_class in ("VALID", "UNEXPECTED") and JourneyEngine.context_transition_is_allowed(item_a.decision_context, item_b.decision_context):
            return True
        return _are_contexts_compatible(item_a.decision_context, item_b.decision_context)

    # Legacy fallback
    if not _check_session_compatibility(item_a, item_b):
        return False
    if not _are_contexts_compatible(item_a.decision_context, item_b.decision_context):
        return False
    if not _are_routes_compatible(item_a.route, item_b.route):
        return False
    return True


class ContradictionEngine:
    """Deterministic contradiction detector and risk escalator."""

    def detect_contradictions(
        self,
        evidence_items: List[EvidenceItem],
        raw_text: Optional[str] = None,
        text_prediction: Optional[PredictResponse] = None,
        price_analysis: Optional[PriceAnalysisResponse] = None,
    ) -> List[ContradictionItem]:
        """Evaluate evidence items for semantic contradictions across sources."""
        if not evidence_items and not raw_text and not text_prediction and not price_analysis:
            return []

        contradictions: List[ContradictionItem] = []
        counter = 1

        def next_cid() -> str:
            nonlocal counter
            cid = f"C{counter:03d}"
            counter += 1
            return cid

        text_items = [e for e in evidence_items if e.source == "text"]
        dom_items = [e for e in evidence_items if e.source == "dom" and e.detected]
        beh_items = [e for e in evidence_items if e.source == "behavior" and e.detected]
        price_items = [e for e in evidence_items if e.source == "price" and e.detected]
        image_items = [e for e in evidence_items if e.source == "image" and e.detected]

        full_text = " ".join(filter(None, [
            raw_text or "",
            text_prediction.evidence if text_prediction else "",
            *(e.description or "" for e in text_items)
        ])).lower()

        # -----------------------------------------------------------------
        # 1. TEXT_DECLARATION_VS_DOM_STATE
        # -----------------------------------------------------------------
        has_easy_cancel_claim = any(k in full_text for k in EASY_CANCEL_KEYWORDS)
        has_opt_out_claim = any(k in full_text for k in OPT_OUT_AVAILABLE_KEYWORDS)

        for dom in dom_items:
            # Check for loading exception: legitimate temporary disable
            dom_reason = (dom.description or "").lower()
            dom_meta = dom.metadata or {}
            is_loading = "loading" in dom_reason or dom_meta.get("is_loading") or dom_meta.get("state") == "loading"
            if is_loading:
                continue

            # Auxiliary evidence never participates in commercial contradiction (Part 12)
            if getattr(dom, "is_auxiliary", False):
                continue
            if text_items and not _check_boundary_compatibility(text_items[0], dom):
                continue

            # Text easy cancel vs DOM cancel disabled / deemphasized / hidden
            if has_easy_cancel_claim:
                is_cancel_context = (
                    _get_context_family(dom.decision_context) == "cancellation_family"
                    or any(k in (dom.route or "").lower() for k in ("cancel", "unsubscribe"))
                    or "cancel" in (dom.type or "").lower()
                )
                if is_cancel_context:
                    is_disabled = dom.type in ("cancel_action_disabled", "disabled_action") or dom_meta.get("disabled") is True
                    is_deemphasized = dom.type in ("cancel_action_visually_deemphasized", "action_visual_deemphasis", "hidden_action", "covered_action")
                    if is_disabled or is_deemphasized:
                        text_id = text_items[0].evidence_id if text_items else "E_TEXT"
                        contradictions.append(
                            ContradictionItem(
                                contradiction_id=next_cid(),
                                type="text_vs_dom",
                                source_a="text",
                                source_b="dom",
                                pattern="obstruction",
                                severity="strong" if is_disabled or dom.strength == "strong" else "moderate",
                                reason="Text declared easy cancellation ('Cancel anytime'), but DOM displays cancel button as disabled or visually de-emphasized.",
                                evidence_ids=[text_id, dom.evidence_id],
                                event_indices=dom.event_indices,
                                route=dom.route,
                                decision_context="cancellation",
                            )
                        )
                        break

            # Text opt-out claim vs DOM hidden opt-out
            if has_opt_out_claim:
                if dom.type in ("hidden_alternative", "hidden_action", "visibility_mismatch"):
                    text_id = text_items[0].evidence_id if text_items else "E_TEXT"
                    contradictions.append(
                        ContradictionItem(
                            contradiction_id=next_cid(),
                            type="text_vs_dom",
                            source_a="text",
                            source_b="dom",
                            pattern="obstruction",
                            severity="strong" if dom.strength == "strong" else "moderate",
                            reason="Text declared opt-out choice is available, but DOM hides or removes the opt-out alternative.",
                            evidence_ids=[text_id, dom.evidence_id],
                            event_indices=dom.event_indices,
                            route=dom.route,
                            decision_context=dom.decision_context or "cancellation",
                        )
                    )
                    break

        # -----------------------------------------------------------------
        # 2. TEXT_DECLARATION_VS_BEHAVIOR
        # -----------------------------------------------------------------
        has_one_click_claim = any(k in full_text for k in ("one click", "one-click", "instant cancel", "simple cancel"))
        if has_one_click_claim:
            for beh in beh_items:
                if getattr(beh, "is_auxiliary", False):
                    continue
                if text_items and not _check_boundary_compatibility(text_items[0], beh):
                    continue

                is_cancel_beh = (
                    _get_context_family(beh.decision_context) == "cancellation_family"
                    or any(k in (beh.route or "").lower() for k in ("cancel", "unsubscribe"))
                )
                if is_cancel_beh:
                    num_steps = len(beh.event_indices) if beh.event_indices else 0
                    has_friction = (
                        num_steps >= 3
                        or beh.type in (
                            "repeated_retention_interference", "cancellation_obstruction",
                            "backtracking_loop", "dead_end_behavior", "forced_delay", "required_survey"
                        )
                    )
                    if has_friction:
                        text_id = text_items[0].evidence_id if text_items else "E_TEXT"
                        contradictions.append(
                            ContradictionItem(
                                contradiction_id=next_cid(),
                                type="text_vs_behavior",
                                source_a="text",
                                source_b="behavior",
                                pattern="obstruction",
                                severity="strong" if beh.strength == "strong" else "moderate",
                                reason="Text declared one-click or instant cancellation, but interaction sequence required multiple cancellation steps or encountered retention friction.",
                                evidence_ids=[text_id, beh.evidence_id],
                                event_indices=beh.event_indices,
                                route=beh.route,
                                decision_context="cancellation",
                            )
                        )
                        break

        # -----------------------------------------------------------------
        # 3. TEXT_VS_PRICE
        # -----------------------------------------------------------------
        has_all_fees_included = any(k in full_text for k in ALL_FEES_INCLUDED_KEYWORDS)
        has_one_time_payment = any(k in full_text for k in ONE_TIME_PAYMENT_KEYWORDS)
        has_free_offer = any(k in full_text for k in FREE_OFFER_KEYWORDS) or (
            raw_text and "free trial" in raw_text.lower() and not ("renew" in raw_text.lower() or "month" in raw_text.lower())
        )

        # Contradiction: all fees included vs additional fee / late fee detected
        if has_all_fees_included:
            fee_item = next((
                e for e in price_items
                if e.type in ("additional_cost", "late_disclosure", "post_action_fee_added")
                and (e.value is not None or e.type == "late_disclosure")
                and not getattr(e, "is_auxiliary", False)
                and (not text_items or _check_boundary_compatibility(text_items[0], e))
            ), None)
            if not fee_item and price_analysis and (price_analysis.additional_cost or price_analysis.additional_costs or price_analysis.late_disclosed):
                fee_item = next((
                    e for e in price_items
                    if e.type in ("additional_cost", "late_disclosure")
                    and not getattr(e, "is_auxiliary", False)
                    and (not text_items or _check_boundary_compatibility(text_items[0], e))
                ), None)

            if fee_item:
                text_id = text_items[0].evidence_id if text_items else "E_TEXT"
                contradictions.append(
                    ContradictionItem(
                        contradiction_id=next_cid(),
                        type="text_vs_price",
                        source_a="text",
                        source_b="price",
                        pattern="drip_pricing",
                        severity="strong",
                        reason="Text declared all fees and taxes included, but pricing analyzer detected an additional or undisclosed fee.",
                        evidence_ids=[text_id, fee_item.evidence_id],
                        decision_context="checkout",
                    )
                )
            else:
                # Also check DOM fee additions (e.g. post_action_fee_added)
                dom_fee_item = next((
                    e for e in dom_items
                    if (
                        e.type in ("post_action_fee_added", "fee_added", "additional_fee", "surprise_fee")
                        or (e.temporal_position == "after_action" and "fee" in (e.type or "").lower())
                    )
                    and not getattr(e, "is_auxiliary", False)
                    and (not text_items or _check_boundary_compatibility(text_items[0], e))
                ), None)
                if dom_fee_item:
                    text_id = text_items[0].evidence_id if text_items else "E_TEXT"
                    contradictions.append(
                        ContradictionItem(
                            contradiction_id=next_cid(),
                            type="text_vs_dom",
                            source_a="text",
                            source_b="dom",
                            pattern="drip_pricing",
                            severity="strong",
                            reason="Text declared all fees included, but post-action fee or unexpected charge appeared in DOM.",
                            evidence_ids=[text_id, dom_fee_item.evidence_id],
                            decision_context=dom_fee_item.decision_context or "checkout",
                            route=dom_fee_item.route,
                        )
                    )

        # Contradiction: one-time payment vs recurring renewal
        if has_one_time_payment:
            renewal_item = next((
                e for e in price_items
                if e.type == "renewal_price"
                and not getattr(e, "is_auxiliary", False)
                and (not text_items or _check_boundary_compatibility(text_items[0], e))
            ), None)
            if not renewal_item and price_analysis and (price_analysis.recurring or price_analysis.renewal_price):
                renewal_item = next((
                    e for e in price_items
                    if e.type == "renewal_price"
                    and not getattr(e, "is_auxiliary", False)
                    and (not text_items or _check_boundary_compatibility(text_items[0], e))
                ), None)

            if renewal_item:
                text_id = text_items[0].evidence_id if text_items else "E_TEXT"
                contradictions.append(
                    ContradictionItem(
                        contradiction_id=next_cid(),
                        type="text_vs_price",
                        source_a="text",
                        source_b="price",
                        pattern="subscription_trap",
                        severity="strong",
                        reason="Text stated a single one-time payment, but pricing analysis detected an ongoing recurring renewal structure.",
                        evidence_ids=[text_id, renewal_item.evidence_id],
                        decision_context="subscription",
                    )
                )

        # Contradiction: free claim vs paid trial or mandatory paid renewal / fee
        if has_free_offer:
            paid_trial_item = next((
                e for e in price_items
                if e.type in ("paid_trial", "additional_cost")
                and not getattr(e, "is_auxiliary", False)
                and (not text_items or _check_boundary_compatibility(text_items[0], e))
            ), None)
            if paid_trial_item:
                text_id = text_items[0].evidence_id if text_items else "E_TEXT"
                is_sub = paid_trial_item.type == "paid_trial"
                contradictions.append(
                    ContradictionItem(
                        contradiction_id=next_cid(),
                        type="text_vs_price",
                        source_a="text",
                        source_b="price",
                        pattern="subscription_trap" if is_sub else "drip_pricing",
                        severity="strong",
                        reason="Text declared offer is free, but pricing analysis identified an explicit paid trial cost." if is_sub else "Text declared offer is free, but an additional mandatory charge was detected.",
                        evidence_ids=[text_id, paid_trial_item.evidence_id],
                        decision_context="subscription" if is_sub else "checkout",
                    )
                )

        # -----------------------------------------------------------------
        # 4. PRICE_BEFORE_VS_AFTER
        # -----------------------------------------------------------------
        # Inspect post-action price changes or late fee additions within the same flow
        if price_analysis and (price_analysis.price_change_detected or price_analysis.price_changed or price_analysis.price_change is not None):
            p_diff = price_analysis.price_change
            if p_diff is not None and p_diff > 0:
                # Disclosed price increase after user interaction
                p_items = [e for e in price_items if e.type in ("price_change", "displayed_price")]
                # Journey boundary check: If price items belong to different journeys, do not contradict
                p_journeys = {getattr(e, "journey_id", None) for e in p_items if getattr(e, "journey_id", None) is not None}
                p_aux = any(getattr(e, "is_auxiliary", False) for e in p_items)
                if len(p_journeys) <= 1 and not p_aux:
                    e_ids = [e.evidence_id for e in p_items] if p_items else ["E_PRICE"]
                    has_late_or_dark = (
                        price_analysis.late_disclosed
                        or price_analysis.late_disclosure_detected
                        or any(e.pattern in ("drip_pricing", "hidden_fee") for e in evidence_items)
                    )
                    contradictions.append(
                        ContradictionItem(
                            contradiction_id=next_cid(),
                            type="price_before_vs_after",
                            source_a="price",
                            source_b="price",
                            pattern="drip_pricing" if has_late_or_dark else None,
                            severity="strong" if has_late_or_dark else "moderate",
                            reason=f"Price changed from {price_analysis.previous_price} to {price_analysis.current_price} after user interaction.",
                            evidence_ids=e_ids,
                            decision_context="checkout",
                        )
                    )

        # -----------------------------------------------------------------
        # 5. DOM_VS_BEHAVIOR
        # -----------------------------------------------------------------
        # DOM shows cancel action appears available, but behavior encounters dead-ends or abandonment
        for beh in beh_items:
            if beh.type in ("cancellation_obstruction", "cancellation_abandonment", "dead_end_behavior", "backtracking_loop"):
                matching_dom = next((
                    d for d in dom_items
                    if _check_boundary_compatibility(d, beh)
                    and d.type not in ("cancel_action_disabled", "disabled_action")
                ), None)
                if matching_dom:
                    contradictions.append(
                        ContradictionItem(
                            contradiction_id=next_cid(),
                            type="dom_vs_behavior",
                            source_a="dom",
                            source_b="behavior",
                            pattern="obstruction",
                            severity="strong" if beh.strength == "strong" else "moderate",
                            reason="Cancellation action appears available in DOM, but interaction sequence resulted in dead-ends, loops, or abandonment.",
                            evidence_ids=[matching_dom.evidence_id, beh.evidence_id],
                            event_indices=beh.event_indices,
                            route=beh.route,
                            decision_context=beh.decision_context or "cancellation",
                        )
                    )
                    break

        # -----------------------------------------------------------------
        # 6. IMAGE_VS_TEXT (Future-Compatible Visual Evidence)
        # -----------------------------------------------------------------
        artificial_urgency_types = {
            "timer_reset",
            "timer_loop",
            "timer_restart",
            "artificial_countdown",
            "artificial_urgency",
        }
        has_explicit_artificial_urgency = any(
            item.type in artificial_urgency_types
            or "reset" in (item.description or "").lower()
            or "restart" in (item.description or "").lower()
            or "loop" in (item.description or "").lower()
            or (item.metadata or {}).get("timer_reset") is True
            or (item.metadata or {}).get("is_artificial") is True
            for item in evidence_items
            if item.detected
        ) or any(
            contradiction.pattern in ("urgency", "false_urgency")
            or "deadline" in contradiction.reason.lower()
            or "timer" in contradiction.reason.lower()
            for contradiction in contradictions
        )

        for img in image_items:
            if getattr(img, "is_auxiliary", False):
                continue
            if text_items and not _check_boundary_compatibility(text_items[0], img):
                continue

            if img.type in ("countdown_timer", "fake_countdown_structure", "urgency_banner"):
                # If text does not claim urgency or pressure
                text_has_urgency = any(
                    "urgency" in (e.pattern or "") or "scarcity" in (e.pattern or "") or "hurry" in (e.description or "").lower()
                    for e in text_items
                ) or (raw_text and any(k in raw_text.lower() for k in ("hurry", "countdown", "expires soon", "limited time")))
                if not text_has_urgency and has_explicit_artificial_urgency:
                    text_id = text_items[0].evidence_id if text_items else "E_TEXT"
                    contradictions.append(
                        ContradictionItem(
                            contradiction_id=next_cid(),
                            type="image_vs_text",
                            source_a="image",
                            source_b="text",
                            pattern="urgency",
                            severity="moderate",
                            reason="Text conveys normal non-urgent communication, but visual image analyzer detected a countdown timer or pressure element.",
                            evidence_ids=[img.evidence_id, text_id],
                            route=img.route,
                            decision_context=img.decision_context or "purchase",
                        )
                    )
                    break

        return contradictions

    def compute_contradiction_escalation(
        self,
        contradictions: List[ContradictionItem],
        evidence_groups: List[EvidenceGroup],
    ) -> float:
        """Calculate bounded contradiction score escalation (Part H).

        - Weak contradiction: +0.5
        - Moderate contradiction: +1.0
        - Strong contradiction: +1.5
        - Maximum total contribution: +2.0
        - If contradiction is already fully represented in a corroborated group,
          apply an anti-double-counting discount.
        """
        if not contradictions:
            return 0.0

        total_escalation = 0.0
        corroborated_patterns = {g.pattern for g in evidence_groups if g.corroborated}

        for c in contradictions:
            weight = CONTRADICTION_SEVERITY_WEIGHTS.get(c.severity, 1.0)
            # Anti-double-counting: if the underlying pattern is already corroborated,
            # apply conservative damping (+0.5) instead of full +1.5
            if c.pattern in corroborated_patterns:
                weight = min(0.5, weight)
            total_escalation += weight

        return min(MAX_CONTRADICTION_SCORE_CONTRIBUTION, total_escalation)
