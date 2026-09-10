"""tests/test_phase10_evidence_fusion_multimodal.py
Phase B5.2 Active Multimodal Evidence Fusion Test Suite.

Verifies that DOM and Behavior evidence actively participate in Evidence Fusion
while remaining deterministic, explainable, conservative, and backward-compatible.

Sections:
1. Multi-modal Combinations A through J
2. DOM Positives (5 scenarios)
3. Behavior Positives (5 scenarios)
4. Hard Negatives (15 scenarios)
5. Test Invariants (determinism, no fake ML confidence, boundedness, traceability)
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas import PredictResponse
from backend.schemas.evidence import EvidenceFusionRequest, EvidenceItem
from backend.schemas.price import DisplayedPrice, PriceAnalysisResponse
from backend.services.evidence_fusion import EvidenceFusionEngine

client = TestClient(app)
fusion_engine = EvidenceFusionEngine()


# =====================================================================
# SECTION 1: COMBINATIONS A THROUGH J
# =====================================================================

def test_combination_a_dom_only():
    """A. DOM only: Strong cancellation obstruction signal produces conservative MEDIUM risk."""
    dom_item = {
        "type": "cancel_action_disabled",
        "detected": True,
        "strength": "strong",
        "reason": "Cancellation button is rendered in a disabled state during account flow",
        "element_ref": "BTN_CANCEL_DISABLED",
        "event_indices": [5],
        "route": "/account/cancel",
        "decision_context": "cancellation",
    }
    req = EvidenceFusionRequest(dom_evidence=[dom_item])
    res = fusion_engine.fuse(req)

    assert len(res.evidence) == 1
    assert res.evidence[0].source == "dom"
    assert res.evidence[0].type == "cancel_action_disabled"
    assert res.evidence[0].element_ref == "BTN_CANCEL_DISABLED"
    assert res.evidence[0].model_confidence is None  # Never fake ML probability
    assert res.evidence[0].strength == "strong"
    assert res.risk_level == "MEDIUM"  # Single source never exceeds MEDIUM
    assert res.risk_score == 3.0
    assert res.risk_detected is True
    assert res.primary_pattern == "Obstruction"
    assert res.is_corroborated is False


def test_combination_b_behavior_only():
    """B. Behavior only: Strong repeated retention loop produces conservative MEDIUM risk."""
    beh_item = {
        "type": "repeated_retention_interference",
        "detected": True,
        "strength": "strong",
        "reason": "Observed 3 consecutive retention dialogue prompts rejecting cancellation",
        "event_indices": [4, 7, 9],
        "route": "/membership/cancel",
        "decision_context": "cancellation",
    }
    req = EvidenceFusionRequest(behavior_evidence=[beh_item])
    res = fusion_engine.fuse(req)

    assert len(res.evidence) == 1
    assert res.evidence[0].source == "behavior"
    assert res.evidence[0].type == "repeated_retention_interference"
    assert res.evidence[0].event_indices == [4, 7, 9]
    assert res.evidence[0].model_confidence is None
    assert res.risk_level == "MEDIUM"
    assert res.risk_score == 3.0
    assert res.risk_detected is True
    assert res.primary_pattern == "Obstruction"
    assert res.is_corroborated is False


def test_combination_c_text_and_dom():
    """C. Text + DOM: Text subscription trap corroborated by DOM cancellation deemphasis."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.88,
        model_version="ClauseGuard-Text-V3",
        pattern_category="Subscription Trap",
        evidence="automatically renews monthly until cancelled",
    )
    dom_item = {
        "type": "action_visual_deemphasis",
        "detected": True,
        "strength": "strong",
        "reason": "Cancel button styled with 1.2:1 contrast and 0.25 opacity",
        "element_ref": "BTN_CANCEL",
        "event_indices": [3],
        "route": "/cancel",
        "decision_context": "cancellation",
    }
    req = EvidenceFusionRequest(text_prediction=text_pred, dom_evidence=[dom_item])
    res = fusion_engine.fuse(req)

    assert res.is_corroborated is True
    assert res.risk_level in ["HIGH", "CRITICAL"]
    assert res.risk_score >= 8.0  # Text (2.0) + DOM (3.0) + Corrob (3.0)
    assert res.primary_pattern == "Subscription Trap"
    assert any(e.source == "dom" for e in res.supporting_evidence)
    assert any(e.source == "text" for e in res.supporting_evidence)


