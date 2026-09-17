# tests/test_api.py
"""API endpoint integration tests for ClauseGuard backend."""

import pytest
from fastapi.testclient import TestClient

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert isinstance(data["model_loaded"], bool)
    assert data["model_version"] in ("clauseguard-text-v1", "clauseguard-text-v2", "clauseguard-text-v3")

def test_model_info_endpoint():
    response = client.get("/model-info")
    assert response.status_code == 200
    data = response.json()
    expected_keys = {"model_version","algorithm","dataset_version","training_date","python_version","scikit_learn_version","expected_input","output_labels"}
    assert expected_keys.issubset(data.keys())
    assert data["model_version"] in ("clauseguard-text-v1", "clauseguard-text-v2", "clauseguard-text-v3")
    assert data["output_labels"] == ["not_dark_pattern","potential_dark_pattern"]


def test_ready_endpoint_reports_model_state():
    response = client.get("/ready")
    assert response.status_code in (200, 503)
    assert response.json()["model_loaded"] in (True, False)


def test_analyze_has_request_id_and_rejects_oversized_text():
    response = client.post("/analyze", json={"text": "x" * 20001})
    assert response.status_code == 422

    response = client.post("/analyze", json={"text": "Normal product information."})
    assert response.status_code == 200
    assert response.headers.get("x-request-id")
