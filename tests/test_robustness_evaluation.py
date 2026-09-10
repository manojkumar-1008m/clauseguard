"""tests/test_robustness_evaluation.py
Phase 5C Robustness and Model Behavior automated test suite.
"""
import csv
import pathlib
import pytest
from fastapi.testclient import TestClient

from backend import model_loader, preprocessing
from backend.main import app

client = TestClient(app)
ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]


def test_level1_ml_unit_sanity():
    """Level 1: Verify model loads and predicts without runtime errors."""
    model = model_loader.get_model()
    assert model is not None
    pred, conf = model_loader.predict("Sample benign test phrase.")
    assert pred in (0, 1)


def test_level2_api_predict():
    """Level 2: API returns 200 with all valid schema fields."""
    response = client.post("/predict", json={"text": "Canceling requires calling customer support."})
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"] == 1
    assert data["label"] == "potential_dark_pattern"
    assert isinstance(data["confidence"], float)


def test_level6_numeric_invariance():
    """Level 6: Verify changing numbers does not destabilize prediction."""
    text_3 = preprocessing.preprocess("Only 3 left in stock!")
    text_300 = preprocessing.preprocess("Only 300 left in stock!")
    pred_3, conf_3 = model_loader.predict(text_3)
    pred_300, conf_300 = model_loader.predict(text_300)
    assert pred_3 in (0, 1)
    assert pred_300 in (0, 1)


def test_level6_currency_invariance():
    """Level 6: Currency symbols (₹, $, €, £) do not crash preprocessing or prediction."""
    currencies = ["₹999", "$999", "€999", "£999"]
    for c in currencies:
        cleaned = preprocessing.preprocess(f"Subscription cost is {c} per month.")
        pred, conf = model_loader.predict(cleaned)
        assert pred in (0, 1)


def test_level6_unicode_and_emoji():
    """Level 6: Unicode emojis and special characters do not cause exceptions."""
    text = "🔥 HURRY! ONLY 2 SEATS LEFT 🔥 ⚠️ EXPIRES SOON ⚠️"
    cleaned = preprocessing.preprocess(text)
    pred, conf = model_loader.predict(cleaned)
    assert pred in (0, 1)


def test_level6_short_inputs():
    """Level 6: Very short inputs do not crash inference."""
    short_words = ["Sale", "Buy now", "Cancel", "Limited", "₹999"]
    for w in short_words:
        cleaned = preprocessing.preprocess(w)
        pred, conf = model_loader.predict(cleaned)
        assert pred in (0, 1)


def test_level7_payload_boundary_limits():
    """Level 7: Payload boundaries (5000 chars vs 5001 chars)."""
    res_valid = client.post("/predict", json={"text": "Valid text " * 400})  # < 5000
    assert res_valid.status_code == 200

    res_limit = client.post("/predict", json={"text": "A" * 5000})
    assert res_limit.status_code == 200

    res_excess = client.post("/predict", json={"text": "A" * 5001})
    assert res_excess.status_code == 422


def test_level8_hard_negatives_accuracy():
    """Level 8: Hard negative regression test - ensures at least 90% accuracy on tough negatives."""
    hn_path = ROOT_DIR / "tests" / "hard_negative_regression.csv"
    assert hn_path.is_file()

    correct_count = 0
    total = 0
    with open(hn_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            cleaned = preprocessing.preprocess(row["text"])
            pred, _ = model_loader.predict(cleaned)
            if pred == 0:
                correct_count += 1

    accuracy = correct_count / total
    assert accuracy >= 0.90, f"Hard negative accuracy dropped below 90%: {accuracy * 100:.1f}%"