def test_combination_d_text_and_behavior():
    """D. Text + Behavior: Subscription text corroborated by behavioral retention interference."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.89,
        model_version="ClauseGuard-Text-V3",
        pattern_category="Subscription Trap",
        evidence="renews automatically at ₹999/month",
    )
    beh_item = {
        "type": "repeated_retention_interference",
        "detected": True,
        "strength": "strong",
        "reason": "Repeated retention offers intercept cancellation intent",
        "event_indices": [6, 8],
        "route": "/cancel",
        "decision_context": "cancellation",
    }
    req = EvidenceFusionRequest(text_prediction=text_pred, behavior_evidence=[beh_item])
    res = fusion_engine.fuse(req)

    assert res.is_corroborated is True
    assert res.risk_level in ["HIGH", "CRITICAL"]
    assert res.primary_pattern == "Subscription Trap"
    assert any(e.source == "behavior" for e in res.supporting_evidence)


def test_combination_e_price_and_dom():
    """E. Price + DOM: Price late disclosure corroborated by post-action fee DOM addition."""
    price_resp = PriceAnalysisResponse(
        additional_cost=250.0,
        late_disclosed=True,
        currency="INR",
    )
    dom_item = {
        "type": "post_action_fee_added",
        "detected": True,
        "strength": "strong",
        "reason": "Processing fee added to total after clicking Continue",
        "element_ref": "LINE_FEE",
        "event_indices": [12],
        "route": "/checkout",
        "decision_context": "checkout",
    }
    req = EvidenceFusionRequest(price_analysis=price_resp, dom_evidence=[dom_item])
    res = fusion_engine.fuse(req)

    assert res.is_corroborated is True
    assert res.risk_level in ["HIGH", "CRITICAL"]
    assert res.primary_pattern == "Drip Pricing"
    assert any(e.source == "dom" for e in res.supporting_evidence)
    assert any(e.source == "price" for e in res.supporting_evidence)


def test_combination_f_price_and_behavior():
    """F. Price + Behavior: Recurring price corroborated by cancellation obstruction behavior."""
    price_resp = PriceAnalysisResponse(
        renewal_price=799.0,
        renewal_currency="INR",
        recurring=True,
    )
    beh_item = {
        "type": "cancellation_obstruction",
        "detected": True,
        "strength": "strong",
        "reason": "Multi-step obstruction loop prevents completing cancellation of recurring subscription",
        "event_indices": [10, 12, 14],
        "route": "/cancel",
        "decision_context": "cancellation",
    }
    req = EvidenceFusionRequest(price_analysis=price_resp, behavior_evidence=[beh_item])
    res = fusion_engine.fuse(req)

    assert res.is_corroborated is True
    assert res.risk_level in ["HIGH", "CRITICAL"]
    assert res.primary_pattern == "Subscription Trap"
    assert any(e.source == "behavior" for e in res.supporting_evidence)
    assert any(e.source == "price" for e in res.supporting_evidence)


def test_combination_g_text_price_and_dom():
    """G. Text + Price + DOM: 3 modalities corroborating subscription trap."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.91,
        model_version="ClauseGuard-Text-V3",
        pattern_category="Subscription Trap",
        evidence="7-day free trial renews automatically at ₹999/month",
    )
    price_resp = PriceAnalysisResponse(
        trial_price=0.0,
        trial_duration_days=7,
        renewal_price=999.0,
        renewal_currency="INR",
        recurring=True,
    )
    dom_item = {
        "type": "cancel_action_visually_deemphasized",
        "detected": True,
        "strength": "strong",
        "reason": "Cancellation button is rendered as tiny unstyled text",
        "element_ref": "SPAN_CANCEL",
        "decision_context": "cancellation",
    }
    req = EvidenceFusionRequest(
        text_prediction=text_pred,
        price_analysis=price_resp,
        dom_evidence=[dom_item],
    )
    res = fusion_engine.fuse(req)

    assert res.is_corroborated is True
    assert res.risk_level == "CRITICAL"
    assert res.risk_score >= 10.0
    assert res.primary_pattern == "Subscription Trap"
    assert len({e.source for e in res.supporting_evidence}) >= 3


