"""tests/test_phase9_1_evidence_fusion.py
Phase 9.1: Text + Price Evidence Fusion Test Suite.

Validates deterministic combination of Text Predictor and Price Analyzer:
1. Rule A: Subscription Trap corroboration
2. Rule B: Drip Pricing / Late Fee corroboration
3. Rule C: Price Change factual signal without dark pattern verdict
4. Rule D: Renewal price without text dark pattern
5. Rule E: Normal single price (Samsung TV)
6. Rule F: Alternative pricing (tiers, options)
7. Rule G: Inclusive fees (taxes, shipping)
8. Rule H: Insufficient context handling
9. Hard Negatives (discount, identical price, price increase alone)
10. Positive Integration Cases (A, B, C, D)
11. Missing-source matrix (text-only, price-only, empty, raw text lazy evaluation)
12. API endpoint integration (/fuse-evidence)
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas import PredictResponse
from backend.schemas.evidence import (
    EvidenceFusionRequest,
    EvidenceFusionResponse,
    EvidenceItem,
)
from backend.schemas.price import DisplayedPrice, PriceAnalysisResponse
from backend.services.evidence_fusion import EvidenceFusionEngine

client = TestClient(app)
fusion_engine = EvidenceFusionEngine()


# =============================================================================
# 1. RULE A — SUBSCRIPTION TRAP CORROBORATION
# =============================================================================

def test_rule_a_subscription_trap_corroboration():
    """Rule A: Subscription trap text + renewal/trial pricing produces corroborated risk."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.88,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Subscription Trap",
        evidence="Your trial automatically renews at ₹999/month.",
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

    assert res.risk_detected is True
    assert res.primary_pattern == "Subscription Trap"
    assert res.dark_pattern == "subscription_trap"
    assert res.is_corroborated is True
    assert res.renewal_signal is True
    assert res.risk_level in ["HIGH", "CRITICAL"]
    assert res.confidence is not None and res.confidence <= 0.99
    assert any("price:renewal_price" in s for s in res.signals)
    assert any("text:pattern:Subscription Trap" in s for s in res.signals)
    assert len(res.supporting_evidence) >= 2
    assert res.consumer_consequence is not None
    assert "recurring" in res.consumer_consequence.description.lower()
    assert "999" in res.consumer_consequence.description


# =============================================================================
# 2. RULE B — DRIP PRICING / LATE FEE CORROBORATION
# =============================================================================

