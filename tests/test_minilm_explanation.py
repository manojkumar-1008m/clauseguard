from backend.schemas.explanation import ExplanationResponse
from backend.schemas.explanation_context import ExplanationContext
from backend.services.minilm_explanation import MiniLMExplanationLayer


class FakeEmbeddingBackend:
    def __init__(self):
        self.calls = 0

    def similarity(self, query, evidence):
        self.calls += 1
        assert "subscription_trap" in query
        return [0.1, 0.9]


def _explanation():
    return ExplanationResponse(
        risk_status="risk_detected",
        title="Recurring charge",
        summary="A recurring charge was identified.",
        recommended_action="Review the renewal terms.",
        evidence_ids=["E001", "E002"],
        disclaimer="This is a consumer-risk signal, not a legal determination.",
        metadata={"risk_score": 7.0, "risk_level": "HIGH", "gate_decision": "ACTIONABLE_RISK"},
    )


def _context(**overrides):
    values = {
        "risk_result": {
            "risk_score": 7.0,
            "risk_level": "HIGH",
            "gate_decision": "ACTIONABLE_RISK",
        },
        "pattern": "subscription_trap",
        "evidence_ids": ["E001", "E002"],
        "evidence_descriptions": ["Free trial", "Renewal at $19.99/month"],
        "recommended_action": "Review the renewal terms.",
    }
    values.update(overrides)
    return ExplanationContext(**values)


def test_minilm_ranks_verified_evidence_without_generating_facts():
    backend = FakeEmbeddingBackend()
    original = _explanation()
    result = MiniLMExplanationLayer(backend=backend).enhance(original, _context())

    assert backend.calls == 1
    assert result.title == original.title
    assert result.summary == original.summary
    assert result.metadata["semantic_layer"]["status"] == "ok"
    assert result.metadata["semantic_layer"]["ranked_evidence_ids"] == ["E002", "E001"]
    assert set(result.metadata["semantic_layer"]["ranked_evidence_ids"]) <= {"E001", "E002"}
    assert result.metadata["risk_score"] == 7.0
    assert result.metadata["risk_level"] == "HIGH"
    assert result.metadata["gate_decision"] == "ACTIONABLE_RISK"


def test_minilm_failure_uses_deterministic_fallback(monkeypatch):
    layer = MiniLMExplanationLayer()
    monkeypatch.setattr(layer, "_get_backend", lambda: (_ for _ in ()).throw(RuntimeError("weights missing")))

    result = layer.enhance(_explanation(), _context())

    semantic = result.metadata["semantic_layer"]
    assert semantic["status"] == "fallback"
    assert semantic["reason"] == "MiniLM unavailable"
    assert result.summary == "A recurring charge was identified."
    assert result.disclaimer == "This is a consumer-risk signal, not a legal determination."


def test_insufficient_context_is_preserved():
    original = _explanation()
    result = MiniLMExplanationLayer(backend=FakeEmbeddingBackend()).enhance(
        original, _context(requires_context=True)
    )

    assert result.requires_context is False
    assert result.summary == original.summary
    assert result.metadata["semantic_layer"]["status"] == "insufficient_context"
    assert result.metadata["semantic_layer"]["model_used"] is False


def test_no_context_does_not_invent_evidence_or_legal_claims():
    original = _explanation()
    result = MiniLMExplanationLayer(backend=FakeEmbeddingBackend()).enhance(original, None)

    assert result.evidence_ids == original.evidence_ids
    assert result.evidence_summary == original.evidence_summary
    assert result.disclaimer == original.disclaimer
    assert result.metadata["semantic_layer"]["status"] == "insufficient_context"


def test_canonical_context_and_regulatory_fields_are_unchanged():
    context = _context(regulatory_assessment={"decision": "review", "basis": "verified upstream assessment"})
    before = context.model_dump()

    MiniLMExplanationLayer(backend=FakeEmbeddingBackend()).enhance(_explanation(), context)

    assert context.model_dump() == before
    assert context.risk_result["risk_score"] == 7.0
    assert context.risk_result["risk_level"] == "HIGH"
    assert context.risk_result["gate_decision"] == "ACTIONABLE_RISK"
    assert context.regulatory_assessment["decision"] == "review"