def test_combination_h_text_price_and_behavior():
    """H. Text + Price + Behavior: 3 modalities corroborating subscription trap."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.90,
        model_version="ClauseGuard-Text-V3",
        pattern_category="Subscription Trap",
        evidence="automatically renews at ₹999/month",
    )
    price_resp = PriceAnalysisResponse(
        renewal_price=999.0,
        renewal_currency="INR",
        recurring=True,
    )
    beh_item = {
        "type": "repeated_retention_interference",
        "detected": True,
        "strength": "strong",
        "reason": "Observed 3 retention interventions",
        "event_indices": [5, 8, 11],
        "decision_context": "cancellation",
    }
    req = EvidenceFusionRequest(
        text_prediction=text_pred,
        price_analysis=price_resp,
        behavior_evidence=[beh_item],
    )
    res = fusion_engine.fuse(req)

    assert res.is_corroborated is True
    assert res.risk_level == "CRITICAL"
    assert res.primary_pattern == "Subscription Trap"


def test_combination_i_text_dom_and_behavior():
    """I. Text + DOM + Behavior: Non-price 3-modality corroboration."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.88,
        model_version="ClauseGuard-Text-V3",
        pattern_category="Subscription Trap",
        evidence="renews automatically until cancelled",
    )
    dom_item = {
        "type": "disabled_action",
        "detected": True,
        "strength": "strong",
        "reason": "Cancellation button is disabled",
        "decision_context": "cancellation",
    }
    beh_item = {
        "type": "cancellation_obstruction",
        "detected": True,
        "strength": "strong",
        "reason": "User prevented from finishing cancellation flow",
        "event_indices": [7, 9],
        "decision_context": "cancellation",
    }
    req = EvidenceFusionRequest(
        text_prediction=text_pred,
        dom_evidence=[dom_item],
        behavior_evidence=[beh_item],
    )
    res = fusion_engine.fuse(req)

    assert res.is_corroborated is True
    assert res.risk_level == "CRITICAL"
    assert res.primary_pattern == "Subscription Trap"


