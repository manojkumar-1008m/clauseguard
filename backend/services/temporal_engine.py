"""backend/services/temporal_engine.py
Phase B5.3 Deterministic Temporal Evidence Engine for Multi-Modal Interactions.

Models before/after state transitions across user interactions:
- Price Change After Action (e.g. ₹499 -> Continue -> ₹578)
- Fee Added After Action (e.g. ₹499 -> Continue -> ₹499 + ₹79 processing fee)
- Option Added After Action (e.g. unselected -> Continue -> commercial add-on preselected)
- Action Disabled After Action (e.g. cancel enabled -> interact -> cancel disabled)
- Alternative Removed After Action (e.g. Reject available -> interact -> only Accept remains)
- Modal Appeared After Action (e.g. normal flow -> cancel click -> retention modal)
- Required Step Appeared After Action (e.g. normal flow -> cancel click -> required survey wall)

Guarantees:
- Strict event order verification (timestamp -> event_indices -> temporal_position).
- Context boundaries respected (incompatible contexts or unrelated routes never form temporal relationships).
- Conservative categorical relevance (immediate interaction -> same flow -> same session).
- Factual and explainable description without premature legal conclusions.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from ..schemas.evidence import EvidenceItem, TemporalRelationshipItem, CONTEXT_FAMILY_MAP
from ..schemas.price import PriceAnalysisResponse
from .journey_engine import JourneyEngine

_logger = logging.getLogger("clauseguard_backend.temporal_engine")


def _get_context_family(context: Optional[str]) -> str:
    if not context:
        return "unknown_family"
    return CONTEXT_FAMILY_MAP.get(str(context).strip().lower(), "unknown_family")


def _are_contexts_compatible(ctx_a: Optional[str], ctx_b: Optional[str]) -> bool:
    """Check if two contexts belong to the same compatible decision family."""
    fam_a = _get_context_family(ctx_a)
    fam_b = _get_context_family(ctx_b)
    if fam_a == "unknown_family" or fam_b == "unknown_family":
        return False
    return fam_a == fam_b


def _are_routes_compatible(route_a: Optional[str], route_b: Optional[str]) -> bool:
    """Check if two routes represent the same page or sequential flow step."""
    if not route_a or not route_b:
        return True
    r_a = route_a.strip().lower()
    r_b = route_b.strip().lower()
    if r_a == r_b:
        return True
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


def _check_temporal_boundary_compatibility(item_a: EvidenceItem, item_b: EvidenceItem) -> bool:
    """Ensure temporal boundary rules (Phase B5.4).
    
    Requirements:
    - If either is auxiliary: False (auxiliary evidence cannot participate in temporal relationships)
    - If both have journey_id:
        - Must have identical journey_id (no cross-journey temporal relationship)
        - Must have valid journey stage transition (e.g. PRODUCT -> PRODUCT is catalog browsing, not price change)
    - Product anchor check: if both items have product_anchor metadata and they differ, return False.
    - Check session, context, and route compatibility.
    """
    if getattr(item_a, "is_auxiliary", False) or getattr(item_b, "is_auxiliary", False):
        return False

    j_a = getattr(item_a, "journey_id", None)
    j_b = getattr(item_b, "journey_id", None)
    is_continuous_flow = False
    if j_a is not None and j_b is not None:
        if j_a != j_b:
            return False
        stage_a = getattr(item_a, "journey_stage", None)
        stage_b = getattr(item_b, "journey_stage", None)
        trans_class = JourneyEngine.classify_stage_transition(stage_a, stage_b)
        if trans_class == "IMPOSSIBLE":
            return False
        if not JourneyEngine.is_valid_stage_transition(stage_a, stage_b) and trans_class != "UNEXPECTED":
            return False
        if JourneyEngine.context_transition_is_allowed(item_a.decision_context, item_b.decision_context):
            is_continuous_flow = True

    # Product anchor check (Part 10 & 11)
    meta_a = item_a.metadata or {}
    meta_b = item_b.metadata or {}
    prod_a = meta_a.get("product_anchor") or meta_a.get("product_id") or meta_a.get("sku")
    prod_b = meta_b.get("product_anchor") or meta_b.get("product_id") or meta_b.get("sku")
    if prod_a and prod_b and str(prod_a).strip().lower() != str(prod_b).strip().lower():
        return False

    if not _check_session_compatibility(item_a, item_b):
        return False

    # B5.6: Check context compatibility (permit directed context transitions in verified journeys)
    if not is_continuous_flow and not _are_contexts_compatible(item_a.decision_context, item_b.decision_context):
        return False

    # B5.6: Cross-page temporal bridge (relax route prefix requirement ONLY for verified continuous journeys)
    if not is_continuous_flow and not _are_routes_compatible(item_a.route, item_b.route):
        return False

    return True


def _determine_temporal_order(
    item_before: EvidenceItem,
    item_after: EvidenceItem,
) -> Optional[str]:
    """Verify strictly whether item_before precedes item_after.

    Preferred ordering hierarchy:
    1. Timestamps (if present)
    2. Event indices (if present)
    3. Categorical temporal_position ('before_action' -> 'after_action')
    """
    if not _check_temporal_boundary_compatibility(item_before, item_after):
        return None

    meta_before = item_before.metadata or {}
    meta_after = item_after.metadata or {}

    ts_before = meta_before.get("timestamp")
    ts_after = meta_after.get("timestamp")
    if ts_before is not None and ts_after is not None:
        if ts_before < ts_after:
            return "timestamp_ordered"
        return None  # Out of order

    idx_before = item_before.event_indices or []
    idx_after = item_after.event_indices or []
    if idx_before and idx_after:
        if max(idx_before) < min(idx_after):
            return "event_index_ordered"
        return None

    pos_before = item_before.temporal_position
    pos_after = item_after.temporal_position
    if pos_before in ("before_action", "static") and pos_after == "after_action":
        return "position_ordered"

    return None


class TemporalEngine:
    """Deterministic before/after interaction and state-change modeling engine."""

    def detect_temporal_relationships(
        self,
        evidence_items: List[EvidenceItem],
        price_analysis: Optional[PriceAnalysisResponse] = None,
    ) -> List[TemporalRelationshipItem]:
        """Detect and structure before/after temporal state changes."""
        if not evidence_items and not price_analysis:
            return []

        relationships: List[TemporalRelationshipItem] = []
        counter = 1

        def next_tid() -> str:
            nonlocal counter
            tid = f"T{counter:03d}"
            counter += 1
            return tid

        # Segregate candidate before and after items
        before_items = [
            e for e in evidence_items
            if e.temporal_position in ("before_action", "static")
        ]
        after_items = [
            e for e in evidence_items
            if e.temporal_position in ("after_action", "session_dynamic")
        ]

        # -----------------------------------------------------------------
        # 1. PRICE_CHANGE_AFTER_ACTION / FEE_ADDED_AFTER_ACTION
        # -----------------------------------------------------------------
        # Check price analysis for explicit previous vs current price
        if price_analysis and (price_analysis.price_change_detected or price_analysis.price_changed or price_analysis.price_change is not None):
            if price_analysis.previous_price is not None and price_analysis.current_price is not None:
                p_diff = price_analysis.price_change
                if p_diff is not None and p_diff > 0:
                    before_item = next((e for e in before_items if e.source == "price" and e.type == "displayed_price"), None)
                    after_item = next((e for e in after_items if e.source == "price" and e.type == "price_change"), None)
                    is_compatible = True
                    if before_item and after_item:
                        is_compatible = _check_temporal_boundary_compatibility(before_item, after_item)
                    elif (before_item and getattr(before_item, "is_auxiliary", False)) or (after_item and getattr(after_item, "is_auxiliary", False)):
                        is_compatible = False

                    if is_compatible:
                        before_id = before_item.evidence_id if before_item else "E_PRICE_BEFORE"
                        after_id = after_item.evidence_id if after_item else "E_PRICE_AFTER"
                        relationships.append(
                            TemporalRelationshipItem(
                                temporal_id=next_tid(),
                                type="price_change_after_action",
                                before_evidence_ids=[before_id],
                                after_evidence_ids=[after_id],
                                decision_context="checkout",
                                strength="strong",
                                reason=f"The price increased from {price_analysis.previous_price} to {price_analysis.current_price} after the user interaction.",
                            )
                        )

        # Check DOM or Price post-action fee added
        post_fee_items = [
            e for e in after_items
            if e.type in ("post_action_fee_added", "additional_cost") and (
                e.temporal_position == "after_action" or (price_analysis and price_analysis.late_disclosed)
            )
        ]
        base_price_items = [
            e for e in before_items
            if e.type in ("displayed_price", "initial_price") or (e.source == "price" and e.type != "additional_cost")
        ]
        for fee in post_fee_items:
            matching_base = next((
                b for b in base_price_items
                if _check_temporal_boundary_compatibility(b, fee)
            ), None)
            if matching_base:
                order = _determine_temporal_order(matching_base, fee)
                if order:
                    relationships.append(
                        TemporalRelationshipItem(
                            temporal_id=next_tid(),
                            type="fee_added_after_action",
                            before_evidence_ids=[matching_base.evidence_id],
                            after_evidence_ids=[fee.evidence_id],
                            event_indices=(matching_base.event_indices or []) + (fee.event_indices or []),
                            route=fee.route or matching_base.route,
                            decision_context=fee.decision_context or matching_base.decision_context or "checkout",
                            strength="strong",
                            reason="An additional fee appeared after the user continued through the flow.",
                        )
                    )

        # -----------------------------------------------------------------
        # 3. OPTION_ADDED_AFTER_ACTION
        # -----------------------------------------------------------------
        post_option_items = [
            e for e in after_items
            if e.type in ("preselected_option", "preselected_commercial_choice") or (
                e.pattern == "sneaking" and e.temporal_position == "after_action"
            )
        ]
        for opt in post_option_items:
            matching_before = next((
                b for b in before_items
                if _check_temporal_boundary_compatibility(b, opt)
                and b.type not in ("preselected_option", "preselected_commercial_choice")
            ), None)
            if matching_before:
                order = _determine_temporal_order(matching_before, opt)
                if order:
                    relationships.append(
                        TemporalRelationshipItem(
                            temporal_id=next_tid(),
                            type="option_added_after_action",
                            before_evidence_ids=[matching_before.evidence_id],
                            after_evidence_ids=[opt.evidence_id],
                            event_indices=(matching_before.event_indices or []) + (opt.event_indices or []),
                            route=opt.route,
                            decision_context=opt.decision_context or "checkout",
                            strength="strong",
                            reason="A preselected commercial add-on or option was introduced after user navigation.",
                        )
                    )

        # -----------------------------------------------------------------
        # 4. ACTION_DISABLED_AFTER_ACTION
        # -----------------------------------------------------------------
        post_disabled_items = [
            e for e in after_items
            if e.type in ("cancel_action_disabled", "disabled_action") or (
                e.metadata and e.metadata.get("disabled") is True and e.temporal_position == "after_action"
            )
        ]
        for dis in post_disabled_items:
            matching_enabled = next((
                b for b in before_items
                if _check_temporal_boundary_compatibility(b, dis)
                and b.type not in ("cancel_action_disabled", "disabled_action")
                and (not b.metadata or not b.metadata.get("disabled"))
            ), None)
            if matching_enabled:
                order = _determine_temporal_order(matching_enabled, dis)
                if order:
                    relationships.append(
                        TemporalRelationshipItem(
                            temporal_id=next_tid(),
                            type="action_disabled_after_action",
                            before_evidence_ids=[matching_enabled.evidence_id],
                            after_evidence_ids=[dis.evidence_id],
                            event_indices=(matching_enabled.event_indices or []) + (dis.event_indices or []),
                            route=dis.route,
                            decision_context=dis.decision_context or "cancellation",
                            strength="strong",
                            reason="Cancellation or modification action was disabled after the user clicked or interacted.",
                        )
                    )

        # -----------------------------------------------------------------
        # 5. ALTERNATIVE_REMOVED_AFTER_ACTION
        # -----------------------------------------------------------------
        post_removed_items = [
            e for e in after_items
            if e.type in ("hidden_alternative", "hidden_action", "visibility_mismatch")
        ]
        for rem in post_removed_items:
            matching_before = next((
                b for b in before_items
                if _check_temporal_boundary_compatibility(b, rem)
                and b.type not in ("hidden_alternative", "hidden_action")
            ), None)
            if matching_before:
                order = _determine_temporal_order(matching_before, rem)
                if order:
                    relationships.append(
                        TemporalRelationshipItem(
                            temporal_id=next_tid(),
                            type="alternative_removed_after_action",
                            before_evidence_ids=[matching_before.evidence_id],
                            after_evidence_ids=[rem.evidence_id],
                            event_indices=(matching_before.event_indices or []) + (rem.event_indices or []),
                            route=rem.route,
                            decision_context=rem.decision_context or "cancellation",
                            strength="strong",
                            reason="An alternative choice (e.g. Reject / Decline) was removed or hidden after user progression.",
                        )
                    )

        # -----------------------------------------------------------------
        # 6. MODAL_APPEARED_AFTER_ACTION
        # -----------------------------------------------------------------
        post_modal_items = [
            e for e in after_items
            if e.type in ("modal_interference", "repeated_retention_interference", "confirmation_ui")
            or "modal" in (e.description or "").lower()
        ]
        for mod in post_modal_items:
            matching_before = next((
                b for b in before_items
                if _check_temporal_boundary_compatibility(b, mod)
                and b.type not in ("modal_interference", "repeated_retention_interference")
            ), None)
            if matching_before:
                order = _determine_temporal_order(matching_before, mod)
                if order:
                    relationships.append(
                        TemporalRelationshipItem(
                            temporal_id=next_tid(),
                            type="modal_appeared_after_action",
                            before_evidence_ids=[matching_before.evidence_id],
                            after_evidence_ids=[mod.evidence_id],
                            event_indices=(matching_before.event_indices or []) + (mod.event_indices or []),
                            route=mod.route,
                            decision_context=mod.decision_context or "cancellation",
                            strength="strong",
                            reason="A retention or upsell modal interrupted the flow following user action.",
                        )
                    )

        # -----------------------------------------------------------------
        # 7. REQUIRED_STEP_APPEARED_AFTER_ACTION
        # -----------------------------------------------------------------
        post_step_items = [
            e for e in after_items
            if e.type in ("required_survey", "survey_wall_friction", "forced_action_sequence")
        ]
        for step in post_step_items:
            matching_before = next((
                b for b in before_items
                if _check_temporal_boundary_compatibility(b, step)
                and b.type not in ("required_survey", "survey_wall_friction")
            ), None)
            if matching_before:
                order = _determine_temporal_order(matching_before, step)
                if order:
                    relationships.append(
                        TemporalRelationshipItem(
                            temporal_id=next_tid(),
                            type="required_step_appeared_after_action",
                            before_evidence_ids=[matching_before.evidence_id],
                            after_evidence_ids=[step.evidence_id],
                            event_indices=(matching_before.event_indices or []) + (step.event_indices or []),
                            route=step.route,
                            decision_context=step.decision_context or "cancellation",
                            strength="strong",
                            reason="A mandatory survey wall or sequential obstacle appeared after proceeding.",
                        )
                    )

        return relationships
