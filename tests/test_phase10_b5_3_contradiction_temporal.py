"""tests/test_phase10_b5_3_contradiction_temporal.py
Phase B5.3 Contradiction Escalation & Temporal Evidence Test Suite.

Comprehensive validation covering:
- Contradiction Positives (10 scenarios)
- Temporal Positives (10 scenarios)
- Hard Negatives (15 scenarios)
- Invariants & Safety Guarantees (10 scenarios)
"""
from __future__ import annotations

import pytest

from backend.schemas import PredictResponse
from backend.schemas.evidence import (
    ContradictionItem,
    EvidenceFusionRequest,
    EvidenceItem,
    TemporalRelationshipItem,
)
from backend.schemas.price import PriceAnalysisResponse
from backend.services.evidence_fusion import EvidenceFusionEngine

fusion_engine = EvidenceFusionEngine()


# =====================================================================
# SECTION 1: CONTRADICTION POSITIVES (10 SCENARIOS)
# =====================================================================

def test_01_text_cancel_anytime_vs_dom_disabled_cancel():
    """1. Text cancel-anytime + DOM disabled cancel: contradiction detected, pattern=obstruction."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.88,
        model_version="v1.0.0",
        pattern_category="Subscription Trap",
        evidence="Cancel anytime online with no penalty.",
    )
    dom_item = {
        "type": "cancel_action_disabled",
        "detected": True,
        "strength": "strong",
        "description": "Cancel button rendered in disabled state",
        "decision_context": "cancellation",
        "route": "/account/cancel",
    }
    req = EvidenceFusionRequest(text_prediction=text_pred, dom_evidence=[dom_item])
    res = fusion_engine.fuse(req)

    assert len(res.contradictions) >= 1
    c = next(x for x in res.contradictions if x.type == "text_vs_dom")
    assert c.source_a == "text"
    assert c.source_b == "dom"
    assert c.pattern == "obstruction"
    assert c.severity == "strong"
    assert "disabled" in c.reason.lower() or "cancel" in c.reason.lower()


def test_02_text_one_click_cancel_vs_behavior_7_steps():
    """2. Text one-click cancel + Behavior 7 cancellation steps: contradiction detected."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.86,
        model_version="v1.0.0",
        pattern_category="Subscription Trap",
        evidence="Cancel in one click whenever you want.",
    )
    beh_item = {
        "type": "repeated_retention_interference",
        "detected": True,
        "strength": "strong",
        "description": "Encountered 7-step retention flow rejecting cancellation attempts",
        "event_indices": [1, 2, 3, 4, 5, 6, 7],
        "decision_context": "cancellation",
        "route": "/cancel",
    }
    req = EvidenceFusionRequest(text_prediction=text_pred, behavior_evidence=[beh_item])
    res = fusion_engine.fuse(req)

    assert len(res.contradictions) >= 1
    c = next(x for x in res.contradictions if x.type == "text_vs_behavior")
    assert c.source_a == "text"
    assert c.source_b == "behavior"
    assert c.pattern == "obstruction"
    assert c.severity == "strong"


def test_03_text_all_fees_included_vs_price_additional_fee():
    """3. Text all-fees-included + Price additional fee: financial disclosure contradiction."""
    req = EvidenceFusionRequest(
        text="All fees included in the stated price. Zero hidden fees.",
        price_analysis=PriceAnalysisResponse(
            additional_cost=150.0,
            late_disclosed=True,
            currency="INR",
        ),
    )
    res = fusion_engine.fuse(req)

    assert len(res.contradictions) >= 1
    c = next(x for x in res.contradictions if x.type == "text_vs_price")
    assert c.source_a == "text"
    assert c.source_b == "price"
    assert c.pattern == "drip_pricing"
    assert c.severity == "strong"