def test_combination_j_text_price_dom_and_behavior():
    """J. Text + Price + DOM + Behavior: All 4 modalities participating together."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.92,
        model_version="ClauseGuard-Text-V3",
        pattern_category="Subscription Trap",
        evidence="auto-renews at ₹999/month",
    )
    price_resp = PriceAnalysisResponse(
        renewal_price=999.0,
        renewal_currency="INR",
        recurring=True,
    )
    dom_item = {
        "type": "action_visual_deemphasis",
        "detected": True,
        "strength": "strong",
        "reason": "De-emphasized cancel button",
        "decision_context": "cancellation",
    }
    beh_item = {
        "type": "repeated_retention_interference",
        "detected": True,
        "strength": "strong",
        "reason": "Repeated retention interference observed",
        "decision_context": "cancellation",
    }
    req = EvidenceFusionRequest(
        text_prediction=text_pred,
        price_analysis=price_resp,
        dom_evidence=[dom_item],
        behavior_evidence=[beh_item],
    )
    res = fusion_engine.fuse(req)

    assert res.is_corroborated is True
    assert res.risk_level == "CRITICAL"
    assert res.primary_pattern == "Subscription Trap"
    assert len({e.source for e in res.supporting_evidence}) >= 4


# =====================================================================
# SECTION 2: DOM POSITIVES (5 SCENARIOS)
# =====================================================================

def test_dom_positive_1_disabled_cancel():
    """DOM Positive 1: disabled cancel in cancellation context."""
    dom_item = {
        "type": "cancel_action_disabled",
        "detected": True,
        "strength": "strong",
        "reason": "Cancel button disabled until survey completed",
        "element_ref": "BTN_CONFIRM_CANCEL",
        "decision_context": "cancellation",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[dom_item]))
    assert res.risk_detected is True
    assert res.primary_pattern == "Obstruction"
    assert res.risk_level == "MEDIUM"
    assert any("dom:cancel_action_disabled" in s for s in res.signals)


def test_dom_positive_2_hidden_cancel():
    """DOM Positive 2: hidden cancel + visible keep membership."""
    dom_item = {
        "type": "hidden_alternative",
        "detected": True,
        "strength": "strong",
        "reason": "Cancel membership link hidden with display:none while Keep Membership is prominent",
        "element_ref": "A_CANCEL_HIDDEN",
        "decision_context": "cancellation",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[dom_item]))
    assert res.risk_detected is True
    assert res.primary_pattern == "Obstruction"
    assert res.evidence[0].element_ref == "A_CANCEL_HIDDEN"


def test_dom_positive_3_preselected_paid_addon():
    """DOM Positive 3: preselected paid add-on during checkout."""
    dom_item = {
        "type": "preselected_option",
        "detected": True,
        "strength": "strong",
        "reason": "Checked baggage protection insurance box pre-selected by default",
        "element_ref": "CHK_PROTECT",
        "decision_context": "checkout",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[dom_item]))
    assert res.risk_detected is True
    assert res.primary_pattern == "Sneaking"
    assert res.risk_level == "MEDIUM"


def test_dom_positive_4_strong_visual_deemphasis():
    """DOM Positive 4: strong action visual deemphasis during cancellation."""
    dom_item = {
        "type": "action_visual_deemphasis",
        "detected": True,
        "strength": "strong",
        "reason": "Cancel option rendered at 1.1:1 contrast ratio against gray backdrop",
        "element_ref": "BTN_UNSUBSCRIBE",
        "decision_context": "cancellation",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[dom_item]))
    assert res.risk_detected is True
    assert res.primary_pattern == "Obstruction"


def test_dom_positive_5_post_action_fee():
    """DOM Positive 5: post-action fee + checkout."""
    dom_item = {
        "type": "post_action_fee_added",
        "detected": True,
        "strength": "strong",
        "reason": "₹150 packaging surcharge added after user clicked Proceed to Payment",
        "element_ref": "FEE_SURCHARGE",
        "decision_context": "checkout",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[dom_item]))
    assert res.risk_detected is True
    assert res.primary_pattern == "Drip Pricing"


# =====================================================================
# SECTION 3: BEHAVIOR POSITIVES (5 SCENARIOS)
# =====================================================================

def test_behavior_positive_1_repeated_retention():
    """Behavior Positive 1: repeated retention interference."""
    beh_item = {
        "type": "repeated_retention_interference",
        "detected": True,
        "strength": "strong",
        "reason": "Multiple discount offers repeatedly intercepting cancellation flow",
        "event_indices": [2, 5, 8],
        "decision_context": "cancellation",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(behavior_evidence=[beh_item]))
    assert res.risk_detected is True
    assert res.primary_pattern == "Obstruction"
    assert any("behavior:repeated_retention_interference" in s for s in res.signals)


def test_behavior_positive_2_cancellation_obstruction():
    """Behavior Positive 2: cancellation obstruction."""
    beh_item = {
        "type": "cancellation_obstruction",
        "detected": True,
        "strength": "strong",
        "reason": "Multi-page forced diversion away from cancellation confirmation",
        "event_indices": [3, 4, 7],
        "decision_context": "cancellation",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(behavior_evidence=[beh_item]))
    assert res.risk_detected is True
    assert res.primary_pattern == "Obstruction"


def test_behavior_positive_3_repeated_confirmation():
    """Behavior Positive 3: repeated confirmation pressure."""
    beh_item = {
        "type": "repeated_confirmation_pressure",
        "detected": True,
        "strength": "strong",
        "reason": "User forced through 4 sequential 'Are you sure?' confirmation steps",
        "event_indices": [6, 9, 12, 15],
        "decision_context": "cancellation",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(behavior_evidence=[beh_item]))
    assert res.risk_detected is True
    assert res.primary_pattern == "Obstruction"


def test_behavior_positive_4_forced_action_sequence():
    """Behavior Positive 4: forced action sequence."""
    beh_item = {
        "type": "forced_action_sequence",
        "detected": True,
        "strength": "strong",
        "reason": "User forced to fill 10-question mandatory survey before cancel button unlocks",
        "event_indices": [5, 6, 7],
        "decision_context": "cancellation",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(behavior_evidence=[beh_item]))
    assert res.risk_detected is True
    assert res.primary_pattern == "Forced Action"


def test_behavior_positive_5_cancellation_abandonment():
    """Behavior Positive 5: cancellation abandonment."""
    beh_item = {
        "type": "cancellation_abandonment",
        "detected": True,
        "strength": "strong",
        "reason": "User abandoned flow after 8 unsuccessful cancellation navigation steps",
        "event_indices": [1, 2, 4, 6, 8],
        "decision_context": "cancellation",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(behavior_evidence=[beh_item]))
    assert res.risk_detected is True
    assert res.primary_pattern == "Obstruction"


# =====================================================================
# SECTION 4: HARD NEGATIVES (15 SCENARIOS)
# =====================================================================

def test_hard_negative_1_normal_disabled_loading_button():
    """HN 1: normal disabled loading button produces LOW risk and no dark pattern."""
    dom_item = {
        "type": "disabled_action",
        "detected": False,  # Not flagged as manipulative
        "strength": "weak",
        "reason": "Submit button temporarily disabled while form submission is in-flight",
        "element_ref": "BTN_SUBMIT_LOADING",
        "decision_context": "checkout",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[dom_item]))
    assert res.risk_level == "LOW"
    assert res.risk_detected is False
    assert res.risk_score == 0.0


def test_hard_negative_2_normal_continue_back():
    """HN 2: normal Continue/Back navigation."""
    dom_item = {
        "type": "action_size_asymmetry",
        "detected": False,
        "strength": "insufficient",
        "reason": "Standard primary Continue and secondary Back buttons",
        "decision_context": "checkout",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[dom_item]))
    assert res.risk_level == "LOW"
    assert res.risk_detected is False


def test_hard_negative_3_normal_save_cancel():
    """HN 3: normal Save/Cancel settings dialog."""
    dom_item = {
        "type": "confirmation_ui",
        "detected": False,
        "strength": "insufficient",
        "reason": "Standard settings Save Changes and Cancel buttons",
        "decision_context": "dialog",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[dom_item]))
    assert res.risk_level == "LOW"
    assert res.risk_detected is False


def test_hard_negative_4_normal_survey():
    """HN 4: normal optional survey."""
    beh_item = {
        "type": "required_survey",
        "detected": False,
        "strength": "insufficient",
        "reason": "Benign optional 1-question feedback survey",
        "decision_context": "dialog",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(behavior_evidence=[beh_item]))
    assert res.risk_level == "LOW"
    assert res.risk_detected is False


def test_hard_negative_5_legitimate_discount():
    """HN 5: legitimate coupon discount."""
    price_resp = PriceAnalysisResponse(
        discount_amount=100.0,
        currency="INR",
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(price_analysis=price_resp))
    assert res.risk_level == "LOW"
    assert res.risk_detected is False


def test_hard_negative_6_legitimate_multistep_cancellation():
    """HN 6: legitimate 2-step cancellation without loops."""
    beh_item = {
        "type": "cancellation_obstruction",
        "detected": False,
        "strength": "insufficient",
        "reason": "Standard 2-step cancellation flow with immediate progress",
        "decision_context": "cancellation",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(behavior_evidence=[beh_item]))
    assert res.risk_level == "LOW"
    assert res.risk_detected is False


def test_hard_negative_7_normal_confirmation():
    """HN 7: normal balanced confirmation dialog."""
    dom_item = {
        "type": "asymmetric_confirmation",
        "detected": False,
        "strength": "insufficient",
        "reason": "Balanced Yes/No dialog for deleting an item",
        "decision_context": "dialog",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[dom_item]))
    assert res.risk_level == "LOW"
    assert res.risk_detected is False


def test_hard_negative_8_normal_checkbox_default():
    """HN 8: normal benign checkbox default (Remember Me)."""
    dom_item = {
        "type": "preselected_option",
        "detected": False,
        "strength": "insufficient",
        "reason": "Remember Me checkbox on login screen",
        "decision_context": "consent",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[dom_item]))
    assert res.risk_level == "LOW"
    assert res.risk_detected is False


def test_hard_negative_9_normal_checkout_option():
    """HN 9: normal shipping selection option."""
    dom_item = {
        "type": "preselected_option",
        "detected": False,
        "strength": "insufficient",
        "reason": "Free standard shipping selected by default",
        "decision_context": "checkout",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[dom_item]))
    assert res.risk_level == "LOW"
    assert res.risk_detected is False


def test_hard_negative_10_unrelated_dom_signal_different_context():
    """HN 10: unrelated DOM signal in different context does not corroborate subscription text."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.85,
        model_version="ClauseGuard-Text-V3",
        pattern_category="Subscription Trap",
        evidence="automatically renews every month",
    )
    # DOM signal belongs to cookie consent, NOT cancellation or subscription!
    dom_item = {
        "type": "action_visual_deemphasis",
        "detected": True,
        "strength": "strong",
        "reason": "Cookie reject button de-emphasized",
        "element_ref": "BTN_REJECT_COOKIES",
        "decision_context": "consent",  # Unrelated context!
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(text_prediction=text_pred, dom_evidence=[dom_item]))

    # Must NOT corroborate into subscription trap!
    sub_groups = [g for g in res.evidence_groups if g.pattern == "subscription_trap"]
    if sub_groups:
        assert sub_groups[0].corroborated is False


