"""tests/test_phase9_0_1_true_fusion.py
Phase 9.0.1: True Text + Price Fusion Test Suite.

Validates the strict separation of financial information from dark patterns:
1. plain price only
2. monthly price only
3. free trial + renewal without text predictor risk
4. subscription text + renewal
5. subscription text + trial + renewal
6. urgency + ordinary price
7. scarcity + ordinary price
8. social proof + ordinary price
9. drip pricing text + additional fee
10. drip pricing text + late disclosure
11. additional fee without text support
12. price increase only
13. price decrease only
14. context-required text + price
15. text prediction = 0 + price
16. duplicate price evidence
17. multiple unrelated findings
18. benign product page
19. no evidence
20. contradiction case
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas import PredictResponse
from backend.schemas.evidence import EvidenceFusionRequest, EvidenceItem
from backend.schemas.price import DisplayedPrice, PriceAnalysisResponse
from backend.services.evidence_fusion import EvidenceFusionEngine
from backend.services.explanation_engine import ConsumerExplanationEngine

client = TestClient(app)
fusion_engine = EvidenceFusionEngine()
explanation_engine = ConsumerExplanationEngine()


# --------------------------------------------------------------------------
# 1. Plain Price Only
# --------------------------------------------------------------------------
def test_01_plain_price_only():
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=49999.0, currency="INR"),
        currency="INR",
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern is None
    assert res.potential_pattern is None
    assert res.is_corroborated is False
    assert res.risk_level == "LOW"
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 2. Monthly Price Only
# --------------------------------------------------------------------------
def test_02_monthly_price_only():
    price_resp = PriceAnalysisResponse(
        renewal_price=999.0,
        renewal_currency="INR",
        billing_period="month",
        recurring=True,
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern is None
    assert res.potential_pattern == "subscription_risk"
    assert res.is_corroborated is False
    assert res.risk_level in ["LOW", "MEDIUM"]
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 3. Free Trial + Renewal Without Text Predictor Risk
# --------------------------------------------------------------------------
def test_03_free_trial_and_renewal_without_text_risk():
    text_pred = PredictResponse(
        prediction=0,
        label="not_dark_pattern",
        confidence=0.15,
        model_version="ClauseGuard-Text-V3",
    )
    price_resp = PriceAnalysisResponse(
        trial_price=0.0,
        trial_duration_days=7,
        renewal_price=999.0,
        renewal_currency="INR",
        billing_period="month",
        recurring=True,
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern is None
    assert res.potential_pattern == "subscription_risk"
    assert res.is_corroborated is False
    assert res.risk_level in ["LOW", "MEDIUM"]
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 4. Subscription Text + Renewal
# --------------------------------------------------------------------------
def test_04_subscription_text_and_renewal():
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.90,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Subscription Trap",
        evidence="Your trial automatically renews at ₹999/month.",
    )
    price_resp = PriceAnalysisResponse(
        renewal_price=999.0,
        renewal_currency="INR",
        billing_period="month",
        recurring=True,
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern == "subscription_trap"
    assert res.potential_pattern == "subscription_trap"
    assert res.is_corroborated is True
    assert res.risk_level in ["HIGH", "CRITICAL"]
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 5. Subscription Text + Trial + Renewal
# --------------------------------------------------------------------------
def test_05_subscription_text_trial_renewal():
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.92,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Subscription Trap",
        evidence="Your 7-day free trial automatically renews into an ongoing subscription.",
    )
    price_resp = PriceAnalysisResponse(
        trial_price=0.0,
        trial_duration_days=7,
        renewal_price=999.0,
        renewal_currency="INR",
        billing_period="month",
        recurring=True,
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern == "subscription_trap"
    assert res.potential_pattern == "subscription_trap"
    assert res.is_corroborated is True
    assert res.risk_level in ["HIGH", "CRITICAL"]
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 6. Urgency + Ordinary Price
# --------------------------------------------------------------------------
def test_06_urgency_and_ordinary_price():
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.88,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Urgency",
        evidence="Limited time offer! Buy now for ₹999.",
    )
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=999.0, currency="INR"),
        currency="INR",
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern == "urgency"
    assert res.potential_pattern == "urgency"
    assert res.is_corroborated is False
    assert res.risk_level in ["LOW", "MEDIUM"]
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 7. Scarcity + Ordinary Price
# --------------------------------------------------------------------------
def test_07_scarcity_and_ordinary_price():
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.85,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Scarcity",
        evidence="Only 2 items left — ₹999.",
    )
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=999.0, currency="INR"),
        currency="INR",
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern == "scarcity"
    assert res.potential_pattern == "scarcity"
    assert res.is_corroborated is False
    assert res.risk_level in ["LOW", "MEDIUM"]
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 8. Social Proof + Ordinary Price
# --------------------------------------------------------------------------
def test_08_social_proof_and_ordinary_price():
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.80,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Social Proof",
        evidence="1,249 people bought this today. ₹999.",
    )
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=999.0, currency="INR"),
        currency="INR",
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern == "social_proof"
    assert res.potential_pattern == "social_proof"
    assert res.is_corroborated is False
    assert res.risk_level in ["LOW", "MEDIUM"]
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 9. Drip Pricing Text + Additional Fee (Without Late Disclosure)
# --------------------------------------------------------------------------
def test_09_drip_pricing_text_and_additional_fee():
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.85,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Drip Pricing",
        evidence="Processing and handling fees apply.",
    )
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=499.0, currency="INR"),
        additional_cost=79.0,
        additional_costs=79.0,
        late_disclosed=False,
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern == "drip_pricing"
    assert res.potential_pattern == "drip_pricing"
    assert res.is_corroborated is False
    assert res.risk_level in ["LOW", "MEDIUM"]
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 10. Drip Pricing Text + Late Disclosure
# --------------------------------------------------------------------------
def test_10_drip_pricing_text_and_late_disclosure():
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.91,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Drip Pricing",
        evidence="A processing fee will be revealed at checkout.",
    )
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=499.0, currency="INR"),
        additional_cost=79.0,
        additional_costs=79.0,
        late_disclosed=True,
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern == "drip_pricing"
    assert res.potential_pattern == "drip_pricing"
    assert res.is_corroborated is True
    assert res.risk_level in ["HIGH", "CRITICAL"]
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 11. Additional Fee Without Text Support
# --------------------------------------------------------------------------
def test_11_additional_fee_without_text_support():
    text_pred = PredictResponse(
        prediction=0,
        label="not_dark_pattern",
        confidence=0.10,
        model_version="ClauseGuard-Text-V3",
    )
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=499.0, currency="INR"),
        additional_cost=79.0,
        additional_costs=79.0,
        known_total=578.0,
        late_disclosed=False,
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern is None
    assert res.potential_pattern == "price_disclosure_risk"
    assert res.is_corroborated is False
    assert res.risk_level in ["LOW", "MEDIUM"]
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 12. Price Increase Only
# --------------------------------------------------------------------------
def test_12_price_increase_only():
    price_resp = PriceAnalysisResponse(
        previous_price=999.0,
        current_price=1299.0,
        price_change=300.0,
        price_change_percentage=30.03,
        price_change_detected=True,
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern is None
    assert res.potential_pattern == "price_change"
    assert res.is_corroborated is False
    assert res.risk_level == "LOW"
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 13. Price Decrease Only
# --------------------------------------------------------------------------
def test_13_price_decrease_only():
    price_resp = PriceAnalysisResponse(
        previous_price=1299.0,
        current_price=999.0,
        price_change=-300.0,
        price_change_percentage=-23.09,
        price_change_detected=True,
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern is None
    assert res.potential_pattern == "price_change"
    assert res.is_corroborated is False
    assert res.risk_level == "LOW"
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 14. Context-Required Text + Price
# --------------------------------------------------------------------------
def test_14_context_required_text_and_price():
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.55,
        model_version="ClauseGuard-Text-V3",
        requires_context=True,
        pattern_category="Urgency",
        evidence="Limited time offer — ₹999",
    )
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=999.0, currency="INR"),
        currency="INR",
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern is None
    assert res.potential_pattern == "urgency"
    assert res.is_corroborated is False
    assert res.risk_level == "LOW"
    assert res.requires_context is True


# --------------------------------------------------------------------------
# 15. Text Prediction = 0 + Price
# --------------------------------------------------------------------------
def test_15_text_prediction_zero_and_price():
    text_pred = PredictResponse(
        prediction=0,
        label="not_dark_pattern",
        confidence=0.08,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
    )
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=999.0, currency="INR"),
        currency="INR",
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern is None
    assert res.potential_pattern is None
    assert res.is_corroborated is False
    assert res.risk_level == "LOW"
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 16. Duplicate Price Evidence
# --------------------------------------------------------------------------
def test_16_duplicate_price_evidence():
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=999.0, currency="INR"),
        renewal_price=999.0,
        renewal_currency="INR",
        billing_period="month",
        recurring=True,
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    # Displayed price identical to renewal in trial/renewal is deduped
    assert res.financial_signal is True
    assert res.dark_pattern is None
    assert res.potential_pattern == "subscription_risk"
    assert res.is_corroborated is False
    assert res.risk_level in ["LOW", "MEDIUM"]
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 17. Multiple Unrelated Findings
# --------------------------------------------------------------------------
def test_17_multiple_unrelated_findings():
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.86,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Urgency",
        evidence="Hurry! Offer ends tonight!",
    )
    price_resp = PriceAnalysisResponse(
        renewal_price=999.0,
        renewal_currency="INR",
        billing_period="month",
        recurring=True,
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern == "urgency"
    assert res.potential_pattern == "urgency"
    # Ordinary subscription pricing does NOT corroborate urgency
    assert res.is_corroborated is False
    assert res.risk_level in ["LOW", "MEDIUM"]
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 18. Benign Product Page
# --------------------------------------------------------------------------
def test_18_benign_product_page():
    req = EvidenceFusionRequest(
        text="Samsung TV — ₹49,999 \n 30-day return policy."
    )
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern is None
    assert res.potential_pattern is None
    assert res.is_corroborated is False
    assert res.risk_level == "LOW"
    assert res.requires_context is False

    # Explanation engine must not declare dark pattern
    exp = explanation_engine.explain_fusion_response(res)
    assert exp.risk_status in ("financial_notice", "no_strong_signal")
    assert "dark pattern" not in exp.title.lower()


# --------------------------------------------------------------------------
# 19. No Evidence
# --------------------------------------------------------------------------
def test_19_no_evidence():
    req = EvidenceFusionRequest()
    res = fusion_engine.fuse(req)

    assert res.financial_signal is False
    assert res.dark_pattern is None
    assert res.potential_pattern is None
    assert res.is_corroborated is False
    assert res.risk_level == "LOW"
    assert res.requires_context is False


# --------------------------------------------------------------------------
# 20. Contradiction Case
# --------------------------------------------------------------------------
def test_20_contradiction_case():
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.82,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Subscription Trap",
        evidence="free trial offer",
    )
    price_resp = PriceAnalysisResponse(
        trial_price=99.0,  # Paid trial contradiction
        trial_currency="INR",
        renewal_price=999.0,
        renewal_currency="INR",
        recurring=True,
    )
    req = EvidenceFusionRequest(
        text="Start your free trial today",
        text_prediction=text_pred,
        price_analysis=price_resp,
    )
    res = fusion_engine.fuse(req)

    assert len(res.conflicts) >= 1
    assert res.financial_signal is True
    assert res.dark_pattern == "subscription_trap"
    assert res.potential_pattern == "subscription_trap"
    assert res.is_corroborated is True
    assert res.requires_context is False
