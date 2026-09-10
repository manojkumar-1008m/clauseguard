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