def test_hard_negative_11_unrelated_behavior_signal():
    """HN 11: unrelated behavior signal does not corroborate text."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.85,
        model_version="ClauseGuard-Text-V3",
        pattern_category="Subscription Trap",
        evidence="renews automatically",
    )
    # Behavior signal in unrelated unknown context
    beh_item = {
        "type": "backtracking_loop",
        "detected": True,
        "strength": "strong",
        "reason": "User searched back and forth in product catalog",
        "decision_context": "unknown",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(text_prediction=text_pred, behavior_evidence=[beh_item]))

    sub_groups = [g for g in res.evidence_groups if g.pattern == "subscription_trap"]
    if sub_groups:
        assert sub_groups[0].corroborated is False


def test_hard_negative_12_text_requires_context_with_strong_dom():
    """HN 12: text requires_context + strong DOM: DOM is NOT suppressed!"""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.55,
        model_version="ClauseGuard-Text-V3",
        requires_context=True,
        pattern_category="Subscription Trap",
        evidence="terms and conditions apply",
    )
    dom_item = {
        "type": "cancel_action_disabled",
        "detected": True,
        "strength": "strong",
        "reason": "Cancellation button is disabled during account cancellation",
        "element_ref": "BTN_CANCEL",
        "decision_context": "cancellation",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(text_prediction=text_pred, dom_evidence=[dom_item]))

    # Text requires context, but strong DOM evidence must NOT be suppressed!
    assert res.requires_context is True
    assert res.context_requirements["text"] is True
    assert res.context_requirements["dom"] is False
    assert res.risk_detected is True
    assert res.primary_pattern == "Obstruction"
    assert res.risk_level == "MEDIUM"


def test_hard_negative_13_text_requires_context_with_strong_behavior():
    """HN 13: text requires_context + strong Behavior: Behavior is NOT suppressed!"""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.55,
        model_version="ClauseGuard-Text-V3",
        requires_context=True,
        pattern_category="Subscription Trap",
        evidence="membership rules apply",
    )
    beh_item = {
        "type": "repeated_retention_interference",
        "detected": True,
        "strength": "strong",
        "reason": "Repeated aggressive retention popups preventing cancellation",
        "event_indices": [3, 6, 9],
        "decision_context": "cancellation",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(text_prediction=text_pred, behavior_evidence=[beh_item]))

    assert res.requires_context is True
    assert res.context_requirements["text"] is True
    assert res.context_requirements["behavior"] is False
    assert res.risk_detected is True
    assert res.primary_pattern == "Obstruction"
    assert res.risk_level == "MEDIUM"


def test_hard_negative_14_price_only():
    """HN 14: price only (displayed price) produces purely financial informational response."""
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=999.0, currency="INR"),
        currency="INR",
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(price_analysis=price_resp))
    assert res.financial_signal is True
    assert res.risk_level == "LOW"
    assert res.risk_score == 0.0
    assert res.risk_detected is False
    assert res.primary_pattern is None


def test_hard_negative_15_dom_only_weak_signal():
    """HN 15: DOM only weak signal produces LOW risk and no detected dark pattern."""
    dom_item = {
        "type": "action_visual_deemphasis",
        "detected": True,
        "strength": "weak",
        "reason": "Slightly lighter shade of gray on secondary link",
        "element_ref": "A_TERMS",
        "decision_context": "cancellation",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[dom_item]))
    assert res.risk_level == "LOW"
    assert res.risk_score < 3.0
    assert res.risk_detected is False
    assert res.primary_pattern is None


# =====================================================================
# SECTION 5: TEST INVARIANTS
# =====================================================================

def test_invariant_1_deterministic_results():
    """Verify identical inputs yield 100% identical fusion responses across repeated runs."""
    req = EvidenceFusionRequest(
        dom_evidence=[
            {
                "type": "cancel_action_visually_deemphasized",
                "detected": True,
                "strength": "strong",
                "reason": "Cancel button deemphasized",
                "element_ref": "BTN_CANCEL",
                "decision_context": "cancellation",
            }
        ],
        behavior_evidence=[
            {
                "type": "repeated_retention_interference",
                "detected": True,
                "strength": "strong",
                "reason": "Retention loops observed",
                "event_indices": [2, 4],
                "decision_context": "cancellation",
            }
        ],
    )
    res1 = fusion_engine.fuse(req)
    res2 = fusion_engine.fuse(req)

    assert res1.risk_level == res2.risk_level
    assert res1.risk_score == res2.risk_score
    assert res1.primary_pattern == res2.primary_pattern
    assert res1.is_corroborated == res2.is_corroborated
    assert len(res1.evidence) == len(res2.evidence)
    assert len(res1.signals) == len(res2.signals)


def test_invariant_2_no_fake_model_confidence():
    """Verify DOM and Behavior evidence items have model_confidence=None (no fabricated ML probabilities)."""
    req = EvidenceFusionRequest(
        dom_evidence=[
            {"type": "cancel_action_disabled", "strength": "strong", "detected": True}
        ],
        behavior_evidence=[
            {"type": "repeated_retention_interference", "strength": "strong", "detected": True}
        ],
    )
    res = fusion_engine.fuse(req)

    dom_items = [e for e in res.evidence if e.source == "dom"]
    beh_items = [e for e in res.evidence if e.source == "behavior"]

    assert len(dom_items) == 1
    assert dom_items[0].model_confidence is None

    assert len(beh_items) == 1
    assert beh_items[0].model_confidence is None


def test_invariant_3_strength_remains_qualitative():
    """Verify strength remains qualitative ('weak', 'moderate', 'strong', 'insufficient')."""
    req = EvidenceFusionRequest(
        dom_evidence=[
            {"type": "cancel_action_disabled", "strength": "strong", "detected": True},
            {"type": "hidden_alternative", "strength": "moderate", "detected": True},
        ]
    )
    res = fusion_engine.fuse(req)
    strengths = {e.strength for e in res.evidence}
    assert strengths.issubset({"weak", "moderate", "strong", "insufficient"})


def test_invariant_4_requires_context_remains_source_scoped():
    """Verify context_requirements preserves source granularity."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        model_version="ClauseGuard-Text-V3",
        requires_context=True,
        pattern_category="Subscription Trap",
    )
    dom_item = {"type": "cancel_action_disabled", "strength": "strong", "detected": True}
    res = fusion_engine.fuse(EvidenceFusionRequest(text_prediction=text_pred, dom_evidence=[dom_item]))

    assert isinstance(res.context_requirements, dict)
    assert res.context_requirements["text"] is True
    assert res.context_requirements["dom"] is False
    assert res.context_requirements["behavior"] is False
    assert res.context_requirements["price"] is False


