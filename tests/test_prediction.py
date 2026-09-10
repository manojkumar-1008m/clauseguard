# tests/test_prediction.py
"""Tests for the /predict endpoint of ClauseGuard backend."""

import pytest
from fastapi.testclient import TestClient

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.main import app

client = TestClient(app)

@pytest.mark.parametrize(
    "input_text,expected_pred",
    [
        ("Canceling your subscription requires contacting customer support.", 1),
        ("The total price including all mandatory fees is shown before payment.", 0),
    ],
)
def test_predict_endpoint(input_text, expected_pred):
    response = client.post("/predict", json={"text": input_text})
    assert response.status_code == 200
    data = response.json()
    assert "prediction" in data and "label" in data and "confidence" in data
    assert data["prediction"] == expected_pred
    # Label must correspond to prediction
    expected_label = "potential_dark_pattern" if expected_pred == 1 else "not_dark_pattern"
    assert data["label"] == expected_label
    # Confidence may be None or a float between 0 and 1
    if data["confidence"] is not None:
        assert 0.0 <= data["confidence"] <= 1.0