def test_rule_b_drip_pricing_late_fee_corroboration():
    """Rule B: Drip pricing text + late disclosure fee produces corroborated risk."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.85,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Drip Pricing",
        evidence="Mandatory processing fee revealed at checkout.",
    )
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=499.0, currency="INR"),
        additional_cost=79.0,
        additional_costs=79.0,
        known_total=578.0,
        late_disclosed=True,
        late_disclosure_detected=True,
        additional_cost_detected=True,
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.risk_detected is True
    assert res.primary_pattern == "Drip Pricing"
    assert res.dark_pattern == "drip_pricing"
    assert res.is_corroborated is True
    assert res.risk_level in ["HIGH", "CRITICAL"]
    assert any("price:late_disclosure" in s for s in res.signals)
    assert any("price:additional_cost" in s for s in res.signals)
    assert res.consumer_consequence is not None
    assert res.consumer_consequence.amount == 79.0
    assert "578" in res.consumer_consequence.description


# =============================================================================
# 3. RULE C — PRICE CHANGE FACTUAL SIGNAL
# =============================================================================

def test_rule_c_price_change_not_dark_pattern():
    """Rule C: Explicit price change exposes factual financial signal without dark pattern."""
    price_resp = PriceAnalysisResponse(
        previous_price=999.0,
        current_price=1299.0,
        price_change=300.0,
        price_change_percentage=30.03,
        price_change_detected=True,
        price_changed=True,
        price_change_direction="increase",
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.price_changed is True
    assert res.risk_detected is False
    assert res.primary_pattern is None
    assert res.dark_pattern is None
    assert res.potential_pattern == "price_change"
    assert res.risk_level == "LOW"
    assert any("price:price_changed" in s for s in res.signals)
    assert any("price:direction:increase" in s for s in res.signals)
    assert res.consumer_consequence is not None
    assert res.consumer_consequence.type == "price_change"
    assert res.consumer_consequence.amount == 300.0


# =============================================================================
# 4. RULE D — RENEWAL WITHOUT DARK PATTERN TEXT
# =============================================================================

def test_rule_d_renewal_informational_signal():
    """Rule D: Renewal pricing without dark pattern text is financial information."""
    price_resp = PriceAnalysisResponse(
        trial_price=0.0,
        trial_duration_days=7,
        renewal_price=999.0,
        renewal_currency="INR",
        billing_period="month",
        recurring=True,
        renewal_price_detected=True,
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.renewal_signal is True
    assert res.risk_detected is False
    assert res.primary_pattern is None
    assert res.dark_pattern is None
    assert res.potential_pattern == "subscription_risk"
    assert res.risk_level in ["LOW", "MEDIUM"]


# =============================================================================
# 5. RULE E & HARD NEGATIVE 1 — NORMAL SINGLE PRICE
# =============================================================================

def test_rule_e_normal_price_samsung_tv():
    """Rule E: Plain product price is non-risk."""
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=49999.0, currency="INR"),
        currency="INR",
    )
    req = EvidenceFusionRequest(
        text="Samsung TV — ₹49,999",
        price_analysis=price_resp,
    )
    res = fusion_engine.fuse(req)

    assert res.risk_detected is False
    assert res.primary_pattern is None
    assert res.dark_pattern is None
    assert res.potential_pattern is None
    assert res.risk_level == "LOW"
    assert res.price_changed is False
    assert res.renewal_signal is False


# =============================================================================
# 6. RULE F & HARD NEGATIVES 4 & 5 — ALTERNATIVE PRICING
# =============================================================================

def test_rule_f_alternative_pricing_choice():
    """Rule F: Multiple choice prices are not classified as price changes."""
    price_resp = PriceAnalysisResponse(
        is_alternative_pricing=True,
        price_change_detected=False,
        price_changed=False,
    )
    req = EvidenceFusionRequest(
        text="Choose between ₹499 and ₹999.",
        price_analysis=price_resp,
    )
    res = fusion_engine.fuse(req)

    assert res.price_changed is False
    assert res.risk_detected is False
    assert res.primary_pattern is None
    assert res.dark_pattern is None
    assert any("price:alternative_pricing" in s for s in res.signals)


def test_rule_f_alternative_pricing_tiers():
    """Rule F: Tiered plans (standard vs premium) are not price changes."""
    price_resp = PriceAnalysisResponse(
        is_alternative_pricing=True,
        price_change_detected=False,
        price_changed=False,
    )
    req = EvidenceFusionRequest(
        text="₹499 for standard, ₹999 for premium.",
        price_analysis=price_resp,
    )
    res = fusion_engine.fuse(req)

    assert res.price_changed is False
    assert res.risk_detected is False


# =============================================================================
# 7. RULE G & HARD NEGATIVES 2 & 3 — INCLUSIVE PRICE
# =============================================================================

def test_rule_g_inclusive_taxes():
    """Rule G: Price including taxes is non-risk from price signal."""
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=999.0, currency="INR"),
        additional_cost_detected=False,
        late_disclosure_detected=False,
        late_disclosed=False,
        currency="INR",
    )
    req = EvidenceFusionRequest(
        text="₹999 including all taxes.",
        price_analysis=price_resp,
    )
    res = fusion_engine.fuse(req)

    assert res.risk_detected is False
    assert res.dark_pattern is None
    assert res.primary_pattern is None
    assert any("price:inclusive_pricing" in s for s in res.signals)


def test_rule_g_inclusive_shipping():
    """Rule G: Price including shipping is non-risk."""
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=499.0, currency="INR"),
        additional_cost_detected=False,
        late_disclosure_detected=False,
        currency="INR",
    )
    req = EvidenceFusionRequest(
        text="₹499 including shipping.",
        price_analysis=price_resp,
    )
    res = fusion_engine.fuse(req)

    assert res.risk_detected is False
    assert res.dark_pattern is None


# =============================================================================
# 8. RULE H — INSUFFICIENT CONTEXT
# =============================================================================

def test_rule_h_insufficient_context_suppresses_risk():
    """Rule H: requires_context=True prevents elevated dark-pattern risk."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.55,
        model_version="ClauseGuard-Text-V3",
        requires_context=True,
        pattern_category="Subscription Trap",
        evidence="Terms and renewal conditions apply.",
    )
    price_resp = PriceAnalysisResponse(
        renewal_price=999.0,
        renewal_currency="INR",
        recurring=True,
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.requires_context is True
    assert res.risk_detected is False
    assert res.primary_pattern is None
    assert res.dark_pattern is None
    assert res.risk_level == "LOW"


# =============================================================================
# 9. HARD NEGATIVES (DISCOUNT, IDENTITY PRICE CHANGE)
# =============================================================================

def test_hard_negative_discount_pricing():
    """Hard negative: Original price vs sale price is discount, not price change."""
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=999.0, currency="INR"),
        discount_amount=300.0,
        discount_percentage=23.09,
        price_change_detected=False,
        price_changed=False,
    )
    req = EvidenceFusionRequest(
        text="Original price ₹1299, sale price ₹999.",
        price_analysis=price_resp,
    )
    res = fusion_engine.fuse(req)

    assert res.price_changed is False
    assert res.risk_detected is False
    assert any("price:discount" in s for s in res.signals)


