"""tests/test_price_analyzer.py
Comprehensive test suite for ClauseGuard Price & Cost Analyzer (Phase 8.1: Price Entity Extraction).
Tests positive extractions, hard negatives, edge cases, number normalization, multi-currency separation,
context preservation, security constraints, and the POST /analyze-price endpoint.
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.price_analyzer import PriceAnalyzer

client = TestClient(app)
analyzer = PriceAnalyzer()


# =====================================================================
# 1. CORE POSITIVE TEST CASES (Prompt Required 1-11)
# =====================================================================

def test_extract_inr_symbol():
    """Test 1: '₹499' -> 1 entity, 499 INR"""
    res = analyzer.analyze("₹499")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 499.0
    assert res.entities[0].currency == "INR"
    assert res.entities[0].original_text == "₹499"


def test_extract_inr_thousands_separator():
    """Test 2: '₹1,299' -> 1299 INR"""
    res = analyzer.analyze("₹1,299")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 1299.0
    assert res.entities[0].currency == "INR"
    assert res.entities[0].original_text == "₹1,299"


def test_extract_inr_decimal():
    """Test 3: '₹1,299.50' -> 1299.50 INR"""
    res = analyzer.analyze("₹1,299.50")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 1299.50
    assert res.entities[0].currency == "INR"
    assert res.entities[0].original_text == "₹1,299.50"


def test_extract_rs_abbreviation():
    """Test 4: 'Rs. 999' -> 999 INR"""
    res = analyzer.analyze("Rs. 999")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 999.0
    assert res.entities[0].currency == "INR"
    assert res.entities[0].original_text == "Rs. 999"


def test_extract_inr_code():
    """Test 5: 'INR 999' -> 999 INR"""
    res = analyzer.analyze("INR 999")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 999.0
    assert res.entities[0].currency == "INR"
    assert res.entities[0].original_text == "INR 999"


def test_extract_usd_symbol():
    """Test 6: '$29.99' -> 29.99 USD"""
    res = analyzer.analyze("$29.99")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 29.99
    assert res.entities[0].currency == "USD"
    assert res.entities[0].original_text == "$29.99"


def test_extract_us_dollar_prefix():
    """Test 7: 'US$29.99' -> 29.99 USD"""
    res = analyzer.analyze("US$29.99")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 29.99
    assert res.entities[0].currency == "USD"
    assert res.entities[0].original_text == "US$29.99"


def test_extract_eur_symbol():
    """Test 8: '€19' -> 19 EUR"""
    res = analyzer.analyze("€19")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 19.0
    assert res.entities[0].currency == "EUR"
    assert res.entities[0].original_text == "€19"


def test_extract_gbp_symbol():
    """Test 9: '£49.99' -> 49.99 GBP"""
    res = analyzer.analyze("£49.99")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 49.99
    assert res.entities[0].currency == "GBP"
    assert res.entities[0].original_text == "£49.99"


def test_extract_multiple_entities_with_context():
    """Test 10: 'The ticket costs ₹499 plus a ₹79 processing fee.' -> 2 entities"""
    text = "The ticket costs ₹499 plus a ₹79 processing fee."
    res = analyzer.analyze(text)
    assert len(res.entities) == 2

    # Entity 1
    assert res.entities[0].amount == 499.0
    assert res.entities[0].currency == "INR"
    assert res.entities[0].original_text == "₹499"
    assert res.entities[0].context == text

    # Entity 2
    assert res.entities[1].amount == 79.0
    assert res.entities[1].currency == "INR"
    assert res.entities[1].original_text == "₹79"
    assert res.entities[1].context == text


def test_extract_multiple_currencies_kept_separate():
    """Test 11: '$20 or €18' -> 2 separate entities (no combining or conversion)"""
    res = analyzer.analyze("$20 or €18")
    assert len(res.entities) == 2
    assert res.entities[0].amount == 20.0
    assert res.entities[0].currency == "USD"
    assert res.entities[0].original_text == "$20"

    assert res.entities[1].amount == 18.0
    assert res.entities[1].currency == "EUR"
    assert res.entities[1].original_text == "€18"


# =====================================================================
# 2. HARD NEGATIVE TEST CASES (Must NOT be detected as prices)
# =====================================================================

@pytest.mark.parametrize(
    "negative_text",
    [
        "30-day return period.",
        "Only 2 seats remaining.",
        "Model 2026.",
        "2026 edition.",
        "Save 20%.",
        "20% off on all purchases.",
        "Order number 123456.",
        "Call 9999999999.",
        "Page 404.",
        "Price available on request.",
        "Starting from 499.",
        "Free.",
        "Call 1800-123-4567 for inquiries.",
        "Credit card 4532 1234 5678 9010",
    ],
)
def test_hard_negatives(negative_text: str):
    """Numbers without monetary indicators must never be extracted as prices."""
    res = analyzer.analyze(negative_text)
    assert len(res.entities) == 0, f"Expected 0 entities for '{negative_text}', got {res.entities}"


# =====================================================================
# 3. EDGE CASES & NORMALIZATION
# =====================================================================

def test_edge_case_zero_amounts():
    """Zero amount variants: ₹0, ₹0.00, $0"""
    res_inr = analyzer.analyze("₹0")
    assert len(res_inr.entities) == 1
    assert res_inr.entities[0].amount == 0.0
    assert res_inr.entities[0].currency == "INR"

    res_inr_dec = analyzer.analyze("₹0.00")
    assert len(res_inr_dec.entities) == 1
    assert res_inr_dec.entities[0].amount == 0.0
    assert res_inr_dec.entities[0].currency == "INR"

    res_usd = analyzer.analyze("$0")
    assert len(res_usd.entities) == 1
    assert res_usd.entities[0].amount == 0.0
    assert res_usd.entities[0].currency == "USD"


def test_edge_case_billing_period_text():
    """₹999/month and ₹999 annually should extract only the monetary amount."""
    res_month = analyzer.analyze("Your subscription is ₹999/month.")
    assert len(res_month.entities) == 1
    assert res_month.entities[0].amount == 999.0
    assert res_month.entities[0].currency == "INR"
    assert res_month.entities[0].original_text == "₹999"

    res_annual = analyzer.analyze("Plan cost: ₹999 annually.")
    assert len(res_annual.entities) == 1
    assert res_annual.entities[0].amount == 999.0
    assert res_annual.entities[0].currency == "INR"
    assert res_annual.entities[0].original_text == "₹999"


def test_percentage_with_valid_monetary_amount():
    """Percentages should not be extracted, but accompanying price should."""
    res = analyzer.analyze("Save 20% on orders over $50 today!")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 50.0
    assert res.entities[0].currency == "USD"
    assert res.entities[0].original_text == "$50"


def test_suffix_currency_formats():
    """Suffix currency expressions: 499 INR, 999 Rs., 19 EUR, 49.99 GBP"""
    res_inr = analyzer.analyze("Final charge: 499 INR.")
    assert len(res_inr.entities) == 1
    assert res_inr.entities[0].amount == 499.0
    assert res_inr.entities[0].currency == "INR"

    res_rs = analyzer.analyze("Total: 999 Rs.")
    assert len(res_rs.entities) == 1
    assert res_rs.entities[0].amount == 999.0
    assert res_rs.entities[0].currency == "INR"


def test_indian_lakh_format():
    """Indian numbering format: ₹1,29,999"""
    res = analyzer.analyze("Price is ₹1,29,999 inclusive of taxes.")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 129999.0
    assert res.entities[0].currency == "INR"
    assert res.entities[0].original_text == "₹1,29,999"


# =====================================================================
# 4. FASTAPI ENDPOINT TESTS (POST /analyze-price)
# =====================================================================

def test_api_analyze_price_success():
    """Test POST /analyze-price with valid payload."""
    payload = {"text": "The ticket costs ₹499."}
    response = client.post("/analyze-price", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["source"] == "price"
    assert len(data["entities"]) == 1
    assert data["entities"][0]["amount"] == 499.0
    assert data["entities"][0]["currency"] == "INR"
    assert data["entities"][0]["original_text"] == "₹499"
    assert data["entities"][0]["context"] == "The ticket costs ₹499."


def test_api_analyze_price_validation_empty():
    """Test POST /analyze-price rejects empty and whitespace-only text."""
    res_empty = client.post("/analyze-price", json={"text": ""})
    assert res_empty.status_code == 422

    res_whitespace = client.post("/analyze-price", json={"text": "   \n\t   "})
    assert res_whitespace.status_code == 422


def test_api_analyze_price_validation_oversized():
    """Test POST /analyze-price rejects oversized text (> 5000 chars)."""
    res_oversized = client.post("/analyze-price", json={"text": "A" * 5001})
    assert res_oversized.status_code == 422


def test_api_analyze_price_validation_malformed():
    """Test POST /analyze-price rejects malformed request bodies."""
    res_missing = client.post("/analyze-price", json={})
    assert res_missing.status_code == 422

    res_type = client.post("/analyze-price", json={"text": 12345})
    assert res_type.status_code == 422


def test_predict_endpoint_unaffected():
    """Regression test: verify POST /predict is completely unaffected by price analyzer addition."""
    res = client.post("/predict", json={"text": "Your free trial automatically renews at ₹999/month after 7 days."})
    assert res.status_code == 200
    data = res.json()
    assert data["prediction"] == 1
    assert data["pattern_category"] == "Subscription Trap"
    assert data["model_version"] == "clauseguard-text-v3"


# =====================================================================
# 5. PHASE 8.2 COST-TYPE CLASSIFICATION & RELATIONSHIPS
# =====================================================================

def test_p82_1_base_price():
    """Test 1: 'The ticket costs ₹499.' -> base_price"""
    res = analyzer.analyze("The ticket costs ₹499.")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 499.0
    assert res.entities[0].type == "base_price"


def test_p82_2_base_plus_processing_fee():
    """Test 2: 'The ticket costs ₹499 plus a ₹79 processing fee.' -> base_price + processing_fee"""
    res = analyzer.analyze("The ticket costs ₹499 plus a ₹79 processing fee.")
    assert len(res.entities) == 2
    assert res.entities[0].type == "base_price"
    assert res.entities[1].type == "processing_fee"
    assert res.entities[1].relationship_type == "additional_cost"
    assert res.entities[1].related_entity_index == 0


def test_p82_3_shipping_fee():
    """Test 3: '₹50 shipping fee.' -> shipping_fee"""
    res = analyzer.analyze("₹50 shipping fee.")
    assert len(res.entities) == 1
    assert res.entities[0].type == "shipping_fee"


def test_p82_4_platform_fee():
    """Test 4: '₹20 platform fee.' -> platform_fee"""
    res = analyzer.analyze("₹20 platform fee.")
    assert len(res.entities) == 1
    assert res.entities[0].type == "platform_fee"


def test_p82_5_original_price_now_sale_price():
    """Test 5: '₹999 original price, now ₹699.' -> original_price and sale_price"""
    res = analyzer.analyze("₹999 original price, now ₹699.")
    assert len(res.entities) == 2
    assert res.entities[0].amount == 999.0
    assert res.entities[0].type == "original_price"
    assert res.entities[0].relationship_type == "original_for_discount"
    assert res.entities[0].related_entity_index == 1

    assert res.entities[1].amount == 699.0
    assert res.entities[1].type == "sale_price"
    assert res.entities[1].relationship_type == "discounted_from"
    assert res.entities[1].related_entity_index == 0


def test_p82_6_was_original_now_sale_price():
    """Test 6: 'Was ₹999, now ₹699.' -> original_price and sale_price"""
    res = analyzer.analyze("Was ₹999, now ₹699.")
    assert len(res.entities) == 2
    assert res.entities[0].type == "original_price"
    assert res.entities[1].type == "sale_price"


def test_p82_7_save_discount_amount():
    """Test 7: 'Save ₹300.' -> discount_amount"""
    res = analyzer.analyze("Save ₹300.")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 300.0
    assert res.entities[0].type == "discount_amount"
    assert res.entities[0].relationship_type == "discount"


def test_p82_8_total_price():
    """Test 8: 'Total: ₹628.' -> total_price"""
    res = analyzer.analyze("Total: ₹628.")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 628.0
    assert res.entities[0].type == "total_price"
    assert res.entities[0].relationship_type == "final_total"


def test_p82_9_amount_payable_total_price():
    """Test 9: 'Amount payable ₹628.' -> total_price"""
    res = analyzer.analyze("Amount payable ₹628.")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 628.0
    assert res.entities[0].type == "total_price"
    assert res.entities[0].relationship_type == "final_total"


def test_p82_10_subscription_alternatives_not_added():
    """Test 10: '₹99/month or ₹999/year.' -> two subscription_price entities (not added)"""
    res = analyzer.analyze("₹99/month or ₹999/year.")
    assert len(res.entities) == 2
    assert res.entities[0].amount == 99.0
    assert res.entities[0].type == "subscription_price"
    assert res.entities[0].relationship_type == "alternative"

    assert res.entities[1].amount == 999.0
    assert res.entities[1].type == "subscription_price"
    assert res.entities[1].relationship_type == "alternative"


def test_p82_11_tax():
    """Test 11: 'GST ₹90.' -> tax"""
    res = analyzer.analyze("GST ₹90.")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 90.0
    assert res.entities[0].type == "tax"


def test_p82_12_delivery_fee():
    """Test 12: '₹50 delivery fee.' -> delivery_fee"""
    res = analyzer.analyze("₹50 delivery fee.")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 50.0
    assert res.entities[0].type == "delivery_fee"


def test_p82_13_protection_fee():
    """Test 13: 'Add protection for ₹199.' -> protection_fee"""
    res = analyzer.analyze("Add protection for ₹199.")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 199.0
    assert res.entities[0].type in ["protection_fee", "add_on"]


def test_p82_14_authoritative_total():
    """Test 14: '₹499 + ₹79 processing fee. Total ₹600.' -> 499 base, 79 processing, 600 total (authoritative)"""
    res = analyzer.analyze("₹499 + ₹79 processing fee. Total ₹600.")
    assert len(res.entities) == 3
    assert res.entities[0].amount == 499.0
    assert res.entities[0].type == "base_price"

    assert res.entities[1].amount == 79.0
    assert res.entities[1].type == "processing_fee"
    assert res.entities[1].relationship_type == "additional_cost"
    assert res.entities[1].related_entity_index == 0

    assert res.entities[2].amount == 600.0
    assert res.entities[2].type == "total_price"
    assert res.entities[2].relationship_type == "final_total"


def test_p82_ambiguous_and_isolated():
    """Ambiguous & isolated values are handled conservatively without guessing."""
    # Isolated amount with no context -> unknown
    res_iso = analyzer.analyze("₹499")
    assert len(res_iso.entities) == 1
    assert res_iso.entities[0].type == "unknown"

    # Scarcity phrase -> unknown (does not fabricate a role)
    res_scarcity = analyzer.analyze("Only ₹499 left.")
    assert len(res_scarcity.entities) == 1
    assert res_scarcity.entities[0].type == "unknown"

    # Price starts at -> base_price
    res_start = analyzer.analyze("Price starts at ₹499.")
    assert len(res_start.entities) == 1
    assert res_start.entities[0].type == "base_price"

    # Save -> discount_amount
    res_save = analyzer.analyze("Save ₹499.")
    assert len(res_save.entities) == 1
    assert res_save.entities[0].type == "discount_amount"


def test_p82_no_dark_pattern_decision():
    """PriceAnalyzer must strictly produce financial evidence, not dark-pattern decisions."""
    res = analyzer.analyze("The ticket costs ₹499 plus a ₹79 processing fee.")
    data = res.model_dump()
    assert "dark_pattern" not in data, "dark_pattern decision must NOT be in PriceAnalysisResponse"
    for entity in res.entities:
        assert "dark_pattern" not in entity.model_dump(), "dark_pattern decision must NOT be in PriceEntity"


def test_p82_api_endpoint_returns_cost_types_and_relationships():
    """Test POST /analyze-price returns cost types and relationship metadata."""
    payload = {"text": "The ticket costs ₹499 plus a ₹79 processing fee."}
    response = client.post("/analyze-price", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["source"] == "price"
    assert len(data["entities"]) == 2

    e0 = data["entities"][0]
    assert e0["amount"] == 499.0
    assert e0["currency"] == "INR"
    assert e0["type"] == "base_price"
    assert e0["relationship_type"] == "base_cost"

    e1 = data["entities"][1]
    assert e1["amount"] == 79.0
    assert e1["currency"] == "INR"
    assert e1["type"] == "processing_fee"
    assert e1["relationship_type"] == "additional_cost"
    assert e1["related_entity_index"] == 0


# =====================================================================
# 6. PHASE 8.3 COST CALCULATION & FINANCIAL RELATIONSHIPS
# =====================================================================

def test_p83_1_base_plus_processing_fee_calc():
    """Test 1: 'The ticket costs ₹499 plus a ₹79 processing fee.' -> base=499, additional=79, total=578"""
    res = analyzer.analyze("The ticket costs ₹499 plus a ₹79 processing fee.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.displayed_price.currency == "INR"
    assert res.additional_costs == 79.0
    assert res.calculated_subtotal == 578.0
    assert res.known_total == 578.0
    assert res.total_source == "computed"
    assert res.price_difference == 79.0
    assert res.additional_cost_percentage == 15.83


def test_p83_2_multiple_additive_fees_calc():
    """Test 2: '₹499 + ₹50 shipping + ₹20 platform fee.' -> additional=70, total=569"""
    res = analyzer.analyze("₹499 + ₹50 shipping + ₹20 platform fee.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_costs == 70.0
    assert res.calculated_subtotal == 569.0
    assert res.known_total == 569.0
    assert res.total_source == "computed"
    assert res.price_difference == 70.0


def test_p83_3_explicit_total_priority():
    """Test 3: '₹499 + ₹79 fee. Total ₹600.' -> computed_subtotal=578, explicit_total=600, known_total=600"""
    res = analyzer.analyze("₹499 + ₹79 fee. Total ₹600.")
    assert res.calculated_subtotal == 578.0
    assert res.explicit_total == 600.0
    assert res.known_total == 600.0
    assert res.total_source == "explicit"
    assert res.price_difference == 101.0


def test_p83_4_missing_shipping_amount():
    """Test 4: '₹499 + shipping.' -> known_total=None, additional_costs=None"""
    res = analyzer.analyze("₹499 + shipping.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_costs is None
    assert res.calculated_subtotal is None
    assert res.known_total is None
    assert res.total_source is None


def test_p83_5_discount_original_sale():
    """Test 5: 'Was ₹999, now ₹699.' -> original=999, sale=699, discount=300, discount_pct=30.03"""
    res = analyzer.analyze("Was ₹999, now ₹699.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 699.0
    assert res.discount_amount == 300.0
    assert res.discount_percentage == 30.03
    assert res.price_difference == 300.0


def test_p83_6_same_currency_addition():
    """Test 6: '$20 + $5 shipping.' -> known_total=25.0"""
    res = analyzer.analyze("$20 + $5 shipping.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 20.0
    assert res.displayed_price.currency == "USD"
    assert res.additional_costs == 5.0
    assert res.known_total == 25.0
    assert res.total_source == "computed"


def test_p83_7_cross_currency_not_combined():
    """Test 7: '$20 + €5.' -> cross currency values must NOT be combined"""
    res = analyzer.analyze("$20 + €5.")
    assert res.known_total is None
    assert res.additional_costs is None
    assert res.calculated_subtotal is None


def test_p83_8_alternative_prices_not_added():
    """Test 8: '₹99/month or ₹999/year.' -> alternative=True, known_total=None"""
    res = analyzer.analyze("₹99/month or ₹999/year.")
    assert res.is_alternative_pricing is True
    assert res.known_total is None
    assert res.calculated_subtotal is None
    assert res.additional_costs is None


def test_p83_9_tax_addition():
    """Test 9: '₹499 + ₹90 GST.' -> known_total=589"""
    res = analyzer.analyze("₹499 + ₹90 GST.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_costs == 90.0
    assert res.known_total == 589.0
    assert res.total_source == "computed"


def test_p83_10_multiple_fees_and_handling():
    """Test 10: '₹499 + ₹50 shipping + ₹20 platform fee + ₹10 handling fee.' -> additional=80, known_total=579"""
    res = analyzer.analyze("₹499 + ₹50 shipping + ₹20 platform fee + ₹10 handling fee.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_costs == 80.0
    assert res.known_total == 579.0
    assert res.total_source == "computed"


def test_p83_11_subtractive_discount():
    """Test 11: '₹999 less ₹100 discount.' -> known_total=899"""
    res = analyzer.analyze("₹999 less ₹100 discount.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 999.0
    assert res.discount_amount == 100.0
    assert res.discount_percentage == 10.01
    assert res.known_total == 899.0
    assert res.total_source == "computed"


def test_p83_12_refundable_deposit_not_discount():
    """Test 12: '₹999 refundable deposit.' -> deposit is NOT classified as discount"""
    res = analyzer.analyze("₹999 refundable deposit.")
    assert res.discount_amount is None
    assert res.discount_percentage is None
    for e in res.entities:
        assert e.type != "discount_amount"


def test_p83_zero_base_price_safe():
    """Zero base price calculation protects against zero division in percentage."""
    res = analyzer.analyze("₹0 + ₹79 processing fee.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 0.0
    assert res.additional_costs == 79.0
    assert res.known_total == 79.0
    assert res.total_source == "computed"
    assert res.additional_cost_percentage is None


def test_p83_hard_negatives_produce_no_calculations():
    """Hard negatives do not trigger false calculations or invent totals."""
    for text in ["30-day return period.", "Only 2 seats remaining.", "Save 20%.", "Model 2026."]:
        res = analyzer.analyze(text)
        assert len(res.entities) == 0
        assert res.displayed_price is None
        assert res.additional_costs is None
        assert res.known_total is None
        assert res.is_alternative_pricing is False


def test_p83_isolated_price_no_fabricated_totals():
    """Isolated price with no context does not invent fees or calculations."""
    res = analyzer.analyze("₹499")
    assert len(res.entities) == 1
    assert res.displayed_price is None
    assert res.additional_costs is None
    assert res.known_total is None


def test_p83_api_endpoint_returns_financial_summary():
    """Test POST /analyze-price returns full Phase 8.3 financial summary."""
    payload = {"text": "The ticket costs ₹499 plus a ₹79 processing fee."}
    response = client.post("/analyze-price", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["source"] == "price"
    assert data["displayed_price"] == {"amount": 499.0, "currency": "INR"}
    assert data["additional_costs"] == 79.0
    assert data["explicit_total"] is None
    assert data["calculated_subtotal"] == 578.0
    assert data["known_total"] == 578.0
    assert data["total_source"] == "computed"
    assert data["price_difference"] == 79.0
    assert data["additional_cost_percentage"] == 15.83
    assert data["discount_amount"] is None
    assert data["discount_percentage"] is None
    assert data["is_alternative_pricing"] is False


# =====================================================================
# 7. PHASE 8.4 — TRIAL, RENEWAL & RECURRING COST TESTS
# =====================================================================

def test_p84_01_free_trial_then_renewal():
    """Test 1: '7-day free trial, then ₹999/month.'"""
    res = analyzer.analyze("7-day free trial, then ₹999/month.")
    assert res.trial_price == 0.0
    assert res.trial_duration_days == 7
    assert res.trial_currency == "INR"
    assert res.renewal_price == 999.0
    assert res.renewal_currency == "INR"
    assert res.billing_period == "month"
    assert res.recurring is True
    # Semantics: Renewal price following a free trial must NOT be labeled as displayed_price
    assert res.displayed_price is None

    # Validate relationships
    trial_ent = next(e for e in res.entities if e.type == "trial_price")
    renew_ent = next(e for e in res.entities if e.type == "renewal_price")
    assert trial_ent.relationship_type == "trial_offer"
    assert renew_ent.relationship_type == "renews_from"
    assert renew_ent.recurring is True
    assert renew_ent.billing_period == "month"


def test_p84_02_promotional_first_month_then_renewal():
    """Test 2: '₹99 for the first month, then ₹999/month.'"""
    res = analyzer.analyze("₹99 for the first month, then ₹999/month.")
    assert res.initial_price == 99.0
    assert res.initial_currency == "INR"
    assert res.renewal_price == 999.0
    assert res.renewal_currency == "INR"
    assert res.later_price == 999.0
    assert res.billing_period == "month"
    assert res.recurring is True
    assert res.promotion_duration_months == 1
    # Semantics: Explicit initial promotional price is populated as displayed_price
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 99.0
    assert res.displayed_price.currency == "INR"

    renew_ent = next(e for e in res.entities if e.type == "renewal_price")
    assert renew_ent.relationship_type == "renews_from"
    assert renew_ent.billing_period == "month"
    assert renew_ent.recurring is True


def test_p84_03_monthly_subscription():
    """Test 3: '₹999/month.'"""
    res = analyzer.analyze("₹999/month.")
    assert res.recurring is True
    assert res.billing_period == "month"
    assert len(res.entities) == 1
    assert res.entities[0].amount == 999.0
    assert res.entities[0].billing_period == "month"
    assert res.entities[0].recurring is True
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 999.0
    assert res.displayed_price.currency == "INR"


def test_p84_04_annual_subscription():
    """Test 4: '₹999 annually.'"""
    res = analyzer.analyze("₹999 annually.")
    assert res.recurring is True
    assert res.billing_period == "year"
    assert len(res.entities) == 1
    assert res.entities[0].amount == 999.0
    assert res.entities[0].billing_period == "year"
    assert res.entities[0].recurring is True


def test_p84_05_weekly_subscription():
    """Test 5: '₹99/week.'"""
    res = analyzer.analyze("₹99/week.")
    assert res.recurring is True
    assert res.billing_period == "week"
    assert len(res.entities) == 1
    assert res.entities[0].amount == 99.0
    assert res.entities[0].billing_period == "week"
    assert res.entities[0].recurring is True


def test_p84_06_daily_subscription():
    """Test 6: '₹10/day.'"""
    res = analyzer.analyze("₹10/day.")
    assert res.recurring is True
    assert res.billing_period == "day"
    assert len(res.entities) == 1
    assert res.entities[0].amount == 10.0
    assert res.entities[0].billing_period == "day"
    assert res.entities[0].recurring is True


def test_p84_07_multistage_subscription():
    """Test 7: 'First 3 months ₹199, then ₹799/month.'"""
    res = analyzer.analyze("First 3 months ₹199, then ₹799/month.")
    assert res.initial_price == 199.0
    assert res.initial_currency == "INR"
    assert res.promotion_duration_months == 3
    assert res.renewal_price == 799.0
    assert res.renewal_currency == "INR"
    assert res.billing_period == "month"
    assert res.recurring is True
    assert res.price_difference == 600.0
    assert res.price_change_percentage == 301.51
    # Semantics: Explicit initial promotional price is populated as displayed_price
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 199.0
    assert res.displayed_price.currency == "INR"


def test_p84_08_alternative_recurring_periods():
    """Test 8: '₹99/month or ₹999/year.'"""
    res = analyzer.analyze("₹99/month or ₹999/year.")
    assert res.is_alternative_pricing is True
    assert res.known_total is None
    assert len(res.entities) == 2
    assert res.entities[0].billing_period == "month"
    assert res.entities[0].recurring is True
    assert res.entities[1].billing_period == "year"
    assert res.entities[1].recurring is True
    assert res.displayed_price is None


def test_p84_09_multicurrency_recurring():
    """Test 9: '$10/month or €9/month.'"""
    res = analyzer.analyze("$10/month or €9/month.")
    assert res.is_alternative_pricing is True
    assert res.known_total is None
    assert len(res.entities) == 2
    assert res.entities[0].currency == "USD"
    assert res.entities[0].amount == 10.0
    assert res.entities[0].billing_period == "month"
    assert res.entities[1].currency == "EUR"
    assert res.entities[1].amount == 9.0
    assert res.entities[1].billing_period == "month"
    assert res.displayed_price is None


def test_p84_10_non_recurring_today():
    """Test 10: '₹999 today.'"""
    res = analyzer.analyze("₹999 today.")
    assert res.recurring is False
    assert res.billing_period is None
    assert len(res.entities) == 1
    assert res.entities[0].amount == 999.0
    assert res.entities[0].recurring is False
    assert res.entities[0].billing_period is None


def test_p84_11_non_recurring_onetime():
    """Test 11: 'One-time payment of ₹999.'"""
    res = analyzer.analyze("One-time payment of ₹999.")
    assert res.recurring is False
    assert res.billing_period is None
    assert len(res.entities) == 1
    assert res.entities[0].amount == 999.0
    assert res.entities[0].recurring is False
    assert res.entities[0].billing_period is None


def test_p84_12_trial_negative_return_period():
    """Test 12: '30-day return period.'"""
    res = analyzer.analyze("30-day return period.")
    assert len(res.entities) == 0
    assert res.trial_duration_days is None
    assert res.trial_price is None


def test_p84_13_trial_negative_warranty():
    """Test 13: '30-day warranty.'"""
    res = analyzer.analyze("30-day warranty.")
    assert len(res.entities) == 0
    assert res.trial_duration_days is None
    assert res.trial_price is None


def test_p84_14_renewal_negative_password():
    """Test 14: 'Renew your password every 30 days.'"""
    res = analyzer.analyze("Renew your password every 30 days.")
    assert len(res.entities) == 0
    assert res.renewal_price is None
    assert res.recurring is False


def test_p84_15_free_trial_missing_renewal_amount():
    """Test 15: '7-day free trial, then regular monthly pricing.'"""
    res = analyzer.analyze("7-day free trial, then regular monthly pricing.")
    assert res.trial_price == 0.0
    assert res.trial_duration_days == 7
    assert res.renewal_price is None
    assert res.recurring is True
    assert res.billing_period == "month"
    assert res.displayed_price is None


def test_p84_16_subscription_renews_missing_period():
    """Test 16: 'Your subscription renews at ₹999.'"""
    res = analyzer.analyze("Your subscription renews at ₹999.")
    assert res.renewal_price == 999.0
    assert res.renewal_currency == "INR"
    assert res.billing_period is None
    assert res.recurring is True
    # Semantics: Renewal price alone without an initial/base price must not be displayed_price
    assert res.displayed_price is None


def test_p84_17_free_trial_standalone():
    """Test 17: 'Free 7-day trial.'"""
    res = analyzer.analyze("Free 7-day trial.")
    assert res.trial_price == 0.0
    assert res.trial_duration_days == 7
    assert res.renewal_price is None
    assert res.billing_period is None
    assert res.recurring is False
    assert res.displayed_price is None


def test_p84_18_price_increase_percentage_math():
    """Test 18: '₹199 for the first month, then ₹799/month.'"""
    res = analyzer.analyze("₹199 for the first month, then ₹799/month.")
    assert res.initial_price == 199.0
    assert res.renewal_price == 799.0
    assert res.billing_period == "month"
    assert res.recurring is True
    assert res.price_difference == 600.0
    assert res.price_change_percentage == 301.51
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 199.0


def test_p84_19_zero_trial_then_renewal():
    """Test 19: '₹0 trial, then ₹499/month.'"""
    res = analyzer.analyze("₹0 trial, then ₹499/month.")
    assert res.trial_price == 0.0
    assert res.trial_currency == "INR"
    assert res.renewal_price == 499.0
    assert res.renewal_currency == "INR"
    assert res.billing_period == "month"
    assert res.recurring is True
    # Semantics: Renewal price following a ₹0 trial must NOT be labeled as displayed_price
    assert res.displayed_price is None


def test_p84_20_multicurrency_annual_alternative():
    """Test 20: '₹999/year or $99/year.'"""
    res = analyzer.analyze("₹999/year or $99/year.")
    assert res.is_alternative_pricing is True
    assert res.known_total is None
    assert len(res.entities) == 2
    assert res.entities[0].currency == "INR"
    assert res.entities[0].amount == 999.0
    assert res.entities[0].billing_period == "year"
    assert res.entities[0].recurring is True
    assert res.entities[1].currency == "USD"
    assert res.entities[1].amount == 99.0
    assert res.entities[1].billing_period == "year"
    assert res.entities[1].recurring is True
    assert res.displayed_price is None


def test_p84_21_trial_negative_version_launched():
    """Test 21: 'Trial version launched in 2026.'"""
    res = analyzer.analyze("Trial version launched in 2026.")
    assert len(res.entities) == 0
    assert res.trial_duration_days is None
    assert res.trial_price is None


def test_p84_22_api_endpoint_recurring_and_trial():
    """Test 22: POST /analyze-price with trial and renewal text."""
    payload = {"text": "7-day free trial, then ₹999/month."}
    response = client.post("/analyze-price", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["source"] == "price"
    assert data["trial_price"] == 0.0
    assert data["trial_duration_days"] == 7
    assert data["renewal_price"] == 999.0
    assert data["renewal_currency"] == "INR"
    assert data["billing_period"] == "month"
    assert data["recurring"] is True
    assert data["displayed_price"] is None


def test_p84_23_paid_trial_displayed_price():
    """Test 23: Paid trial establishes upfront trial price as displayed_price."""
    res = analyzer.analyze("₹99 for a 7-day trial, then ₹999/month.")
    assert res.trial_price == 99.0
    assert res.trial_duration_days == 7
    assert res.renewal_price == 999.0
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 99.0
    assert res.displayed_price.currency == "INR"


def test_p84_24_explicit_base_price_with_free_trial_and_renewal():
    """Test 24: Explicit base price keyword establishes displayed_price even with trial."""
    res = analyzer.analyze("Base price is ₹999/month with a 7-day free trial.")
    assert res.trial_price == 0.0
    assert res.trial_duration_days == 7
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 999.0
    assert res.displayed_price.currency == "INR"


# =====================================================================
# 8. PHASE 8.5 LATE-DISCLOSURE & PRICE-CHANGE DETECTION (SECTIONS A - P)
# =====================================================================

# Section A: Basic Price
def test_p85_a_basic_price_ordinary():
    """A. Ordinary price extraction and presentation without fees."""
    res = analyzer.analyze("Samsung TV — ₹49,999")
    assert len(res.entities) == 1
    assert res.entities[0].amount == 49999.0
    assert res.entities[0].currency == "INR"
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 49999.0
    assert res.displayed_price.currency == "INR"
    assert res.additional_costs is None
    assert res.additional_cost_detected is False
    assert res.late_disclosure_detected is False
    assert res.price_change_detected is False
    assert res.is_alternative_pricing is False


# Section B: Additional Fee
def test_p85_b_additional_fee_inclusive_alongside():
    """B. Fee disclosed alongside as inclusive is not late disclosure."""
    res = analyzer.analyze("Ticket price is ₹499 including a ₹79 processing fee.")
    assert len(res.entities) == 2
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_cost_detected is False
    assert res.late_disclosure_detected is False
    assert res.known_total == 499.0
    assert res.price_change_detected is False


# Section C: Late-Disclosed Fee
def test_p85_c_late_disclosed_fee():
    """C. Fee disclosed after initial price in separate statement is late disclosure."""
    res = analyzer.analyze("Ticket price is ₹499. A processing fee of ₹79 applies.")
    assert len(res.entities) == 2
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_cost == 79.0
    assert res.additional_costs == 79.0
    assert res.calculated_subtotal == 578.0
    assert res.known_total == 578.0
    assert res.additional_cost_detected is True
    assert res.late_disclosure_detected is True
    assert res.late_disclosed is True
    assert res.initial_price_position is not None
    assert res.additional_cost_position is not None
    assert res.additional_cost_position > res.initial_price_position


# Section D: Explicit Total
def test_p85_d_explicit_total_authoritative():
    """D. Explicit total is authoritative and preserves both explicit and computed values."""
    res = analyzer.analyze("Ticket price ₹499. Processing fee ₹79. Total ₹600.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_cost == 79.0
    assert res.calculated_subtotal == 578.0
    assert res.explicit_total == 600.0
    assert res.known_total == 600.0
    assert res.total_source == "explicit"
    assert res.additional_cost_detected is True
    assert res.late_disclosure_detected is True


# Section E: Calculated Subtotal
def test_p85_e_calculated_subtotal():
    """E. Subtotal computed correctly from base and multiple fees."""
    res = analyzer.analyze("Item price ₹1,000. Delivery fee ₹100. Platform fee ₹50.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 1000.0
    assert res.additional_cost == 150.0
    assert res.calculated_subtotal == 1150.0
    assert res.known_total == 1150.0
    assert res.total_source == "computed"
    assert res.additional_cost_detected is True
    assert res.late_disclosure_detected is True


# Section F: Price Increase
def test_p85_f_price_increase():
    """F. Explicit price increase statement from X to Y."""
    res = analyzer.analyze("Price increased from ₹999 to ₹1299.")
    assert res.initial_price == 999.0
    assert res.later_price == 1299.0
    assert res.previous_price == 999.0
    assert res.current_price == 1299.0
    assert res.price_difference == 300.0
    assert res.price_change == 300.0
    assert res.price_change_percentage == 30.03
    assert res.price_change_direction == "increase"
    assert res.price_change_detected is True
    assert res.price_changed is True
    assert res.late_disclosure_detected is False


# Section G: Price Decrease
def test_p85_g_price_decrease():
    """G. Explicit price decrease statement from X to Y."""
    res = analyzer.analyze("Price dropped from ₹1299 to ₹999.")
    assert res.initial_price == 1299.0
    assert res.later_price == 999.0
    assert res.previous_price == 1299.0
    assert res.current_price == 999.0
    assert res.price_difference == 300.0
    assert res.price_change == -300.0
    assert res.price_change_direction == "decrease"
    assert res.price_change_detected is True
    assert res.price_changed is True
    assert res.late_disclosure_detected is False


# Section H: Alternative Pricing
def test_p85_h_alternative_pricing():
    """H. Alternative pricing options are conservative and isolated."""
    res1 = analyzer.analyze("Choose between ₹499 and ₹999.")
    assert res1.is_alternative_pricing is True
    assert res1.price_change_detected is False
    assert res1.price_changed is False
    assert res1.price_change_direction is None
    assert res1.late_disclosure_detected is False

    res2 = analyzer.analyze("₹499 for standard, ₹999 for premium.")
    assert res2.is_alternative_pricing is True
    assert res2.price_change_detected is False
    assert res2.late_disclosure_detected is False


# Section I: Discount
def test_p85_i_discount_original_and_sale():
    """I. Original price and sale price discount relationship."""
    res = analyzer.analyze("Original price ₹1299, sale price ₹999.")
    assert res.discount_amount == 300.0
    assert res.discount_percentage == 23.09
    assert res.price_difference == 300.0
    assert res.price_change_detected is False
    assert res.late_disclosure_detected is False
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 999.0


# Section J: Trial → Renewal
def test_p85_j_trial_to_renewal():
    """J. Free trial followed by renewal: displayed_price must be null."""
    res = analyzer.analyze("7-day free trial, then ₹999/month.")
    assert res.trial_price == 0.0
    assert res.trial_duration_days == 7
    assert res.renewal_price == 999.0
    assert res.renewal_currency == "INR"
    assert res.billing_period == "month"
    assert res.recurring is True
    assert res.displayed_price is None
    assert res.renewal_price_detected is True
    assert res.late_disclosure_detected is False
    assert res.price_change_detected is False


# Section K: Promotional → Renewal
def test_p85_k_promotional_to_renewal():
    """K. Promotional introductory price transitioning to recurring renewal price."""
    res = analyzer.analyze("₹499 for the first month, then ₹999/month.")
    assert res.initial_price == 499.0
    assert res.later_price == 999.0
    assert res.renewal_price == 999.0
    assert res.billing_period == "month"
    assert res.recurring is True
    assert res.price_difference == 500.0
    assert res.price_change_percentage == 100.2
    assert res.price_change_direction == "increase"
    assert res.price_change_detected is True
    assert res.renewal_price_detected is True
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.is_alternative_pricing is False


# Section L: Multi-Currency
def test_p85_l_multi_currency_safety():
    """L. Multi-currency values must never be combined or confused."""
    res = analyzer.analyze("Price is ₹499 or $10.")
    assert len(res.entities) == 2
    assert res.is_alternative_pricing is True
    assert res.known_total is None
    assert res.calculated_subtotal is None
    assert res.additional_costs is None
    assert res.price_change_detected is False


# Section M: Hard Negatives
def test_p85_m_hard_negatives():
    """M. Conservative rejection of non-monetary and non-price-change items."""
    # Inclusive fees
    res_tax = analyzer.analyze("₹999 including all taxes.")
    assert res_tax.additional_cost_detected is False
    assert res_tax.late_disclosure_detected is False

    res_ship = analyzer.analyze("₹499 including shipping.")
    assert res_ship.additional_cost_detected is False
    assert res_ship.late_disclosure_detected is False

    # Standalone savings
    res_save = analyzer.analyze("Save ₹300 when you subscribe.")
    assert res_save.price_change_detected is False
    assert res_save.late_disclosure_detected is False

    # Non-monetary items
    assert len(analyzer.analyze("2 seats available.").entities) == 0
    assert len(analyzer.analyze("30-day return policy.").entities) == 0
    assert len(analyzer.analyze("Order number 2026.").entities) == 0
    assert len(analyzer.analyze("20% discount.").entities) == 0
    assert len(analyzer.analyze("Phone support available at 1800-123-4567.").entities) == 0
    assert len(analyzer.analyze("Model number X999.").entities) == 0


# Section N: Ambiguous Wording
def test_p85_n_ambiguous_wording():
    """N. Ambiguous and isolated monetary values without roles."""
    res = analyzer.analyze("₹499")
    assert len(res.entities) == 1
    assert res.entities[0].type == "unknown"
    assert res.displayed_price is None
    assert res.price_change_detected is False
    assert res.late_disclosure_detected is False


# Section O: Explicit Total vs Calculated Subtotal Discrepancy
def test_p85_o_explicit_total_vs_calculated_subtotal():
    """O. Preserve discrepancy between calculated subtotal and explicit total."""
    res = analyzer.analyze("₹499 + ₹79 processing fee. Total ₹600.")
    assert res.displayed_price is not None
    assert res.displayed_price.amount == 499.0
    assert res.additional_cost == 79.0
    assert res.calculated_subtotal == 578.0
    assert res.explicit_total == 600.0
    assert res.known_total == 600.0
    assert res.total_source == "explicit"
    assert res.price_difference == 101.0
    assert res.late_disclosure_detected is True


# Section P: Displayed-Price Semantic Correctness Regression
def test_p85_p_displayed_price_semantic_correctness_regression():
    """P. Regression: Renewal price following free trial must NOT be labeled as displayed_price."""
    res = analyzer.analyze("7-day free trial, then ₹999/month.")
    assert res.displayed_price is None
    assert res.trial_price == 0.0
    assert res.renewal_price == 999.0

    res_paid = analyzer.analyze("₹99 for 7-day trial, then ₹999/month.")
    assert res_paid.displayed_price is not None
    assert res_paid.displayed_price.amount == 99.0
    assert res_paid.trial_price == 99.0
    assert res_paid.renewal_price == 999.0


# Section Q: Position and Disclosure Order Tracking
def test_p85_q_position_and_disclosure_order_tracking():
    """Q. Verify position_start, position_end, sentence_index, and disclosure_order on entities."""
    res = analyzer.analyze("Ticket price is ₹499. A processing fee of ₹79 applies.")
    assert len(res.entities) == 2
    e0 = res.entities[0]
    e1 = res.entities[1]

    assert e0.amount == 499.0
    assert e0.position_start == 16
    assert e0.position_end == 20
    assert e0.sentence_index == 0
    assert e0.disclosure_order == 0

    assert e1.amount == 79.0
    assert e1.position_start == 42
    assert e1.position_end == 45
    assert e1.sentence_index == 1
    assert e1.disclosure_order == 1





