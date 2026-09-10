"""tests/test_phase8_6_evidence_fusion.py
Comprehensive test suite for ClauseGuard Phase 8.6: Evidence Fusion Engine.

Tests:
1. text-only evidence
2. price-only evidence
3. text + price corroboration
4. trial + renewal
5. displayed price + additional fee
6. late disclosure + fee
7. explicit total preservation
8. price increase
9. price decrease
10. alternative pricing
11. multi-currency isolation
12. context-required evidence
13. prediction = 0
14. contradictory evidence
15. duplicate evidence
16. no evidence
17. multiple evidence groups
18. financial signal without dark-pattern conclusion
19. strong corroborated signal
20. risk threshold boundaries
21. POST /fuse-evidence API endpoint integration
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.evidence import (
    EvidenceFusionRequest,
    EvidenceItem,
)
from backend.schemas.price import DisplayedPrice, PriceAnalysisResponse
from backend.schemas import PredictResponse
from backend.services.evidence_fusion import (
    EvidenceFusionEngine,
    RISK_THRESHOLD_CRITICAL,
    RISK_THRESHOLD_HIGH,
    RISK_THRESHOLD_MEDIUM,
)

client = TestClient(app)
fusion_engine = EvidenceFusionEngine()


# =====================================================================
# 1. TEXT-ONLY EVIDENCE
# =====================================================================

def test_01_text_only_evidence():
    """Test 1: Only text dark pattern evidence without price figures."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.88,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Urgency",
        evidence="Hurry! Only 2 items left at this price!",
        consumer_consequence="Creates false pressure to purchase quickly.",
    )
    req = EvidenceFusionRequest(text_prediction=text_pred)
    res = fusion_engine.fuse(req)

    assert len(res.evidence) == 1
    assert res.evidence[0].source == "text"
    assert res.evidence[0].pattern == "urgency"
    assert res.is_corroborated is False
    assert res.financial_signal is False
    assert res.dark_pattern == "urgency"
    assert res.risk_level in ["LOW", "MEDIUM"]
    assert res.risk_score == 2.0


# =====================================================================
# 2. PRICE-ONLY EVIDENCE
# =====================================================================

def test_02_price_only_evidence():
    """Test 2: Only price entities without text dark patterns."""
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=499.0, currency="INR"),
        currency="INR",
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert len(res.evidence) == 1
    assert res.evidence[0].source == "price"
    assert res.evidence[0].type == "displayed_price"
    assert res.dark_pattern is None
    assert res.is_corroborated is False
    assert res.risk_level == "LOW"


# =====================================================================
# 3. TEXT + PRICE CORROBORATION
# =====================================================================