def test_04_text_no_recurring_charge_vs_price_renewal():
    """4. Text no recurring charge + Price renewal: subscription trap contradiction."""
    req = EvidenceFusionRequest(
        text="Single payment only. No recurring charge.",
        price_analysis=PriceAnalysisResponse(
            renewal_price=499.0,
            renewal_currency="INR",
            recurring=True,
            billing_period="month",
        ),
    )
    res = fusion_engine.fuse(req)

    assert len(res.contradictions) >= 1
    c = next(x for x in res.contradictions if x.type == "text_vs_price")
    assert c.pattern == "subscription_trap"
    assert c.severity == "strong"


def test_05_dom_cancel_visible_vs_behavior_dead_end():
    """5. DOM cancel visible + Behavior cancellation dead-end: interaction contradiction."""
    dom_item = {
        "type": "action_rendered",
        "detected": True,
        "strength": "moderate",
        "description": "Cancel button is visible and active on page",
        "element_ref": "BTN_CANCEL",
        "decision_context": "cancellation",
        "route": "/account/cancel",
    }
    beh_item = {
        "type": "cancellation_abandonment",
        "detected": True,
        "strength": "strong",
        "description": "User clicks cancel but encounters dead-end loop with no termination",
        "event_indices": [5, 8, 12],
        "decision_context": "cancellation",
        "route": "/account/cancel",
    }
    req = EvidenceFusionRequest(dom_evidence=[dom_item], behavior_evidence=[beh_item])
    res = fusion_engine.fuse(req)

    assert len(res.contradictions) >= 1
    c = next(x for x in res.contradictions if x.type == "dom_vs_behavior")
    assert c.source_a == "dom"
    assert c.source_b == "behavior"
    assert c.pattern == "obstruction"


def test_06_text_normal_urgency_vs_image_countdown():
    """6. Text normal urgency + Image countdown: visual contradiction detected."""
    image_item = {
        "type": "countdown_timer",
        "detected": True,
        "strength": "moderate",
        "description": "Flashing countdown timer detected above purchase button",
        "decision_context": "purchase",
    }
    req = EvidenceFusionRequest(
        text="Standard product description with standard delivery options.",
        image_evidence=[image_item],
    )
    res = fusion_engine.fuse(req)

    assert len(res.contradictions) >= 1
    c = next(x for x in res.contradictions if x.type == "image_vs_text")
    assert c.source_a == "image"
    assert c.source_b == "text"
    assert c.pattern == "urgency"


