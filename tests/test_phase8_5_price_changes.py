"""tests/test_phase8_5_price_changes.py
Comprehensive test suite for ClauseGuard Phase 8.5:
Late-Disclosure & Price-Change Detection.

Tests deterministic detection of:
- Category A: Late-disclosure (fees following base price, position preservation, unknown fees, preceding fees)
- Category B: Explicit price increases (from X to Y, previously X now Y, renewal changes)
- Category C: Explicit price decreases (reduced from X to Y, negative price changes)
- Category D: Same-price changes (no meaningful price change detected)
- Category E: Promotional transitions (initial promo price to renewal price)
- Category F: Trial to renewal transitions (free vs paid trials)
- Category G: Alternative pricing isolation (options not combined)
- Category H: Incomplete / unknown pricing (no invented amounts)
- Category I: Non-monetary negative filtering (dates, seats, models, orders)
- Category J: Multi-currency safety (currencies never combined)
- Category K: API endpoint contracts and schema compliance
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.price_analyzer import PriceAnalyzer

client = TestClient(app)
analyzer = PriceAnalyzer()


# =====================================================================
# CATEGORY A: LATE-DISCLOSURE DETECTION
# =====================================================================

def test_a1_late_disclosure_processing_fee():
    """A1: '₹499 + ₹79 processing fee' -> displayed=499, additional=79, total=578, late_disclosed=True."""
    res = analyzer.analyze("₹499 + ₹79 processing fee")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.displayed_price.currency == "INR"
    assert res.additional_costs == 79.0
    assert res.additional_cost == 79.0
    assert res.calculated_subtotal == 578.0
    assert res.known_total == 578.0
    assert res.additional_cost_percentage == 15.83
    assert res.late_disclosed is True
    assert res.initial_price_position is not None
    assert res.additional_cost_position is not None
    assert res.additional_cost_position > res.initial_price_position


def test_a2_late_disclosure_shipping_at_checkout():
    """A2: 'The product costs ₹999. Shipping ₹120 is added at checkout.' -> displayed=999, additional=120, total=1119, late_disclosed=True."""
    res = analyzer.analyze("The product costs ₹999. Shipping ₹120 is added at checkout.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 999.0
    assert res.additional_costs == 120.0
    assert res.additional_cost == 120.0
    assert res.calculated_subtotal == 1119.0
    assert res.known_total == 1119.0
    assert res.additional_cost_percentage == 12.01
    assert res.late_disclosed is True


def test_a3_price_followed_by_disclosed_fee():
    """A3: 'Ticket price is ₹499. A processing fee of ₹79 applies.' -> displayed=499, additional=79, late_disclosed=True."""
    res = analyzer.analyze("Ticket price is ₹499. A processing fee of ₹79 applies.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_costs == 79.0
    assert res.additional_cost == 79.0
    assert res.known_total == 578.0
    assert res.additional_cost_percentage == 15.83
    assert res.late_disclosed is True
    assert res.initial_price_position == 16
    assert res.additional_cost_position == 42


def test_a4_unknown_fee_amount():
    """A4: '₹499. Taxes and fees apply.' -> displayed=499, additional_cost=None, late_disclosed=False."""
    res = analyzer.analyze("₹499. Taxes and fees apply.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_costs is None
    assert res.additional_cost is None
    assert res.known_total is None
    assert res.late_disclosed is False


def test_a5_fee_before_base_price():
    """A5: 'Processing fee ₹79. Ticket price is ₹499.' -> fee precedes base, late_disclosed=False."""
    res = analyzer.analyze("Processing fee ₹79. Ticket price is ₹499.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_costs == 79.0
    assert res.additional_cost == 79.0
    assert res.known_total == 578.0
    assert res.late_disclosed is False
    assert res.initial_price_position is not None
    assert res.additional_cost_position is not None
    assert res.additional_cost_position < res.initial_price_position


def test_a6_multiple_additional_costs():
    """A6: 'Ticket price is ₹499. A processing fee of ₹79 and ₹50 tax apply.' -> additional=129, late_disclosed=True."""
    res = analyzer.analyze("Ticket price is ₹499. A processing fee of ₹79 and ₹50 tax apply.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_costs == 129.0
    assert res.additional_cost == 129.0
    assert res.calculated_subtotal == 628.0
    assert res.known_total == 628.0
    assert res.additional_cost_percentage == 25.85
    assert res.late_disclosed is True
    assert res.initial_price_position == 16
    assert res.additional_cost_position == 42


def test_a7_explicit_total_preservation():
    """A7: '₹499 + ₹79 fee. Total ₹600.' -> explicit_total=600 authoritative over calculated 578."""
    res = analyzer.analyze("₹499 + ₹79 fee. Total ₹600.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_costs == 79.0
    assert res.additional_cost == 79.0
    assert res.calculated_subtotal == 578.0
    assert res.explicit_total == 600.0
    assert res.known_total == 600.0
    assert res.total_source == "explicit"
    assert res.late_disclosed is True


# =====================================================================
# CATEGORY B: PRICE INCREASE DETECTION
# =====================================================================

def test_b7_price_increase_from_to():
    """B7: 'Price increased from ₹999 to ₹1299.' -> change=300, pct=30.03."""
    res = analyzer.analyze("Price increased from ₹999 to ₹1299.")
    assert res.previous_price == 999.0
    assert res.previous_currency == "INR"
    assert res.current_price == 1299.0
    assert res.current_currency == "INR"
    assert res.price_change == 300.0
    assert res.price_change_percentage == 30.03
    assert res.price_change_detected is True
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 1299.0


def test_b8_price_increase_previously_now():
    """B8: 'Previously ₹799, now ₹999.' -> change=200, pct=25.03."""
    res = analyzer.analyze("Previously ₹799, now ₹999.")
    assert res.previous_price == 799.0
    assert res.previous_currency == "INR"
    assert res.current_price == 999.0
    assert res.current_currency == "INR"
    assert res.price_change == 200.0
    assert res.price_change_percentage == 25.03
    assert res.price_change_detected is True
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 999.0


def test_b9_monthly_renewal_increase():
    """B9: 'Renewal price changed from ₹999/month to ₹1,299/month.' -> billing_period=month, recurring=True."""
    res = analyzer.analyze("Renewal price changed from ₹999/month to ₹1,299/month.")
    assert res.previous_price == 999.0
    assert res.current_price == 1299.0
    assert res.price_change == 300.0
    assert res.price_change_percentage == 30.03
    assert res.billing_period == "month"
    assert res.recurring is True
    assert res.price_change_detected is True


def test_b10_annual_renewal_increase():
    """B10: 'Annual subscription increased from $100/year to $150/year.' -> change=50, billing_period=year."""
    res = analyzer.analyze("Annual subscription increased from $100/year to $150/year.")
    assert res.previous_price == 100.0
    assert res.previous_currency == "USD"
    assert res.current_price == 150.0
    assert res.current_currency == "USD"
    assert res.price_change == 50.0
    assert res.price_change_percentage == 50.0
    assert res.billing_period == "year"
    assert res.recurring is True
    assert res.price_change_detected is True


def test_b11_subscription_was_now_renews():
    """B11: 'Your subscription was ₹999/month and now renews at ₹1299/month.'"""
    res = analyzer.analyze("Your subscription was ₹999/month and now renews at ₹1299/month.")
    assert res.previous_price == 999.0
    assert res.current_price == 1299.0
    assert res.price_change == 300.0
    assert res.price_change_percentage == 30.03
    assert res.billing_period == "month"
    assert res.recurring is True
    assert res.price_change_detected is True


# =====================================================================
# CATEGORY C: PRICE DECREASE DETECTION
# =====================================================================

def test_c11_price_decrease_reduced_from_to():
    """C11: 'Price reduced from ₹999 to ₹799.' -> change=-200, pct=-20.02."""
    res = analyzer.analyze("Price reduced from ₹999 to ₹799.")
    assert res.previous_price == 999.0
    assert res.current_price == 799.0
    assert res.price_change == -200.0
    assert res.price_change_percentage == -20.02
    assert res.price_change_detected is True
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 799.0


def test_c12_price_decrease_dropped_from_to():
    """C12: 'Price dropped from ₹1299 to ₹999.' -> change=-300, pct=-23.09."""
    res = analyzer.analyze("Price dropped from ₹1299 to ₹999.")
    assert res.previous_price == 1299.0
    assert res.current_price == 999.0
    assert res.price_change == -300.0
    assert res.price_change_percentage == -23.09
    assert res.price_change_detected is True
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 999.0


# =====================================================================
# CATEGORY D: SAME-PRICE CASE (NO CHANGE)
# =====================================================================

def test_d13_same_price_case():
    """D13: 'Price changed from ₹999 to ₹999.' -> change=0, detected=False."""
    res = analyzer.analyze("Price changed from ₹999 to ₹999.")
    assert res.previous_price == 999.0
    assert res.current_price == 999.0
    assert res.price_change == 0.0
    assert res.price_change_percentage == 0.0
    assert res.price_change_detected is False


# =====================================================================
# CATEGORY E: PROMOTIONAL PRICING
# =====================================================================

def test_e14_promotional_pricing_transition():
    """E14: '₹99 for the first month, then ₹999/month.' -> promo transition."""
    res = analyzer.analyze("₹99 for the first month, then ₹999/month.")
    assert res.initial_price == 99.0
    assert res.renewal_price == 999.0
    assert res.later_price == 999.0
    assert res.price_change == 900.0
    assert res.price_change_percentage == 909.09
    assert res.price_change_detected is True
    assert res.late_disclosed is False
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 99.0


def test_e15_multi_month_promotional_transition():
    """E15: 'First 3 months ₹199, then ₹799/month.'"""
    res = analyzer.analyze("First 3 months ₹199, then ₹799/month.")
    assert res.initial_price == 199.0
    assert res.renewal_price == 799.0
    assert res.price_change == 600.0
    assert res.price_change_percentage == 301.51
    assert res.promotion_duration_months == 3
    assert res.price_change_detected is True
    assert res.late_disclosed is False


# =====================================================================
# CATEGORY F: TRIAL / RENEWAL PRICING
# =====================================================================

def test_f16_free_trial_then_renewal():
    """F16: '7-day free trial, then ₹999/month.' -> renewal is not displayed_price."""
    res = analyzer.analyze("7-day free trial, then ₹999/month.")
    assert res.trial_price == 0.0
    assert res.trial_duration_days == 7
    assert res.renewal_price == 999.0
    assert res.displayed_price is None
    assert res.late_disclosed is False
    assert res.price_change_detected is False


def test_f17_paid_trial_then_renewal():
    """F17: '₹99 for a 7-day trial, then ₹999/month.' -> displayed=99, trial=99, renewal=999."""
    res = analyzer.analyze("₹99 for a 7-day trial, then ₹999/month.")
    assert res.trial_price == 99.0
    assert res.trial_duration_days == 7
    assert res.renewal_price == 999.0
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 99.0
    assert res.price_change == 900.0
    assert res.price_change_percentage == 909.09
    assert res.price_change_detected is True


# =====================================================================
# CATEGORY G: ALTERNATIVE PRICING
# =====================================================================

def test_g18_alternative_pricing():
    """G18: '₹99/month or ₹999/year.' -> is_alt=True, price_change=None."""
    res = analyzer.analyze("₹99/month or ₹999/year.")
    assert res.is_alternative_pricing is True
    assert res.price_change is None
    assert res.price_change_percentage is None
    assert res.price_change_detected is False
    assert res.late_disclosed is False


# =====================================================================
# CATEGORY H: INCOMPLETE PRICING
# =====================================================================

def test_h19_base_price_plus_shipping():
    """H19: '₹499 + shipping' -> displayed=499, additional=None, late_disclosed=False."""
    res = analyzer.analyze("₹499 + shipping")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_costs is None
    assert res.additional_cost is None
    assert res.known_total is None
    assert res.late_disclosed is False


def test_h20_base_price_plus_taxes():
    """H20: '₹499 + taxes' -> displayed=499, additional=None, late_disclosed=False."""
    res = analyzer.analyze("₹499 + taxes")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_costs is None
    assert res.additional_cost is None
    assert res.known_total is None
    assert res.late_disclosed is False


# =====================================================================
# CATEGORY I: NON-MONETARY NEGATIVES
# =====================================================================

def test_i21_non_monetary_return_days():
    """I21: '30-day return' -> 0 entities."""
    res = analyzer.analyze("30-day return")
    assert len(res.entities) == 0


def test_i22_non_monetary_seats():
    """I22: '2 seats' -> 0 entities."""
    res = analyzer.analyze("2 seats")
    assert len(res.entities) == 0


def test_i23_non_monetary_model():
    """I23: 'Model 2026' -> 0 entities."""
    res = analyzer.analyze("Model 2026")
    assert len(res.entities) == 0


def test_i24_non_monetary_order_number():
    """I24: 'Order #499' -> 0 entities."""
    res = analyzer.analyze("Order #499")
    assert len(res.entities) == 0


# =====================================================================
# CATEGORY J: MULTI-CURRENCY SAFETY
# =====================================================================

def test_j25_multi_currency_safety():
    """J25: '₹499 + $20' -> multi-currency isolated, no price change, no totals."""
    res = analyzer.analyze("₹499 + $20")
    assert len(res.entities) == 2
    assert res.displayed_price is None
    assert res.additional_costs is None
    assert res.known_total is None
    assert res.price_change is None
    assert res.price_change_detected is False


# =====================================================================
# CATEGORY K: API CONTRACT & POSITION TRACKING
# =====================================================================

def test_k26_entity_character_offsets_and_indices():
    """K26: Verify character_start, character_end, and entity_index on entities."""
    res = analyzer.analyze("Ticket price ₹499. Processing fee ₹79.")
    assert len(res.entities) == 2
    assert res.entities[0].entity_index == 0
    assert res.entities[0].character_start == 13
    assert res.entities[0].character_end == 17
    assert res.entities[1].entity_index == 1
    assert res.entities[1].character_start == 34
    assert res.entities[1].character_end == 37


def test_k27_api_endpoint_late_disclosure():
    """K27: Test POST /analyze-price returns Phase 8.5 schema fields."""
    response = client.post(
        "/analyze-price",
        json={"text": "Ticket price is ₹499. A processing fee of ₹79 applies."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "price"
    assert data["displayed_price"]["amount"] == 499.0
    assert data["additional_cost"] == 79.0
    assert data["additional_costs"] == 79.0
    assert data["known_total"] == 578.0
    assert data["late_disclosed"] is True
    assert data["initial_price_position"] == 16
    assert data["additional_cost_position"] == 42


def test_k28_api_endpoint_price_change():
    """K28: Test POST /analyze-price for explicit price change."""
    response = client.post(
        "/analyze-price",
        json={"text": "Price increased from ₹999 to ₹1299."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["previous_price"] == 999.0
    assert data["current_price"] == 1299.0
    assert data["price_change"] == 300.0
    assert data["price_change_percentage"] == 30.03
    assert data["price_change_detected"] is True
