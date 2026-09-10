# tests/test_validation.py
"""Input validation tests for ClauseGuard backend."""

import pytest
from fastapi.testclient import TestClient

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.main import app

client = TestClient(app)

def test_empty_text():
    response = client.post("/predict", json={"text": ""})
    assert response.status_code == 422

def test_whitespace_only():
    response = client.post("/predict", json={"text": "   \n\t"})
    assert response.status_code == 422

def test_excessively_long_text():
    long_text = "a" * 6000  # exceeds 5000 limit
    response = client.post("/predict", json={"text": long_text})
    assert response.status_code == 422

def test_missing_text_field():
    response = client.post("/predict", json={})
    assert response.status_code == 422