def test_hard_negative_identity_price_change():
    """Hard negative: 'Price changed from ₹999 to ₹999' is not a price change."""
    price_resp = PriceAnalysisResponse(
        previous_price=999.0,
        current_price=999.0,
        price_change=0.0,
        price_change_percentage=0.0,
        price_change_detected=False,
        price_changed=False,
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.price_changed is False
    assert res.risk_detected is False


# =============================================================================
# 10. POSITIVE INTEGRATION TESTS
# =============================================================================

def test_positive_integration_case_a_full_pipeline():
    """Positive Case A: 'Your free trial automatically renews at ₹999/month after 7 days.'"""
    raw_text = "Your free trial automatically renews at ₹999/month after 7 days."
    req = EvidenceFusionRequest(text=raw_text)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.renewal_signal is True
    # If text predictor tags Subscription Trap, corroboration triggers
    if res.dark_pattern == "subscription_trap":
        assert res.risk_detected is True
        assert res.primary_pattern == "Subscription Trap"
        assert res.is_corroborated is True
        assert res.consumer_consequence is not None
        assert "recurring" in res.consumer_consequence.description.lower()
        assert "999" in res.consumer_consequence.description


def test_positive_integration_case_b_full_pipeline():
    """Positive Case B: 'Ticket price is ₹499. A processing fee of ₹79 applies.'"""
    raw_text = "Ticket price is ₹499. A processing fee of ₹79 applies."
    req = EvidenceFusionRequest(text=raw_text)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.financial_impact is not None
    assert res.financial_impact.initial_price == 499.0
    assert res.financial_impact.additional_cost == 79.0
    assert res.financial_impact.known_total == 578.0
    if res.dark_pattern == "drip_pricing":
        assert res.risk_detected is True
        assert res.primary_pattern == "Drip Pricing"


def test_positive_integration_case_c_full_pipeline():
    """Positive Case C: 'Price increased from ₹999 to ₹1299.'"""
    raw_text = "Price increased from ₹999 to ₹1299."
    req = EvidenceFusionRequest(text=raw_text)
    res = fusion_engine.fuse(req)

    assert res.price_changed is True
    assert res.financial_impact is not None
    assert res.financial_impact.previous_price == 999.0
    assert res.financial_impact.current_price == 1299.0
    assert res.financial_impact.price_change == 300.0
    # Price change alone must NOT be declared a dark pattern
    assert res.dark_pattern is None
    assert res.risk_detected is False


def test_positive_integration_case_d_full_pipeline():
    """Positive Case D: 'Base price is ₹999/month with a 7-day free trial.'"""
    raw_text = "Base price is ₹999/month with a 7-day free trial."
    req = EvidenceFusionRequest(text=raw_text)
    res = fusion_engine.fuse(req)

    assert res.financial_impact is not None
    assert res.financial_impact.initial_price == 999.0
    assert res.financial_impact.trial_price == 0.0
    assert res.financial_impact.trial_duration_days == 7
    # ₹999 must NOT be incorrectly labeled as renewal price only
    assert res.financial_impact.renewal_price is None


# =============================================================================
# 11. MISSING-SOURCE MATRIX
# =============================================================================

def test_missing_source_text_only():
    """Missing source: text only provided."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.80,
        model_version="ClauseGuard-Text-V3",
        pattern_category="Urgency",
        evidence="Hurry! Only 2 left!",
    )
    req = EvidenceFusionRequest(text_prediction=text_pred)
    res = fusion_engine.fuse(req)

    assert res.risk_detected is True
    assert res.primary_pattern == "Urgency"
    assert res.financial_signal is False
    assert res.price_changed is False
    assert res.renewal_signal is False


def test_missing_source_price_only():
    """Missing source: price only provided."""
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=499.0, currency="INR"),
        currency="INR",
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.risk_detected is False
    assert res.primary_pattern is None
    assert res.financial_signal is True


def test_missing_source_empty_request():
    """Missing source: empty request with no inputs."""
    req = EvidenceFusionRequest()
    res = fusion_engine.fuse(req)

    assert res.risk_detected is False
    assert res.primary_pattern is None
    assert res.dark_pattern is None
    assert res.risk_level == "LOW"
    assert res.risk_score == 0.0
    assert res.confidence is None
    assert len(res.evidence) == 0


def test_missing_source_null_fields():
    """Missing source: explicit null values in optional fields."""
    req = EvidenceFusionRequest(
        text=None,
        text_prediction=None,
        price_analysis=None,
        ui_evidence=None,
        behavior_evidence=None,
        raw_evidence=None,
    )
    res = fusion_engine.fuse(req)

    assert res.risk_detected is False
    assert res.risk_level == "LOW"
    assert res.confidence is None


# =============================================================================
# 12. API ENDPOINT INTEGRATION (/fuse-evidence)
# =============================================================================

def test_api_fuse_evidence_endpoint():
    """POST /fuse-evidence returns HTTP 200 and schema compliant payload."""
    payload = {
        "text": "Your free trial automatically renews at ₹999/month after 7 days.",
    }
    response = client.post("/fuse-evidence", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["source"] == "evidence_fusion"
    assert "risk_detected" in data
    assert "signals" in data
    assert isinstance(data["signals"], list)
    assert "supporting_evidence" in data
    assert "risk_level" in data
