from backend.schemas import EvidenceFusionResponse
from backend.services.consumer_risk_gate import ConsumerRiskGate


def test_gate_uses_canonical_risk_boundaries():
    gate = ConsumerRiskGate()
    expected = {
        2.99: "LOW",
        3.0: "MEDIUM",
        4.99: "MEDIUM",
        5.0: "HIGH",
        7.99: "HIGH",
        8.0: "CRITICAL",
        10.0: "CRITICAL",
    }
    for score, level in expected.items():
        result = gate.evaluate(EvidenceFusionResponse(risk_score=score, risk_detected=True))
        assert result["risk_level"] == level
        assert result["risk_score"] == score


def test_gate_suppresses_context_required_signal():
    result = ConsumerRiskGate().evaluate(
        EvidenceFusionResponse(risk_score=8.0, risk_detected=True, requires_context=True)
    )
    assert result["decision"] == "POTENTIAL"
    assert result["actionable"] is False
