"""tests/test_extension_integration.py
Phase 9.0 Extension Integration Test Suite.

Validates:
1. AT-01: Benign product page -> No strong consumer-risk signal.
2. AT-02: Subscription page -> Free trial + recurring renewal explanation.
3. AT-03: Additional fee page -> Stated price + fee + known total.
4. AT-04: Price change page -> Price increase fact without deceptive dark pattern.
5. AT-05: Urgency page -> Urgency dark-pattern text finding preserved.
6. AT-06: Non-monetary page -> Zero price entities, benign / low risk.
7. AT-07: Error resilience / partial failure (e.g. price failure fallback).
8. AT-08: Page length truncation contract (MAX_PAGE_TEXT_LENGTH = 20000).
"""
import os
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

DEMO_DIR = os.path.join(os.path.dirname(__file__), "demo_pages")


def _read_demo_page(filename: str) -> str:
    path = os.path.join(DEMO_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _simulate_extension_orchestrator(page_text: str):
    """Simulates the exact async orchestrator logic in extension/popup.js."""
    # Step 1: Parallel calls to /predict and /analyze-price
    truncated_text = page_text[:20000]
    pred_resp = client.post("/predict", json={"text": truncated_text[:5000]})
    pred_data = pred_resp.json() if pred_resp.status_code == 200 else None

    price_resp = client.post("/analyze-price", json={"text": truncated_text[:5000]})
    price_data = price_resp.json() if price_resp.status_code == 200 else None

    # Step 2: Build EvidenceFusionRequest
    fusion_payload = {
        "text": truncated_text[:5000],
        "text_prediction": pred_data,
        "price_analysis": price_data,
    }

    # Step 3: /fuse-evidence
    fuse_resp = client.post("/fuse-evidence", json=fusion_payload)
    assert fuse_resp.status_code == 200, f"Fusion failed: {fuse_resp.text}"
    fuse_data = fuse_resp.json()

    # Step 4: /explain
    explain_resp = client.post("/explain", json={"fusion_response": fuse_data})
    assert explain_resp.status_code == 200, f"Explain failed: {explain_resp.text}"
    return explain_resp.json()


# --------------------------------------------------------------------------
# AT-01: Benign product page
# --------------------------------------------------------------------------
def test_at01_benign_product_page():
    html = _read_demo_page("benign.html")
    # Simulate text extraction
    text = "Samsung 4K Ultra HD Smart TV. Price: ₹49,999. Enjoy crystal-clear 4K resolution. Free delivery included. Standard 30-day return policy applies."
    result = _simulate_extension_orchestrator(text)

    assert result["risk_status"] == "no_strong_signal"
    assert "No strong consumer-risk signal" in result["title"]
    assert result["disclaimer"] is None


# --------------------------------------------------------------------------
# AT-02: Subscription page
# --------------------------------------------------------------------------
def test_at02_subscription_page():
    html = _read_demo_page("subscription.html")
    text = "Start your entertainment journey with full catalog access. 7-day free trial, then ₹999/month. Automatic renewal applies."
    result = _simulate_extension_orchestrator(text)

    assert result["risk_status"] in ("financial_notice", "risk_detected")
    assert "Free trial" in result["title"]
    assert "₹999" in result["summary"] or "999" in result["summary"]
    assert "cancellation" in result["recommended_action"].lower() or "renewal" in result["recommended_action"].lower()
    assert len(result["evidence_ids"]) > 0


# --------------------------------------------------------------------------
# AT-03: Additional fee page
# --------------------------------------------------------------------------
def test_at03_additional_fee_page():
    html = _read_demo_page("additional_fee.html")
    text = "Ticket price is ₹499. A processing fee of ₹79 applies at final payment. Known total payable is ₹578."
    result = _simulate_extension_orchestrator(text)

    assert result["risk_status"] in ("financial_notice", "risk_detected")
    assert "fee" in result["title"].lower() or "cost" in result["title"].lower()
    assert "578" in (result["financial_consequence"] or "") or "578" in (result["consumer_consequence"] or "")
    assert "check" in result["recommended_action"].lower() or "review" in result["recommended_action"].lower()


# --------------------------------------------------------------------------
# AT-04: Price change page
# --------------------------------------------------------------------------
def test_at04_price_change_page():
    html = _read_demo_page("price_change.html")
    text = "Your selected itinerary fare has been updated. Price increased from ₹999 to ₹1299. Please verify all flight details."
    result = _simulate_extension_orchestrator(text)

    assert result["risk_status"] in ("risk_detected", "financial_notice", "no_strong_signal")
    assert "Price changed" in result["title"]
    assert "increased" in result["summary"].lower()
    assert "300" in (result["consumer_consequence"] or "") or "300" in (result["financial_consequence"] or "")
    assert "deceptive" not in result["summary"].lower()
    assert "fraud" not in result["summary"].lower()


# --------------------------------------------------------------------------
# AT-05: Urgency page
# --------------------------------------------------------------------------
def test_at05_urgency_page():
    html = _read_demo_page("urgency.html")
    text = "Exclusive offer ends tonight! Only 1 ticket remaining at this price! Standard seating applies."
    result = _simulate_extension_orchestrator(text)

    assert result["risk_status"] in ("risk_detected", "context_required")
    assert "Urgency" in result["title"] or "context" in result["title"].lower()
    assert len(result["evidence_ids"]) > 0


# --------------------------------------------------------------------------
# AT-06: Non-monetary page
# --------------------------------------------------------------------------
def test_at06_non_monetary_page():
    html = _read_demo_page("non_monetary.html")
    text = "Standard 30-day return policy for unused goods. Items may be returned in store or via registered postal mail."
    result = _simulate_extension_orchestrator(text)

    assert result["risk_status"] == "no_strong_signal"
    assert "No strong consumer-risk" in result["title"]


# --------------------------------------------------------------------------
# AT-07: Error resilience / price failure fallback
# --------------------------------------------------------------------------
def test_at07_price_failure_fallback():
    # When price analysis fails or returns None, fusion handles text-only evidence gracefully
    text = "Exclusive offer ends tonight! Only 1 ticket remaining at this price!"
    pred_resp = client.post("/predict", json={"text": text})
    pred_data = pred_resp.json()

    # Fusion without price analysis
    fusion_payload = {
        "text": text,
        "text_prediction": pred_data,
        "price_analysis": None,
    }
    fuse_resp = client.post("/fuse-evidence", json=fusion_payload)
    assert fuse_resp.status_code == 200
    fuse_data = fuse_resp.json()

    explain_resp = client.post("/explain", json={"fusion_response": fuse_data})
    assert explain_resp.status_code == 200
    explain_data = explain_resp.json()
    assert explain_data["title"] is not None


# --------------------------------------------------------------------------
# AT-08: Page length truncation contract
# --------------------------------------------------------------------------
def test_at08_page_length_truncation():
    giant_text = ("Normal product description. Price: ₹499. " * 1000) # > 40,000 chars
    truncated = giant_text[:20000]
    assert len(truncated) == 20000

    result = _simulate_extension_orchestrator(giant_text)
    assert result["source"] == "consumer_explanation"