def test_invariant_5_evidence_traceability_preserved():
    """Verify all metadata fields (element_ref, event_indices, route, decision_context, provenance) are preserved."""
    dom_item = {
        "type": "action_visual_deemphasis",
        "detected": True,
        "strength": "strong",
        "reason": "Tiny gray link",
        "element_ref": "LINK_CANCEL_99",
        "event_indices": [7],
        "route": "/settings/billing",
        "decision_context": "cancellation",
        "provenance": "dom_analyzer_b4_test",
    }
    beh_item = {
        "type": "repeated_confirmation_pressure",
        "detected": True,
        "strength": "strong",
        "reason": "Four sequential confirmations",
        "event_indices": [10, 12, 14, 16],
        "route": "/settings/billing/confirm",
        "decision_context": "cancellation",
        "provenance": "behavior_sequence_b3_test",
    }
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=[dom_item], behavior_evidence=[beh_item]))

    dom_res = next(e for e in res.evidence if e.source == "dom")
    assert dom_res.element_ref == "LINK_CANCEL_99"
    assert dom_res.event_indices == [7]
    assert dom_res.route == "/settings/billing"
    assert dom_res.decision_context == "cancellation"
    assert dom_res.provenance == "dom_analyzer_b4_test"

    beh_res = next(e for e in res.evidence if e.source == "behavior")
    assert beh_res.event_indices == [10, 12, 14, 16]
    assert beh_res.route == "/settings/billing/confirm"
    assert beh_res.decision_context == "cancellation"
    assert beh_res.provenance == "behavior_sequence_b3_test"


def test_invariant_6_no_risk_explosion_from_many_items():
    """Verify bounded aggregation: 10 DOM signals and 10 Behavior signals cannot explode risk score."""
    many_dom = [
        {"type": f"action_visual_deemphasis_{i}", "strength": "strong", "detected": True}
        for i in range(10)
    ]
    many_beh = [
        {"type": f"retention_friction_{i}", "strength": "strong", "detected": True}
        for i in range(10)
    ]
    res = fusion_engine.fuse(EvidenceFusionRequest(dom_evidence=many_dom, behavior_evidence=many_beh))

    # Caps: dom_score <= 3.5, beh_score <= 3.5. Corrob bonus <= 3.0.
    # Total score should not exceed ~10.0 and never explode to 60.0.
    assert res.risk_score <= 12.0