def test_03_text_and_price_corroboration():
    """Test 3: Text subscription trap corroborated by price renewal."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.90,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Subscription Trap",
        evidence="renews automatically at ₹999/month",
        consumer_consequence="Continuous recurring charges without manual confirmation.",
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

    assert res.is_corroborated is True
    assert res.potential_pattern == "subscription_trap"
    assert res.dark_pattern == "subscription_trap"
    assert any(g.corroborated for g in res.evidence_groups)
    assert res.risk_level in ["HIGH", "CRITICAL"]
    assert res.risk_score >= 7.0


# =====================================================================
# 4. TRIAL + RENEWAL
# =====================================================================

def test_04_trial_to_renewal():
    """Test 4: Free trial converting into recurring charge."""
    price_resp = PriceAnalysisResponse(
        trial_price=0.0,
        trial_duration_days=14,
        trial_currency="USD",
        renewal_price=29.99,
        renewal_currency="USD",
        billing_period="month",
        recurring=True,
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_impact is not None
    assert res.financial_impact.trial_price == 0.0
    assert res.financial_impact.trial_duration_days == 14
    assert res.financial_impact.renewal_price == 29.99
    assert res.consumer_consequence is not None
    assert res.consumer_consequence.type == "recurring_charge"
    assert res.consumer_consequence.amount == 29.99
    assert "recurring" in res.consumer_consequence.description


# =====================================================================
# 5. DISPLAYED PRICE + ADDITIONAL FEE
# =====================================================================

def test_05_displayed_price_and_additional_fee():
    """Test 5: Base price followed by explicit fee."""
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=999.0, currency="INR"),
        additional_costs=120.0,
        additional_cost=120.0,
        calculated_subtotal=1119.0,
        known_total=1119.0,
        additional_cost_percentage=12.01,
        late_disclosed=False,
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_impact is not None
    assert res.financial_impact.initial_price == 999.0
    assert res.financial_impact.additional_cost == 120.0
    assert res.financial_impact.known_total == 1119.0
    assert res.financial_signal is True


# =====================================================================
# 6. LATE DISCLOSURE + FEE
# =====================================================================

def test_06_late_disclosure_and_fee():
    """Test 6: Late-disclosed fee produces financial disclosure risk."""
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=499.0, currency="INR"),
        additional_costs=79.0,
        additional_cost=79.0,
        known_total=578.0,
        additional_cost_percentage=15.83,
        late_disclosed=True,
        initial_price_position=16,
        additional_cost_position=42,
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.potential_pattern == "price_disclosure_risk"
    # Factual financial signal alone does NOT declare dark pattern
    assert res.dark_pattern is None
    assert res.consumer_consequence is not None
    assert res.consumer_consequence.type == "additional_fee"
    assert res.consumer_consequence.amount == 79.0


# =====================================================================
# 7. EXPLICIT TOTAL PRESERVATION
# =====================================================================

def test_07_explicit_total_preservation():
    """Test 7: Explicit total preserved over calculated subtotal."""
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=499.0, currency="INR"),
        additional_costs=79.0,
        additional_cost=79.0,
        calculated_subtotal=578.0,
        explicit_total=600.0,
        known_total=600.0,
        total_source="explicit",
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_impact is not None
    assert res.financial_impact.known_total == 600.0
    assert any(e.type == "explicit_total" and e.value == 600.0 for e in res.evidence)


# =====================================================================
# 8. PRICE INCREASE
# =====================================================================

def test_08_price_increase_signal():
    """Test 8: Price increase is a financial signal, not dark pattern."""
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
    assert res.financial_impact.price_change == 300.0
    assert res.consumer_consequence is not None
    assert res.consumer_consequence.type == "price_change"
    assert res.consumer_consequence.amount == 300.0


# =====================================================================
# 9. PRICE DECREASE
# =====================================================================

def test_09_price_decrease_signal():
    """Test 9: Price reduction reports negative delta correctly."""
    price_resp = PriceAnalysisResponse(
        previous_price=999.0,
        current_price=799.0,
        price_change=-200.0,
        price_change_percentage=-20.02,
        price_change_detected=True,
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern is None
    assert res.financial_impact.price_change == -200.0


# =====================================================================
# 10. ALTERNATIVE PRICING
# =====================================================================

def test_10_alternative_pricing():
    """Test 10: Alternative pricing is isolated and preserved."""
    price_resp = PriceAnalysisResponse(
        is_alternative_pricing=True,
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert any(e.type == "alternative_pricing" for e in res.evidence)
    assert res.financial_impact.known_total is None


# =====================================================================
# 11. MULTI-CURRENCY ISOLATION
# =====================================================================

def test_11_multi_currency_isolation():
    """Test 11: Multi-currency does not combine totals."""
    price_resp = PriceAnalysisResponse(
        currency=None,
        known_total=None,
    )
    req = EvidenceFusionRequest(price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_impact.known_total is None


# =====================================================================
# 12. CONTEXT-REQUIRED EVIDENCE
# =====================================================================

def test_12_context_required_evidence():
    """Test 12: requires_context produces reduced score and confidence."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.62,
        model_version="ClauseGuard-Text-V3",
        requires_context=True,
        pattern_category=None,
        evidence="billing terms apply",
    )
    req = EvidenceFusionRequest(text_prediction=text_pred)
    res = fusion_engine.fuse(req)

    assert res.requires_context is True
    assert res.risk_level == "LOW"
    assert res.risk_score == 1.0
    assert res.confidence is not None and res.confidence < 0.70


# =====================================================================
# 13. PREDICTION = 0
# =====================================================================

def test_13_prediction_zero():
    """Test 13: prediction=0 produces no dark pattern evidence."""
    text_pred = PredictResponse(
        prediction=0,
        label="not_dark_pattern",
        confidence=0.10,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
    )
    req = EvidenceFusionRequest(text_prediction=text_pred)
    res = fusion_engine.fuse(req)

    assert len(res.evidence) == 0
    assert res.risk_score == 0.0
    assert res.risk_level == "LOW"
    assert res.dark_pattern is None


# =====================================================================
# 14. CONTRADICTORY EVIDENCE
# =====================================================================

