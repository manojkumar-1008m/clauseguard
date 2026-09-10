import sys
import os
import pathlib
import pytest
from fastapi.testclient import TestClient

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.main import app

client = TestClient(app)

def test_subscription_trap():
    """Verify subscription trap detection, category mapping, and consequence."""
    text = "Your free trial automatically renews at ₹999/month after 7 days."
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"] == 1
    assert data["label"] == "potential_dark_pattern"
    assert data["pattern_category"] == "Subscription Trap"
    assert data["evidence"] is not None
    assert "renews" in data["evidence"].lower()
    assert data["consumer_consequence"] is not None
    assert "renew automatically" in data["consumer_consequence"].lower()
    assert data["requires_context"] is False

def test_drip_pricing():
    """Verify drip pricing detection, category mapping, and consequence."""
    text = "The processing fee is revealed after payment details are entered."
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"] == 1
    assert data["label"] == "potential_dark_pattern"
    assert data["pattern_category"] == "Drip Pricing"
    assert data["evidence"] is not None
    assert "revealed" in data["evidence"].lower()
    assert "additional fee" in data["consumer_consequence"].lower()

def test_benign_fee_disclosure():
    """Verify benign fee disclosure is not classified as a dark pattern."""
    text = "The processing fee is displayed clearly before payment."
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"] == 0
    assert data["label"] == "not_dark_pattern"
    assert data["pattern_category"] is None
    assert data["consumer_consequence"] is None

def test_obstruction():
    """Verify obstruction detection for phone-only/support cancellation."""
    text = "To cancel your subscription, contact customer support by phone."
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"] == 1
    assert data["label"] == "potential_dark_pattern"
    assert data["pattern_category"] == "Obstruction"
    assert data["evidence"] is not None
    assert "contact" in data["evidence"].lower()
    assert "extra steps" in data["consumer_consequence"].lower()

def test_benign_cancellation():
    """Verify self-serve cancellation from account settings is benign."""
    text = "You can cancel your subscription at any time from Account Settings."
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"] == 0
    assert data["label"] == "not_dark_pattern"
    assert data["pattern_category"] is None
    assert data["consumer_consequence"] is None

def test_sneaking():
    """Verify sneaking detection for pre-selected warranties."""
    text = "An extended warranty has already been selected for your order."
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"] == 1
    assert data["label"] == "potential_dark_pattern"
    assert data["pattern_category"] == "Sneaking"
    assert data["evidence"] is not None
    assert "selected" in data["evidence"].lower()
    assert "automatically" in data["consumer_consequence"].lower()

def test_scarcity():
    """Verify scarcity detection for low stock pressure."""
    text = "Only three left — order soon."
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"] == 1
    assert data["label"] == "potential_dark_pattern"
    assert data["pattern_category"] == "Scarcity"
    assert data["evidence"] is not None
    assert "only three left" in data["evidence"].lower()
    assert "pressure to purchase quickly" in data["consumer_consequence"].lower()

def test_benign_inventory():
    """Verify factual inventory/variant statements are not scarcity dark patterns."""
    text = "Only three colors are currently available."
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"] == 0
    assert data["label"] == "not_dark_pattern"
    assert data["pattern_category"] is None

def test_urgency():
    """Verify urgency detection for countdowns / expiration claims."""
    text = "This offer expires tonight."
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"] == 1
    assert data["label"] == "potential_dark_pattern"
    assert data["pattern_category"] == "Urgency"
    assert data["evidence"] is not None
    assert "expires tonight" in data["evidence"].lower()
    assert "pressure" in data["consumer_consequence"].lower()

def test_forced_action():
    """Verify forced action detection for mandatory account creation gates."""
    text = "You must create an account before continuing."
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"] == 1
    assert data["label"] == "potential_dark_pattern"
    assert data["pattern_category"] == "Forced Action"
    assert data["evidence"] is not None
    assert "must create an account before continuing" in data["evidence"].lower()
    assert "required to provide information" in data["consumer_consequence"].lower()

def test_confirm_shaming():
    """Verify confirmshaming detection for emotionally manipulative opt-outs."""
    text = "No thanks, I don't want to protect my purchase."
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"] == 1
    assert data["label"] == "potential_dark_pattern"
    assert data["pattern_category"] == "Confirm Shaming"
    assert data["evidence"] is not None
    assert "no thanks" in data["evidence"].lower()
    assert "negative language" in data["consumer_consequence"].lower()

def test_short_text_context_guard():
    """Verify short isolated phrases trigger requires_context without confident pattern mapping."""
    text = "Buy now"
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 200
    data = response.json()
    assert data["requires_context"] is True
    assert data["pattern_category"] is None
    assert data["evidence"] == "Buy now"
    assert data["consumer_consequence"] is None
