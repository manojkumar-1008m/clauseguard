"""Focused production-hardening contracts."""

from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.explanation import ExplanationResponse
from backend.schemas.explanation_context import ExplanationContext
from backend.services.minilm_explanation import MiniLMExplanationLayer


client = TestClient(app)


class FakeEmbeddingBackend:
    def __init__(self):
        self.calls = 0

    def similarity(self, query, evidence):
        self.calls += 1
        return [0.5 for _ in evidence]


def _explanation():
    return ExplanationResponse(
        risk_status="risk_detected",
        title="Recurring charge",
        summary="A recurring charge was identified.",
        recommended_action="Review the renewal terms.",
        evidence_ids=["E001"],
        disclaimer="Consumer information, not legal advice.",
    )


def _context():
    return ExplanationContext(
        risk_result={"risk_score": 7.0, "risk_level": "HIGH", "gate_decision": "ACTIONABLE_RISK"},
        pattern="subscription_trap",
        evidence_ids=["E001"],
        evidence_descriptions=["Renewal at $19.99/month"],
        recommended_action="Review the renewal terms.",
    )


def test_minilm_can_be_disabled_without_changing_explanation(monkeypatch):
    monkeypatch.setenv("CLAUSEGUARD_MINILM_ENABLED", "0")
    backend = FakeEmbeddingBackend()
    result = MiniLMExplanationLayer(backend=backend).enhance(_explanation(), _context())
    assert backend.calls == 0
    assert result.title == "Recurring charge"
    assert result.metadata["semantic_layer"]["status"] == "disabled"


def test_model_info_reports_active_artifact_hash():
    response = client.get("/model-info")
    assert response.status_code == 200
    data = response.json()
    assert data["artifact"] == "clauseguard_model_v3.joblib"
    assert len(data["artifact_sha256"]) == 64


def test_vision_rejects_non_image_before_inference():
    response = client.post("/vision/predict", content=b"not an image", headers={"content-type": "text/plain"})
    assert response.status_code == 415
