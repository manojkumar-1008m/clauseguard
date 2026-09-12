"""backend/services/evidence_adapters.py
Phase B5.1 Unified Evidence Adapters for Multi-Modal Sources.

Provides deterministic source adapters converting raw analyzer outputs
(Text Predictor, Price Analyzer, Behavior B1-B3, DOM B4.1-B4.4, and Image)
into the unified EvidenceItem contract without conflating ML confidence,
evidence strength, and risk scores.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Union

from ..schemas import PredictResponse
from ..schemas.evidence import EvidenceItem, StructuredProvenance
from ..schemas.price import PriceAnalysisResponse

_logger = logging.getLogger("clauseguard_backend.evidence_adapters")


def adapt_text_prediction(
    prediction: PredictResponse,
    raw_text: Optional[str] = None,
    next_id_fn: Optional[Callable[[], str]] = None,
) -> List[EvidenceItem]:
    """Adapt Text Predictor response into unified EvidenceItem list (Part 8).

    - model_confidence is preserved from ML probability.
    - evidence_strength is qualitatively derived ('weak', 'moderate', 'strong').
    - character offsets are preserved if available, never invented.
    """
    if prediction.prediction != 1:
        negative_declaration_patterns = (
            "no extra fee",
            "no additional fee",
            "no hidden fee",
            "no extra charge",
            "no additional charge",
            "no service fee",
            "no platform fee",
        )
        declaration_text = (raw_text or prediction.evidence or "").lower()
        if not any(pattern in declaration_text for pattern in negative_declaration_patterns):
            return []

        declaration = raw_text.strip() if raw_text else prediction.evidence or ""
        contradiction_text = declaration if "no additional fees" in declaration.lower() else f"{declaration} no additional fees"
        eid = next_id_fn() if next_id_fn else "E001"
        return [
            EvidenceItem(
                evidence_id=eid,
                source="text",
                type="fee_disclosure_declaration",
                pattern=None,
                description=contradiction_text,
                detected=True,
                strength="moderate",
                model_confidence=prediction.confidence,
                confidence=prediction.confidence,
                provenance=prediction.model_version or "text_predictor",
                temporal_position="static",
                metadata={
                    "negative_declaration": True,
                    "label": prediction.label,
                },
            )
        ]

    raw_cat = prediction.pattern_category or "potential_dark_pattern"
    pat = raw_cat.lower().replace(" ", "_")
    desc = prediction.evidence or f"Textual evidence of {prediction.pattern_category or 'dark pattern'}"
    req_ctx = bool(prediction.requires_context)

    # ML model confidence
    m_conf = prediction.confidence

    # Qualitative evidence strength
    if req_ctx:
        strength = "weak"
    elif m_conf is not None and m_conf > 0.85:
        strength = "strong"
    else:
        strength = "moderate"

    # Legacy confidence for backward compatibility
    legacy_conf = (m_conf or 0.80) * (0.70 if req_ctx else 1.0)

    # Offsets if available in raw_text
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    if raw_text and prediction.evidence and prediction.evidence in raw_text:
        char_start = raw_text.find(prediction.evidence)
        char_end = char_start + len(prediction.evidence)

    eid = next_id_fn() if next_id_fn else "E001"

    item = EvidenceItem(
        evidence_id=eid,
        source="text",
        type=pat,
        pattern=pat,
        description=desc,
        detected=True,
        strength=strength,
        model_confidence=m_conf,
        confidence=legacy_conf,
        character_start=char_start,
        character_end=char_end,
        severity="low" if req_ctx else ("high" if (m_conf or 0.8) > 0.85 else "medium"),
        provenance=prediction.model_version or "text_predictor",
        temporal_position="static",
        metadata={
            "requires_context": req_ctx,
            "label": prediction.label,
            "consumer_consequence": prediction.consumer_consequence,
        },
    )
    return [item]


def adapt_price_analysis(
    analysis: PriceAnalysisResponse,
    has_text_sub: bool = False,
    has_text_drip: bool = False,
    next_id_fn: Optional[Callable[[], str]] = None,
) -> List[EvidenceItem]:
    """Adapt Price Analyzer response into unified EvidenceItem list (Part 9).

    - Deterministic parser certainty: strength="strong".
    - model_confidence is None (NEVER fabricate fake ML probability).
    - Legacy confidence=0.95 preserved for backward-compatible scoring.
    """
    items: List[EvidenceItem] = []

    def get_id() -> str:
        return next_id_fn() if next_id_fn else f"E{len(items) + 1:03d}"

    # A. Free trial or paid trial
    if analysis.trial_price is not None:
        is_free = (analysis.trial_price == 0.0)
        dur = analysis.trial_duration_days
        desc = (
            f"{dur}-day free trial" if (is_free and dur)
            else ("Free trial offer" if is_free else f"{dur or ''}-day paid trial ({analysis.trial_currency or ''}{analysis.trial_price})".strip())
        )
        items.append(
            EvidenceItem(
                evidence_id=get_id(),
                source="price",
                type="free_trial" if is_free else "paid_trial",
                pattern="subscription_trap" if has_text_sub else None,
                description=desc,
                value=analysis.trial_price,
                currency=analysis.trial_currency,
                detected=True,
                strength="strong",
                model_confidence=None,
                confidence=0.95,  # legacy
                character_start=analysis.initial_price_position,
                decision_context="subscription",
                temporal_position="static",
                severity="medium" if (has_text_sub and is_free and analysis.renewal_price) else "low",
                provenance="price_analyzer",
                metadata={"trial_duration_days": dur},
            )
        )

    # B. Renewal price
    if analysis.renewal_price is not None:
        period_str = f"/{analysis.billing_period}" if analysis.billing_period else ""
        desc = f"Renewal price of {analysis.renewal_currency or ''}{analysis.renewal_price}{period_str}"
        items.append(
            EvidenceItem(
                evidence_id=get_id(),
                source="price",
                type="renewal_price",
                pattern="subscription_trap" if has_text_sub else None,
                description=desc,
                value=analysis.renewal_price,
                currency=analysis.renewal_currency,
                detected=True,
                strength="strong",
                model_confidence=None,
                confidence=0.95,  # legacy
                decision_context="subscription",
                temporal_position="static",
                severity="medium" if has_text_sub else "low",
                provenance="price_analyzer",
                metadata={
                    "billing_period": analysis.billing_period,
                    "recurring": analysis.recurring,
                },
            )
        )

    # C. Upfront / Displayed base price
    if analysis.displayed_price is not None:
        is_duplicate_renewal = (
            analysis.renewal_price is not None
            and analysis.displayed_price.amount == analysis.renewal_price
            and analysis.trial_price is None
        )
        if not is_duplicate_renewal:
            items.append(
                EvidenceItem(
                    evidence_id=get_id(),
                    source="price",
                    type="displayed_price",
                    pattern=None,
                    description=f"Base displayed price of {analysis.displayed_price.currency} {analysis.displayed_price.amount}",
                    value=analysis.displayed_price.amount,
                    currency=analysis.displayed_price.currency,
                    detected=True,
                    strength="strong",
                    model_confidence=None,
                    confidence=0.95,  # legacy
                    character_start=analysis.initial_price_position,
                    temporal_position="static",
                    severity="low",
                    provenance="price_analyzer",
                )
            )
    elif analysis.entities and not any(e.source == "price" for e in items):
        for ent in analysis.entities:
            items.append(
                EvidenceItem(
                    evidence_id=get_id(),
                    source="price",
                    type="displayed_price",
                    pattern=None,
                    description=f"Price: {ent.currency} {ent.amount}",
                    value=ent.amount,
                    currency=ent.currency,
                    detected=True,
                    strength="strong",
                    model_confidence=None,
                    confidence=0.95,
                    character_start=ent.character_start,
                    character_end=ent.character_end,
                    temporal_position="static",
                    severity="low",
                    provenance="price_analyzer",
                )
            )

    # D. Additional costs / fees
    add_amt = analysis.additional_cost if analysis.additional_cost is not None else analysis.additional_costs
    if analysis.additional_cost_detected and add_amt is not None and add_amt > 0:
        curr = analysis.currency or (analysis.displayed_price.currency if analysis.displayed_price else None)
        pct_str = f" (+{analysis.additional_cost_percentage}%)" if analysis.additional_cost_percentage else ""
        items.append(
            EvidenceItem(
                evidence_id=get_id(),
                source="price",
                type="additional_cost",
                pattern="drip_pricing" if (has_text_drip and analysis.late_disclosed) else None,
                description=f"Additional fee of {curr or ''}{add_amt}{pct_str}",
                value=add_amt,
                currency=curr,
                detected=True,
                strength="strong",
                model_confidence=None,
                confidence=0.95,  # legacy
                character_start=analysis.additional_cost_position,
                decision_context="checkout",
                temporal_position="after_action" if analysis.late_disclosed else "static",
                severity="high" if (has_text_drip and analysis.late_disclosed) else "medium",
                provenance="price_analyzer",
                metadata={"percentage": analysis.additional_cost_percentage},
            )
        )

    # E. Late disclosure
    if analysis.late_disclosed is True or analysis.late_disclosure_detected:
        items.append(
            EvidenceItem(
                evidence_id=get_id(),
                source="price",
                type="late_disclosure",
                pattern="drip_pricing" if has_text_drip else None,
                description="Mandatory additional fee disclosed after base price",
                value=True,
                detected=True,
                strength="strong",
                model_confidence=None,
                confidence=0.95,  # legacy
                character_start=analysis.additional_cost_position,
                decision_context="checkout",
                temporal_position="after_action",
                severity="high" if has_text_drip else "medium",
                provenance="price_analyzer",
            )
        )

    # F. Price change
    has_actual_change = bool(
        not analysis.is_alternative_pricing
        and (
            analysis.price_change_detected
            or analysis.price_changed
            or (analysis.price_change is not None and analysis.price_change != 0.0)
        )
        and (analysis.price_change != 0.0 if analysis.price_change is not None else True)
    )
    if has_actual_change and analysis.price_change is not None and analysis.price_change != 0.0:
        p_diff = analysis.price_change
        pct = analysis.price_change_percentage
        items.append(
            EvidenceItem(
                evidence_id=get_id(),
                source="price",
                type="price_change",
                pattern=None,
                description=f"Price changed by {p_diff} ({pct}%)",
                value=p_diff,
                detected=True,
                strength="strong",
                model_confidence=None,
                confidence=0.95,  # legacy
                decision_context="checkout",
                temporal_position="after_action",
                severity="medium" if (p_diff and p_diff > 0) else "low",
                provenance="price_analyzer",
                metadata={
                    "price_change": p_diff,
                    "price_change_percentage": pct,
                    "previous_price": analysis.previous_price,
                    "current_price": analysis.current_price,
                },
            )
        )

    # G. Alternative pricing
    if analysis.is_alternative_pricing:
        items.append(
            EvidenceItem(
                evidence_id=get_id(),
                source="price",
                type="alternative_pricing",
                pattern=None,
                description="Mutually exclusive alternative pricing options detected",
                value=True,
                detected=True,
                strength="strong",
                model_confidence=None,
                confidence=0.95,  # legacy
                temporal_position="static",
                severity="low",
                provenance="price_analyzer",
            )
        )

    # H. Explicit total
    if analysis.explicit_total is not None:
        items.append(
            EvidenceItem(
                evidence_id=get_id(),
                source="price",
                type="explicit_total",
                pattern=None,
                description=f"Authoritative explicit total stated as {analysis.explicit_total}",
                value=analysis.explicit_total,
                detected=True,
                strength="strong",
                model_confidence=None,
                confidence=0.95,  # legacy
                temporal_position="static",
                severity="low",
                provenance="price_analyzer",
            )
        )

    return items


BEHAVIOR_SIGNAL_PATTERN_MAP: Dict[str, str] = {
    # Obstruction / retention loops
    "repeated_retention_interference": "obstruction",
    "retention_friction": "obstruction",
    "repeated_retention": "obstruction",
    "cancellation_obstruction": "obstruction",
    "cancellation_abandonment": "obstruction",
    "repeated_confirmation_pressure": "obstruction",
    "repeated_confirmation_friction": "obstruction",
    "backtracking_loop": "obstruction",
    "dead_end_behavior": "obstruction",
    "forced_delay": "obstruction",
    # Forced action / survey walls
    "required_survey": "forced_action",
    "survey_wall_friction": "forced_action",
    "forced_action_sequence": "forced_action",
}

BEHAVIOR_ANALYZER_OBSTRUCTION_TYPES = {
    "DIFFICULT_CANCELLATION",
    "EXCESSIVE_STEPS",
    "REPEATED_PROMPTS",
}

DOM_SIGNAL_PATTERN_MAP: Dict[str, str] = {
    # Obstruction / cancellation friction
    "cancel_action_visually_deemphasized": "obstruction",
    "cancel_action_disabled": "obstruction",
    "disabled_action": "obstruction",
    "hidden_alternative": "obstruction",
    "hidden_action": "obstruction",
    "covered_action": "obstruction",
    "confirmation_ui": "obstruction",
    "cancellation_obstruction": "obstruction",
    # Forced action
    "modal_interference": "forced_action",
    "scroll_lock_interference": "forced_action",
    # Confirm shaming
    "asymmetric_confirmation": "confirm_shaming",
    # Misdirection / visual prominence asymmetry
    "action_visual_deemphasis": "misdirection",
    "action_size_asymmetry": "misdirection",
    "contrast_asymmetry": "misdirection",
    "typography_asymmetry": "misdirection",
    "visibility_mismatch": "misdirection",
    "semantic_competing_actions": "misdirection",
    # Sneaking / commercial preselection
    "preselected_option": "sneaking",
    "preselected_commercial_choice": "sneaking",
    # Drip Pricing
    "post_action_fee_added": "drip_pricing",
    "post_action_price_changed": "drip_pricing",
    # Urgency
    "fake_countdown_structure": "urgency",
}

CANONICAL_CONTEXT_MAPPINGS: Dict[str, str] = {
    "cart": "checkout",
    "basket": "checkout",
}

CANONICAL_DECISION_CONTEXTS: Set[str] = {
    "cancellation", "subscription", "checkout", "billing", "consent",
    "purchase", "account_deletion", "membership", "renewal", "dialog", "unknown",
}


def normalize_decision_context(raw_val: Optional[Any]) -> Optional[str]:
    """Deterministically normalize raw decision context to canonical vocabulary before EvidenceItem creation.

    - Case-insensitive
    - Whitespace-trimmed
    - Maps alias terms ('cart', 'basket' -> 'checkout')
    - Maps recognized canonical contexts directly
    - Safely maps unknown / unrecognized string values to 'unknown'
    - Preserves None if raw_val is None
    """
    if raw_val is None:
        return None
    s = str(raw_val).strip().lower()
    if not s:
        return None
    if s in CANONICAL_CONTEXT_MAPPINGS:
        return CANONICAL_CONTEXT_MAPPINGS[s]
    if s in CANONICAL_DECISION_CONTEXTS:
        return s
    return "unknown"


def adapt_behavior_evidence(
    raw_behavior: Union[List[Any], Dict[str, Any], Any],
    next_id_fn: Optional[Callable[[], str]] = None,
) -> List[EvidenceItem]:
    """Adapt B3 behavior sequence signals and evidence into unified EvidenceItems (Part 10).

    Preserves:
    - signal type
    - strength ('weak', 'moderate', 'strong')
    - reason / description
    - event_indices
    - route_sequence
    - decision_context
    - model_confidence is explicitly None (deterministic reasoning).
    """
    items: List[EvidenceItem] = []

    # Flatten signals / evidence list from B3 dict
    raw_list: List[Any] = []
    if isinstance(raw_behavior, dict):
        if "behavior_signals" in raw_behavior and isinstance(raw_behavior["behavior_signals"], list):
            raw_list.extend(raw_behavior["behavior_signals"])
        elif "evidence" in raw_behavior and isinstance(raw_behavior["evidence"], list):
            raw_list.extend(raw_behavior["evidence"])
        else:
            raw_list.append(raw_behavior)
    elif isinstance(raw_behavior, list):
        raw_list.extend(raw_behavior)
    elif raw_behavior is not None:
        raw_list.append(raw_behavior)

    for entry in raw_list:
        if isinstance(entry, EvidenceItem):
            if not entry.detected:
                continue
            item = entry.model_copy() if hasattr(entry, "model_copy") else entry.copy()
            if item.decision_context is not None:
                item.decision_context = normalize_decision_context(item.decision_context)
            if not item.evidence_id and next_id_fn:
                item.evidence_id = next_id_fn()
            items.append(item)
            continue

        if not isinstance(entry, dict):
            continue

        sig_type = entry.get("signal_type") or entry.get("type") or entry.get("behavior") or "behavior_signal"
        strength = entry.get("strength") or "moderate"
        reason = entry.get("reason") or entry.get("description") or entry.get("explanation") or f"Observed {sig_type}"
        event_indices = entry.get("event_indices") or []
        route_sequence = entry.get("route_sequence") or []
        route = entry.get("route") or (route_sequence[-1] if route_sequence else None)

        # Context inference and canonical normalization
        raw_ctx = entry.get("decision_context")
        if raw_ctx is not None:
            decision_context = normalize_decision_context(raw_ctx)
        else:
            lowered = f"{sig_type} {reason} {' '.join(route_sequence)}".lower()
            if "cancel" in lowered or "unsubscribe" in lowered:
                decision_context = "cancellation"
            elif "subscri" in lowered or "membership" in lowered or "renew" in lowered:
                decision_context = "subscription"
            elif "checkout" in lowered or "billing" in lowered or "cart" in lowered or "basket" in lowered or "order" in lowered:
                decision_context = "checkout"
            elif "consent" in lowered or "cookie" in lowered:
                decision_context = "consent"
            else:
                decision_context = None

        # Canonical pattern mapping. High-level analyzer findings become
        # obstruction evidence only when explicitly tied to cancellation.
        detected = bool(entry.get("detected", True))
        has_cancellation_context = decision_context in ("cancellation", "account_deletion")
        analyzer_obstruction = (
            not entry.get("pattern")
            and detected
            and sig_type in BEHAVIOR_ANALYZER_OBSTRUCTION_TYPES
            and has_cancellation_context
        )
        pat = (
            entry.get("pattern")
            or ("obstruction" if analyzer_obstruction else None)
            or BEHAVIOR_SIGNAL_PATTERN_MAP.get(sig_type)
            or sig_type
        )

        # Temporal position
        temporal_pos = entry.get("temporal_position")
        if not temporal_pos:
            temporal_pos = "during_action" if ("friction" in sig_type or "obstruction" in sig_type or "loop" in sig_type) else "static"

        eid = next_id_fn() if next_id_fn else f"E{len(items) + 1:03d}"

        items.append(
            EvidenceItem(
                evidence_id=eid,
                source="behavior",
                type=sig_type,
                pattern=pat,
                description=reason,
                detected=detected,
                strength=strength,
                model_confidence=None,  # Deterministic sequence reasoning
                confidence=None,
                event_indices=event_indices,
                route=route,
                route_sequence=route_sequence,
                decision_context=decision_context,
                temporal_position=temporal_pos,
                severity=entry.get("severity") or ("high" if strength == "strong" else "medium"),
                provenance=entry.get("provenance") or "behavior_sequence_b3",
                metadata=entry.get("metadata") or {
                    k: v for k, v in entry.items()
                    if k not in {
                        "signal_type", "type", "behavior", "strength", "reason",
                        "description", "event_indices", "route_sequence", "route",
                        "decision_context", "temporal_position", "severity", "provenance"
                    }
                },
            )
        )

    return items


def adapt_dom_evidence(
    raw_dom: Union[List[Any], Dict[str, Any], Any],
    next_id_fn: Optional[Callable[[], str]] = None,
) -> List[EvidenceItem]:
    """Adapt B4.1–B4.4 DOM context signals and evidence into unified EvidenceItems (Part 11).

    Preserves:
    - type
    - detected
    - strength
    - reason / description
    - element_ref
    - event_indices
    - route
    - decision_context
    - dom_properties in metadata (not flattened into strings).
    - model_confidence is None (deterministic DOM reasoning).
    """
    items: List[EvidenceItem] = []

    raw_list: List[Any] = []
    if isinstance(raw_dom, dict):
        if "dom_signals" in raw_dom and isinstance(raw_dom["dom_signals"], list):
            raw_list.extend(raw_dom["dom_signals"])
        elif "evidence" in raw_dom and isinstance(raw_dom["evidence"], list):
            raw_list.extend(raw_dom["evidence"])
        else:
            raw_list.append(raw_dom)
    elif isinstance(raw_dom, list):
        raw_list.extend(raw_dom)
    elif raw_dom is not None:
        raw_list.append(raw_dom)

    for entry in raw_list:
        if isinstance(entry, EvidenceItem):
            item = entry.model_copy() if hasattr(entry, "model_copy") else entry.copy()
            if item.decision_context is not None:
                item.decision_context = normalize_decision_context(item.decision_context)
            if not item.evidence_id and next_id_fn:
                item.evidence_id = next_id_fn()
            items.append(item)
            continue

        if not isinstance(entry, dict):
            continue

        sig_type = entry.get("signal_type") or entry.get("type") or "dom_signal"
        strength = entry.get("strength") or "moderate"
        reason = entry.get("reason") or entry.get("description") or f"Observed {sig_type}"
        element_ref = entry.get("element_ref")
        event_indices = entry.get("event_indices") or []
        route = entry.get("route")

        # Context inference and canonical normalization
        raw_ctx = entry.get("decision_context")
        if raw_ctx is not None:
            decision_context = normalize_decision_context(raw_ctx)
        else:
            lowered = f"{sig_type} {reason} {route or ''}".lower()
            if "cancel" in lowered or "unsubscribe" in lowered:
                decision_context = "cancellation"
            elif "subscri" in lowered or "membership" in lowered or "renew" in lowered:
                decision_context = "subscription"
            elif "checkout" in lowered or "billing" in lowered or "cart" in lowered or "basket" in lowered or "order" in lowered:
                decision_context = "checkout"
            elif "consent" in lowered or "cookie" in lowered:
                decision_context = "consent"
            else:
                decision_context = None

        # Canonical pattern mapping
        pat = entry.get("pattern") or DOM_SIGNAL_PATTERN_MAP.get(sig_type) or sig_type

        # Temporal position
        temporal_pos = entry.get("temporal_position")
        if not temporal_pos:
            temporal_pos = "after_action" if sig_type.startswith("post_action_") else "static"

        eid = next_id_fn() if next_id_fn else f"E{len(items) + 1:03d}"

        dom_props = entry.get("dom_properties") or {}
        dom_value = entry.get("value")
        if dom_value is None and isinstance(dom_props, dict):
            dom_value = dom_props.get("amount")

        items.append(
            EvidenceItem(
                evidence_id=eid,
                source="dom",
                type=sig_type,
                pattern=pat,
                description=reason,
                value=dom_value,
                detected=bool(entry.get("detected", True)),
                strength=strength,
                model_confidence=None,  # Deterministic DOM reasoning
                confidence=None,
                element_ref=element_ref,
                event_indices=event_indices,
                route=route,
                decision_context=decision_context,
                temporal_position=temporal_pos,
                severity=entry.get("severity") or ("high" if strength == "strong" else "medium"),
                provenance=entry.get("provenance") or "dom_analyzer_b4",
                metadata={
                    "dom_properties": dom_props,
                    **{
                        k: v for k, v in entry.items()
                        if k not in {
                            "signal_type", "type", "strength", "reason",
                            "description", "element_ref", "event_indices", "route",
                            "decision_context", "temporal_position", "severity",
                            "provenance", "dom_properties"
                        }
                    }
                },
            )
        )

    return items


def adapt_image_evidence(
    raw_image: Union[List[Any], Dict[str, Any], Any],
    next_id_fn: Optional[Callable[[], str]] = None,
) -> List[EvidenceItem]:
    """Adapt future Image Analyzer output into unified EvidenceItems (Part 12 placeholder).

    - model_confidence preserves ML detector probability.
    - evidence_strength is optional qualitative strength.
    - bounding_box and frame_id are preserved.
    """
    items: List[EvidenceItem] = []

    raw_list: List[Any] = []
    if isinstance(raw_image, dict):
        if "image_signals" in raw_image and isinstance(raw_image["image_signals"], list):
            raw_list.extend(raw_image["image_signals"])
        elif "evidence" in raw_image and isinstance(raw_image["evidence"], list):
            raw_list.extend(raw_image["evidence"])
        else:
            raw_list.append(raw_image)
    elif isinstance(raw_image, list):
        raw_list.extend(raw_image)
    elif raw_image is not None:
        raw_list.append(raw_image)

    for entry in raw_list:
        if isinstance(entry, EvidenceItem):
            item = entry.model_copy() if hasattr(entry, "model_copy") else entry.copy()
            if item.decision_context is not None:
                item.decision_context = normalize_decision_context(item.decision_context)
            if not item.evidence_id and next_id_fn:
                item.evidence_id = next_id_fn()
            items.append(item)
            continue

        if not isinstance(entry, dict):
            continue

        original_label = entry.get("signal_type") or entry.get("type") or entry.get("class") or "visual_pattern"
        detected = bool(entry.get("detected", True))
        if not detected:
            continue

        vision_type_map = {
            "activity_message": "activity_notification",
            "limited_time_message": "urgency",
            "low_stock_message": "scarcity",
        }
        sig_type = vision_type_map.get(original_label, original_label)
        m_conf = entry.get("model_confidence")
        if m_conf is None and "confidence" in entry and isinstance(entry["confidence"], (int, float)):
            m_conf = float(entry["confidence"])

        strength = entry.get("strength")
        if not strength:
            strength = "strong" if (m_conf or 0.0) > 0.85 else "moderate"

        desc = entry.get("description") or f"Visual detection of {original_label}"
        bbox = entry.get("bounding_box") or entry.get("bbox")
        frame_id = entry.get("frame_id")
        temporal_pos = entry.get("temporal_position") or "static"

        eid = next_id_fn() if next_id_fn else f"E{len(items) + 1:03d}"
        original_metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        fallback_metadata = {
            k: v for k, v in entry.items()
            if k not in {
                "signal_type", "type", "class", "strength", "description",
                "model_confidence", "confidence", "bounding_box", "bbox",
                "frame_id", "temporal_position", "decision_context",
                "severity", "provenance", "metadata", "detected"
            }
        }
        metadata = {
            **fallback_metadata,
            **original_metadata,
            "original_vision_label": original_label,
        }

        raw_ctx = entry.get("decision_context")
        decision_context = normalize_decision_context(raw_ctx) if raw_ctx is not None else None

        items.append(
            EvidenceItem(
                evidence_id=eid,
                source="image",
                type=sig_type,
                pattern=sig_type,
                description=desc,
                detected=detected,
                strength=strength,
                model_confidence=m_conf,
                confidence=m_conf,  # legacy
                bounding_box=bbox,
                frame_id=frame_id,
                temporal_position=temporal_pos,
                decision_context=decision_context,
                severity=entry.get("severity") or ("high" if strength == "strong" else "medium"),
                provenance=entry.get("provenance") or "image_analyzer",
                metadata=metadata,
            )
        )

    return items
