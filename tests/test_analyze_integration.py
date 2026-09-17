from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_analyze_exposes_fused_risk_and_gate_contract():
    response = client.post(
        "/analyze",
        json={"text": "Free trial renews automatically at $19.99/month."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert 0.0 <= payload["risk_score"] <= 10.0
    assert payload["model_version"] == "clauseguard-text-v3"
    assert payload["evidence_count"] >= 1
    assert payload["consumer_gate"]["decision"] in {"CLEAR", "POTENTIAL", "ACTIONABLE_RISK", "SUPPRESSED"}
    assert payload["consumer_gate"]["risk_score"] == payload["risk_score"]
    assert payload["explanation"]["source"] == "consumer_explanation"
    assert payload["explanation_context"]["risk_result"]["risk_score"] == payload["risk_score"]
    breakdown = payload["score_breakdown"]
    assert breakdown["final_score"] == payload["risk_score"]
    assert "dom_cap" in breakdown
    assert "behavior_cap" in breakdown
    assert "corroboration_bonus" in breakdown
    assert "conflict_penalty" in breakdown
    assert "ceiling_applied" in breakdown


def test_analyze_routes_vision_observation_through_fusion_and_explanation():
    response = client.post(
        "/analyze",
        json={
            "text": "Standard product information.",
            "image_evidence": [
                {
                    "type": "countdown_timer",
                    "detected": True,
                    "strength": "moderate",
                    "description": "Observed countdown timer in the purchase interface.",
                    "decision_context": "purchase",
                    "model_confidence": 0.91,
                    "provenance": "vision:test",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert any(item["source"] == "image" for item in payload["evidence"])
    assert payload["explanation"]["source"] == "consumer_explanation"
    assert payload["risk_score"] <= 10.0


def test_analyze_score_breakdown_is_canonical_and_sources_are_backend_supplied():
    response = client.post(
        "/analyze",
        json={
            "text": "Cancel subscription requires contacting support.",
            "dom_evidence": [{
                "type": "cancel_action_disabled",
                "detected": True,
                "strength": "strong",
                "decision_context": "cancellation",
            }],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    breakdown = payload["score_breakdown"]
    assert breakdown["final_score"] == payload["risk_score"]
    assert breakdown["dom_contribution"] <= breakdown["dom_cap"]
    assert breakdown["evidence_sources"] == sorted(breakdown["evidence_sources"])


def test_popup_score_breakdown_contract_is_display_only_and_optional():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    popup = (root / "extension" / "popup.js").read_text(encoding="utf-8")
    html = (root / "extension" / "popup.html").read_text(encoding="utf-8")
    assert "score_breakdown" in popup
    assert "final_score" in popup
    assert "scoreBreakdownSection" in html
    assert "scoreBreakdownToggle" in html
    assert "headerRiskBadge" in html
    assert "headerRiskScore" in html
    assert "headerRiskLevel" in html
    assert "risk_score" not in popup.split("renderScoreBreakdown", 1)[1].split("function", 1)[0]
    assert "pre_ceiling_score" in popup
    assert "dom_cap" in popup
    assert "behavior_cap" in popup
    assert "ceiling_applied" in popup
    assert "finalScore" in popup
    assert "data.risk_level" in popup
    assert "askQuestionAndRender" in popup
    assert "riskScore *" not in popup
    assert "risk_score *" not in popup
    assert "score_breakdown.*" not in popup


def test_header_score_uses_backend_final_score_and_gate_level():
    response = client.post("/analyze", json={"text": "Cancel subscription requires contacting support."})
    assert response.status_code == 200
    payload = response.json()
    assert payload["score_breakdown"]["final_score"] == payload["risk_score"]
    assert payload["risk_level"] == payload["consumer_gate"]["risk_level"]