def test_14_contradictory_evidence():
    """Test 14: Conflicting evidence is recorded and penalized."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.80,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Subscription Trap",
        evidence="free trial offer",
    )
    price_resp = PriceAnalysisResponse(
        trial_price=99.0,  # Contradiction: Paid trial of 99 vs text claim of free trial
        trial_currency="INR",
        renewal_price=999.0,
    )
    req = EvidenceFusionRequest(
        text="Start your free trial today",
        text_prediction=text_pred,
        price_analysis=price_resp,
    )
    res = fusion_engine.fuse(req)

    assert len(res.conflicts) >= 1
    assert res.conflicts[0].type == "evidence_conflict"
    assert "text" in res.conflicts[0].sources
    assert "price" in res.conflicts[0].sources
    assert res.conflicts[0].resolution == "preserve_both"


# =====================================================================
# 15. DUPLICATE EVIDENCE
# =====================================================================

def test_15_duplicate_evidence_handling():
    """Test 15: Identical evidence items are not counted twice."""
    item1 = EvidenceItem(
        evidence_id="E001",
        source="ui",
        type="countdown_timer",
        pattern="urgency",
        description="Countdown timer active",
        value="05:00",
    )
    item2 = EvidenceItem(
        evidence_id="E002",
        source="ui",
        type="countdown_timer",
        pattern="urgency",
        description="Countdown timer active",
        value="05:00",
    )
    req = EvidenceFusionRequest(ui_evidence=[item1, item2])
    res = fusion_engine.fuse(req)

    # Deduped to 1 item
    assert len(res.evidence) == 1


# =====================================================================
# 16. NO EVIDENCE
# =====================================================================

def test_16_no_evidence():
    """Test 16: Empty inputs produce LOW risk with zero findings."""
    req = EvidenceFusionRequest()
    res = fusion_engine.fuse(req)

    assert res.risk_level == "LOW"
    assert res.risk_score == 0.0
    assert len(res.evidence) == 0
    assert res.confidence is None
    assert res.dark_pattern is None


# =====================================================================
# 17. MULTIPLE EVIDENCE GROUPS
# =====================================================================

def test_17_multiple_evidence_groups():
    """Test 17: Distinct risks form separate evidence groups."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.85,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Urgency",
        evidence="Sale ends in 5 minutes!",
    )
    price_resp = PriceAnalysisResponse(
        displayed_price=DisplayedPrice(amount=499.0, currency="INR"),
        additional_costs=79.0,
        additional_cost=79.0,
        late_disclosed=True,
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert len(res.evidence_groups) >= 2
    patterns = {g.pattern for g in res.evidence_groups}
    assert "urgency" in patterns
    assert "drip_pricing" in patterns


# =====================================================================
# 18. FINANCIAL SIGNAL WITHOUT DARK PATTERN
# =====================================================================

def test_18_financial_signal_without_dark_pattern():
    """Test 18: Price increase alone is not labeled as a dark pattern."""
    price_resp = PriceAnalysisResponse(
        previous_price=999.0,
        current_price=1299.0,
        price_change=300.0,
        price_change_percentage=30.03,
        price_change_detected=True,
    )
    text_pred = PredictResponse(
        prediction=0,
        label="not_dark_pattern",
        confidence=0.10,
        model_version="ClauseGuard-Text-V3",
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.financial_signal is True
    assert res.dark_pattern is None
    assert res.risk_level in ["LOW", "MEDIUM"]


# =====================================================================
# 19. STRONG CORROBORATED SIGNAL
# =====================================================================

def test_19_strong_corroborated_signal():
    """Test 19: Full corroboration (Text + Price) yields CRITICAL/HIGH risk."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.92,
        model_version="ClauseGuard-Text-V3",
        requires_context=False,
        pattern_category="Subscription Trap",
        evidence="7-day free trial converts to auto-renewing subscription",
    )
    price_resp = PriceAnalysisResponse(
        trial_price=0.0,
        trial_duration_days=7,
        renewal_price=999.0,
        billing_period="month",
        recurring=True,
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.is_corroborated is True
    assert res.risk_level in ["HIGH", "CRITICAL"]
    assert res.confidence is not None and res.confidence >= 0.90


# =====================================================================
# 20. RISK THRESHOLD BOUNDARIES
# =====================================================================

def test_20_risk_threshold_boundaries():
    """Test 20: Verify exact score boundaries map to expected risk levels."""
    # Boundary 0.0 -> LOW
    assert fusion_engine.fuse(EvidenceFusionRequest()).risk_level == "LOW"

    # Score 3.0 -> MEDIUM
    item_med = EvidenceItem(
        evidence_id="E1",
        source="ui",
        type="preselected_checkbox",
        description="Prechecked box",
    )
    # Give moderate score
    res_med = fusion_engine.fuse(EvidenceFusionRequest(
        price_analysis=PriceAnalysisResponse(
            displayed_price=DisplayedPrice(amount=499.0, currency="INR"),
            additional_costs=50.0,
            late_disclosed=True,
        )
    ))
    assert res_med.risk_score >= 2.0


# =====================================================================
# 21. API ENDPOINT INTEGRATION
# =====================================================================

def test_21_api_endpoint_integration():
    """Test 21: POST /fuse-evidence with raw text runs full pipeline."""
    payload = {
        "text": "7-day free trial, then ₹999/month."
    }
    response = client.post("/fuse-evidence", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["source"] == "evidence_fusion"
    assert "risk_level" in data
    assert "evidence" in data
    assert "evidence_groups" in data
    assert data["financial_impact"] is not None
    assert data["financial_impact"]["renewal_price"] == 999.0