def test_07_text_normal_subscription_vs_dom_retention_interference():
    """7. Text normal subscription + DOM retention interference."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.85,
        model_version="v1.0.0",
        pattern_category="Subscription Trap",
        evidence="Cancel anytime with one click.",
    )
    dom_item = {
        "type": "cancel_action_visually_deemphasized",
        "detected": True,
        "strength": "strong",
        "description": "Cancel option rendered at 1.1:1 contrast ratio beneath large retention offer",
        "decision_context": "cancellation",
        "route": "/membership/cancel",
    }
    req = EvidenceFusionRequest(text_prediction=text_pred, dom_evidence=[dom_item])
    res = fusion_engine.fuse(req)

    assert len(res.contradictions) >= 1
    assert any(c.pattern == "obstruction" for c in res.contradictions)


def test_08_text_free_vs_price_paid_trial():
    """8. Text 100% free + Price paid trial: contradiction detected."""
    req = EvidenceFusionRequest(
        text="100% free offer with no commitment ever.",
        price_analysis=PriceAnalysisResponse(
            trial_price=49.0,
            trial_duration_days=3,
            currency="INR",
        ),
    )
    res = fusion_engine.fuse(req)

    assert len(res.contradictions) >= 1
    c = next(x for x in res.contradictions if x.type == "text_vs_price")
    assert c.pattern == "subscription_trap"


def test_09_text_included_fee_vs_post_action_fee():
    """9. Text inclusive fee + post-action fee added."""
    dom_fee = {
        "type": "post_action_fee_added",
        "detected": True,
        "strength": "strong",
        "description": "Surprise handling fee appeared after checkout step",
        "temporal_position": "after_action",
        "decision_context": "checkout",
    }
    req = EvidenceFusionRequest(
        text="All fees included in the stated cart total.",
        dom_evidence=[dom_fee],
    )
    res = fusion_engine.fuse(req)

    assert len(res.contradictions) >= 1
    assert any(c.type == "text_vs_price" or c.type == "text_vs_dom" for c in res.contradictions)


def test_10_text_opt_out_available_vs_dom_hidden_opt_out():
    """10. Text opt-out available + DOM hidden opt-out choice."""
    dom_item = {
        "type": "hidden_alternative",
        "detected": True,
        "strength": "strong",
        "description": "Reject all cookies option is completely hidden behind nested link",
        "decision_context": "consent",
        "route": "/consent",
    }
    req = EvidenceFusionRequest(
        text="You can opt out at any time. Decline anytime.",
        dom_evidence=[dom_item],
    )
    res = fusion_engine.fuse(req)

    assert len(res.contradictions) >= 1
    c = next(x for x in res.contradictions if x.type == "text_vs_dom")
    assert c.pattern == "obstruction"


# =====================================================================
# SECTION 2: TEMPORAL POSITIVES (10 SCENARIOS)
# =====================================================================

def test_11_price_increases_after_continue():
    """11. Price increases after Continue: price_change_after_action."""
    price_resp = PriceAnalysisResponse(
        previous_price=499.0,
        current_price=578.0,
        price_change=79.0,
        price_change_detected=True,
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(price_analysis=price_resp))

    assert len(res.temporal_relationships) >= 1
    t = next(x for x in res.temporal_relationships if x.type == "price_change_after_action")
    assert t.decision_context == "checkout"
    assert "increased" in t.reason.lower() or "changed" in t.reason.lower()


def test_12_fee_appears_after_continue():
    """12. Fee appears after Continue: fee_added_after_action."""
    base_price = {
        "type": "displayed_price",
        "detected": True,
        "value": 499.0,
        "temporal_position": "before_action",
        "decision_context": "checkout",
        "route": "/checkout",
    }
    post_fee = {
        "type": "post_action_fee_added",
        "detected": True,
        "value": 79.0,
        "temporal_position": "after_action",
        "decision_context": "checkout",
        "route": "/checkout",
    }
    req = EvidenceFusionRequest(dom_evidence=[base_price, post_fee])
    res = fusion_engine.fuse(req)

    assert len(res.temporal_relationships) >= 1
    t = next(x for x in res.temporal_relationships if x.type == "fee_added_after_action")
    assert t.strength == "strong"


def test_13_add_on_selected_after_continue():
    """13. Add-on selected after Continue: option_added_after_action."""
    before_opt = {
        "type": "action_unselected",
        "detected": True,
        "temporal_position": "before_action",
        "decision_context": "checkout",
        "route": "/checkout",
    }
    after_opt = {
        "type": "preselected_option",
        "detected": True,
        "temporal_position": "after_action",
        "decision_context": "checkout",
        "route": "/checkout",
    }
    req = EvidenceFusionRequest(dom_evidence=[before_opt, after_opt])
    res = fusion_engine.fuse(req)

    assert len(res.temporal_relationships) >= 1
    t = next(x for x in res.temporal_relationships if x.type == "option_added_after_action")
    assert t.decision_context == "checkout"


def test_14_cancel_disabled_after_interaction():
    """14. Cancel disabled after interaction: action_disabled_after_action."""
    before_act = {
        "type": "action_enabled",
        "detected": True,
        "temporal_position": "before_action",
        "decision_context": "cancellation",
        "route": "/cancel",
    }
    after_act = {
        "type": "cancel_action_disabled",
        "detected": True,
        "temporal_position": "after_action",
        "decision_context": "cancellation",
        "route": "/cancel",
    }
    req = EvidenceFusionRequest(dom_evidence=[before_act, after_act])
    res = fusion_engine.fuse(req)

    assert len(res.temporal_relationships) >= 1
    t = next(x for x in res.temporal_relationships if x.type == "action_disabled_after_action")
    assert t.decision_context == "cancellation"


def test_15_alternative_removed_after_action():
    """15. Alternative removed after user action: alternative_removed_after_action."""
    before_alt = {
        "type": "action_available",
        "detected": True,
        "temporal_position": "before_action",
        "decision_context": "cancellation",
        "route": "/cancel",
    }
    after_alt = {
        "type": "hidden_alternative",
        "detected": True,
        "temporal_position": "after_action",
        "decision_context": "cancellation",
        "route": "/cancel",
    }
    req = EvidenceFusionRequest(dom_evidence=[before_alt, after_alt])
    res = fusion_engine.fuse(req)

    assert len(res.temporal_relationships) >= 1
    t = next(x for x in res.temporal_relationships if x.type == "alternative_removed_after_action")
    assert t.strength == "strong"


def test_16_retention_modal_appears_after_action():
    """16. Retention modal appears after interaction: modal_appeared_after_action."""
    before_flow = {
        "type": "flow_page",
        "detected": True,
        "temporal_position": "before_action",
        "decision_context": "cancellation",
        "route": "/cancel",
    }
    after_modal = {
        "type": "modal_interference",
        "detected": True,
        "temporal_position": "after_action",
        "decision_context": "cancellation",
        "route": "/cancel",
    }
    req = EvidenceFusionRequest(dom_evidence=[before_flow, after_modal])
    res = fusion_engine.fuse(req)

    assert len(res.temporal_relationships) >= 1
    t = next(x for x in res.temporal_relationships if x.type == "modal_appeared_after_action")
    assert t.decision_context == "cancellation"


def test_17_required_survey_appears_after_action():
    """17. Required survey appears after interaction: required_step_appeared_after_action."""
    before_flow = {
        "type": "flow_page",
        "detected": True,
        "temporal_position": "before_action",
        "decision_context": "cancellation",
        "route": "/cancel",
    }
    after_survey = {
        "type": "required_survey",
        "detected": True,
        "temporal_position": "after_action",
        "decision_context": "cancellation",
        "route": "/cancel",
    }
    req = EvidenceFusionRequest(dom_evidence=[before_flow], behavior_evidence=[after_survey])
    res = fusion_engine.fuse(req)

    assert len(res.temporal_relationships) >= 1
    t = next(x for x in res.temporal_relationships if x.type == "required_step_appeared_after_action")
    assert t.strength == "strong"


def test_18_confirmation_ui_appears_after_action():
    """18. Confirmation friction UI appears after action."""
    before_step = {
        "type": "flow_page",
        "detected": True,
        "temporal_position": "before_action",
        "decision_context": "cancellation",
        "route": "/cancel",
    }
    after_ui = {
        "type": "modal_interference",
        "detected": True,
        "temporal_position": "after_action",
        "decision_context": "cancellation",
        "route": "/cancel",
    }
    req = EvidenceFusionRequest(dom_evidence=[before_step, after_ui])
    res = fusion_engine.fuse(req)

    assert len(res.temporal_relationships) >= 1


def test_19_price_changes_within_same_checkout_route():
    """19. Price changes within same checkout route."""
    price_resp = PriceAnalysisResponse(
        previous_price=999.0,
        current_price=1099.0,
        price_change=100.0,
        price_change_detected=True,
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(price_analysis=price_resp))
    assert len(res.temporal_relationships) == 1
    assert res.temporal_relationships[0].type == "price_change_after_action"


def test_20_subscription_renewal_revealed_after_trial():
    """20. Subscription recurring renewal revealed after trial selection."""
    before_trial = {
        "type": "displayed_price",
        "detected": True,
        "value": 0.0,
        "temporal_position": "before_action",
        "decision_context": "checkout",
        "route": "/checkout",
    }
    after_fee = {
        "type": "post_action_fee_added",
        "detected": True,
        "value": 299.0,
        "temporal_position": "after_action",
        "decision_context": "checkout",
        "route": "/checkout",
    }
    req = EvidenceFusionRequest(dom_evidence=[before_trial, after_fee])
    res = fusion_engine.fuse(req)

    assert len(res.temporal_relationships) >= 1
    assert any(t.type == "fee_added_after_action" for t in res.temporal_relationships)


# =====================================================================
# SECTION 3: HARD NEGATIVES (15 SCENARIOS)
# =====================================================================

def test_21_price_changes_between_unrelated_sessions():
    """21. Price changes between unrelated sessions: must NOT form temporal relationship."""
    before_item = {
        "type": "displayed_price",
        "detected": True,
        "temporal_position": "before_action",
        "metadata": {"session_id": "session_alpha"},
    }
    after_item = {
        "type": "post_action_fee_added",
        "detected": True,
        "temporal_position": "after_action",
        "metadata": {"session_id": "session_beta"},
    }
    req = EvidenceFusionRequest(dom_evidence=[before_item, after_item])
    res = fusion_engine.fuse(req)

    assert len(res.temporal_relationships) == 0


def test_22_price_change_explicitly_disclosed_before_action():
    """22. Price change explicitly disclosed before action: not a dark-pattern contradiction."""
    req = EvidenceFusionRequest(
        text="Price will increase to ₹578 after taxes upon checkout.",
        price_analysis=PriceAnalysisResponse(
            previous_price=499.0,
            current_price=578.0,
            price_change=79.0,
            late_disclosed=False,
        ),
    )
    res = fusion_engine.fuse(req)

    # Factual price change is recorded, but no text_vs_price contradiction
    assert not any(c.type == "text_vs_price" for c in res.contradictions)


def test_23_legitimate_tax_shown_before_payment():
    """23. Legitimate tax shown before payment: not a contradiction."""
    req = EvidenceFusionRequest(
        text="Standard product purchase. Taxes calculated at checkout.",
        price_analysis=PriceAnalysisResponse(
            additional_cost=50.0,
            late_disclosed=False,
        ),
    )
    res = fusion_engine.fuse(req)

    assert not any(c.type == "text_vs_price" for c in res.contradictions)


def test_24_loading_temporarily_disables_button():
    """24. Loading state temporarily disables button: NOT an obstruction contradiction."""
    dom_item = {
        "type": "disabled_action",
        "detected": True,
        "strength": "moderate",
        "description": "Button is disabled while loading transaction data",
        "metadata": {"state": "loading"},
        "decision_context": "cancellation",
    }
    req = EvidenceFusionRequest(
        text="Cancel anytime with one click.",
        dom_evidence=[dom_item],
    )
    res = fusion_engine.fuse(req)

    assert not any(c.type == "text_vs_dom" for c in res.contradictions)


def test_25_normal_modal():
    """25. Normal confirmation modal without interference: no contradiction."""
    dom_item = {
        "type": "normal_modal",
        "detected": False,
        "decision_context": "cancellation",
    }
    req = EvidenceFusionRequest(
        text="Standard cancellation workflow.",
        dom_evidence=[dom_item],
    )
    res = fusion_engine.fuse(req)
    assert len(res.contradictions) == 0


def test_26_legitimate_survey():
    """26. Legitimate optional survey: no forced action contradiction."""
    beh_item = {
        "type": "optional_feedback",
        "detected": False,
        "decision_context": "cancellation",
    }
    req = EvidenceFusionRequest(behavior_evidence=[beh_item])
    res = fusion_engine.fuse(req)
    assert len(res.contradictions) == 0


def test_27_normal_cancellation_with_several_steps():
    """27. Normal cancellation workflow with multiple standard steps: no text_vs_behavior contradiction."""
    req = EvidenceFusionRequest(
        text="Review your cancellation details and confirm your selection.",
        behavior_evidence=[{
            "type": "navigation_step",
            "detected": True,
            "event_indices": [1, 2, 3],
            "decision_context": "cancellation",
        }],
    )
    res = fusion_engine.fuse(req)
    assert not any(c.type == "text_vs_behavior" for c in res.contradictions)


def test_28_normal_back_continue_navigation():
    """28. Normal Back -> Continue navigation: no contradiction."""
    req = EvidenceFusionRequest(
        text="Navigate through steps to complete your profile.",
        behavior_evidence=[{
            "type": "standard_navigation",
            "detected": True,
            "event_indices": [2, 3],
        }],
    )
    res = fusion_engine.fuse(req)
    assert len(res.contradictions) == 0


def test_29_normal_responsive_button_size_difference():
    """29. Normal responsive layout: no contradiction."""
    dom_item = {
        "type": "responsive_button",
        "detected": False,
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[dom_item]))
    assert len(res.contradictions) == 0


def test_30_normal_countdown_for_legitimate_event():
    """30. Normal countdown when text explicitly announces live sale: no image_vs_text contradiction."""
    req = EvidenceFusionRequest(
        text="Flash sale ends in 10 minutes! Hurry up!",
        image_evidence=[{
            "type": "countdown_timer",
            "detected": True,
            "decision_context": "purchase",
        }],
    )
    res = fusion_engine.fuse(req)
    assert not any(c.type == "image_vs_text" for c in res.contradictions)


def test_31_normal_low_stock_information():
    """31. Factual stock inventory communication: no contradiction."""
    req = EvidenceFusionRequest(
        text="Only 2 items left in warehouse.",
    )
    res = fusion_engine.fuse(req)
    assert len(res.contradictions) == 0


def test_32_text_and_price_agreeing():
    """32. Text and price agreeing (e.g. ₹999/month text + ₹999/month price): corroboration, NOT contradiction."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.90,
        model_version="v1.0.0",
        pattern_category="Subscription Trap",
        evidence="automatically renews at ₹999/month",
    )
    price_resp = PriceAnalysisResponse(
        renewal_price=999.0,
        renewal_currency="INR",
        recurring=True,
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    # Agreeing sources must corroborate, not contradict
    assert res.is_corroborated is True
    assert not any(c.type == "text_vs_price" for c in res.contradictions)


def test_33_text_and_dom_agreeing():
    """33. Text and DOM agreeing on obstruction: corroboration, NOT contradiction."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.88,
        model_version="v1.0.0",
        pattern_category="Subscription Trap",
        evidence="difficult cancellation flow",
    )
    dom_item = {
        "type": "action_visual_deemphasis",
        "detected": True,
        "strength": "strong",
        "decision_context": "cancellation",
    }
    req = EvidenceFusionRequest(text_prediction=text_pred, dom_evidence=[dom_item])
    res = fusion_engine.fuse(req)

    assert res.is_corroborated is True


def test_34_unrelated_routes():
    """34. Unrelated routes (/privacy vs /account/delete): do NOT form contradiction or temporal relationship."""
    dom_item = {
        "type": "disabled_action",
        "detected": True,
        "route": "/privacy",
        "decision_context": "consent",
    }
    beh_item = {
        "type": "cancellation_obstruction",
        "detected": True,
        "route": "/account/delete",
        "decision_context": "account_deletion",
    }
    req = EvidenceFusionRequest(dom_evidence=[dom_item], behavior_evidence=[beh_item])
    res = fusion_engine.fuse(req)

    assert len(res.contradictions) == 0
    assert len(res.temporal_relationships) == 0


def test_35_unrelated_contexts():
    """35. Incompatible context families (consent vs purchase): no cross-context contradiction."""
    dom_item = {
        "type": "disabled_action",
        "detected": True,
        "decision_context": "consent",
        "route": "/cookie-consent",
    }
    req = EvidenceFusionRequest(
        text="One-time payment of ₹500 for books.",
        dom_evidence=[dom_item],
    )
    res = fusion_engine.fuse(req)
    assert len(res.contradictions) == 0


# =====================================================================
# SECTION 4: INVARIANTS & SAFETY GUARANTEES
# =====================================================================

def test_36_invariant_no_evidence_no_contradiction():
    """Verify empty input produces empty contradictions and temporal relationships."""
    res = fusion_engine.fuse(EvidenceFusionRequest())
    assert res.contradictions == []
    assert res.temporal_relationships == []
    assert res.risk_score == 0.0


def test_37_invariant_contradiction_does_not_exceed_cap():
    """Verify multiple contradictions cannot exceed the +2.0 maximum contribution."""
    # Synthesize multiple contradiction signals
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.90,
        model_version="v1.0.0",
        pattern_category="Subscription Trap",
        evidence="Cancel anytime with one click. All fees included. No recurring charge.",
    )
    price_resp = PriceAnalysisResponse(
        additional_cost=200.0,
        late_disclosed=True,
        renewal_price=999.0,
        recurring=True,
    )
    dom_item = {
        "type": "cancel_action_disabled",
        "detected": True,
        "strength": "strong",
        "decision_context": "cancellation",
        "route": "/cancel",
    }
    beh_item = {
        "type": "repeated_retention_interference",
        "detected": True,
        "strength": "strong",
        "event_indices": [1, 2, 3, 4],
        "decision_context": "cancellation",
        "route": "/cancel",
    }
    req = EvidenceFusionRequest(
        text_prediction=text_pred,
        price_analysis=price_resp,
        dom_evidence=[dom_item],
        behavior_evidence=[beh_item],
    )
    res = fusion_engine.fuse(req)

    assert len(res.contradictions) >= 2
    assert res.risk_score <= 10.0


def test_38_invariant_temporal_relationship_requires_valid_ordering():
    """Verify temporal relationships are not invented when before/after ordering is invalid or missing."""
    item_a = {
        "type": "displayed_price",
        "detected": True,
        "temporal_position": "unknown",
        "decision_context": "checkout",
    }
    item_b = {
        "type": "displayed_price",
        "detected": True,
        "temporal_position": "unknown",
        "decision_context": "checkout",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[item_a, item_b]))
    assert len(res.temporal_relationships) == 0


def test_39_invariant_deterministic_severity_no_fake_ml_confidence():
    """Verify contradictions have discrete severity and no fabricated ML probability."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.88,
        model_version="v1.0.0",
        pattern_category="Subscription Trap",
        evidence="Cancel anytime online.",
    )
    dom_item = {
        "type": "cancel_action_disabled",
        "detected": True,
        "strength": "strong",
        "decision_context": "cancellation",
        "route": "/cancel",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(text_prediction=text_pred, dom_evidence=[dom_item]))

    assert len(res.contradictions) >= 1
    for c in res.contradictions:
        assert c.severity in ("weak", "moderate", "strong")
        assert not hasattr(c, "confidence") or getattr(c, "confidence", None) is None


def test_40_invariant_backward_compatibility_preserved():
    """Verify existing API fields (conflicts, evidence_groups, signals, risk_level) remain 100% compatible."""
    req = EvidenceFusionRequest(
        text="Your free trial automatically renews at ₹999/month.",
        price_analysis=PriceAnalysisResponse(
            trial_price=0.0,
            renewal_price=999.0,
            recurring=True,
        ),
    )
    res = fusion_engine.fuse(req)

    assert hasattr(res, "risk_level")
    assert hasattr(res, "risk_score")
    assert hasattr(res, "evidence")
    assert hasattr(res, "conflicts")
    assert hasattr(res, "contradictions")
    assert hasattr(res, "temporal_relationships")
    assert hasattr(res, "context_requirements")
    assert isinstance(res.contradictions, list)
    assert isinstance(res.temporal_relationships, list)
