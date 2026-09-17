"""Regression tests for complete grounded reasoning answers."""
import sys

sys.path.insert(0, "tests")

from backend.services.ask_clauseguard import AskClauseGuardService
from test_ask_active_finding_isolation import mixed_context


def answer(question, prefer_local_llm=False):
    return AskClauseGuardService().answer(
        "reasoning-quality",
        question,
        mixed_context(),
        prefer_local_llm=prefer_local_llm,
    )


def test_evidence_answer_is_evidence_only():
    response = answer("What evidence did you find?")
    answer_text = response.answer.lower()
    assert response.intent == "WHAT_EVIDENCE"
    assert response.response_mode == "DETERMINISTIC_FACT"
    assert "other users" in answer_text
    assert "matter" not in answer_text
    assert "because" not in answer_text
    assert "consequence" not in answer_text
    assert "before continuing" not in answer_text


def test_warning_answer_contains_evidence_and_consequence():
    response = answer("Why am I seeing this warning?")
    assert "social proof" in response.answer.lower()
    assert "other users" in response.answer.lower()
    assert "matter because" in response.answer.lower()


def test_pattern_explanation_preserves_potential_status():
    response = answer("What makes this a potential dark pattern?")
    assert "potential social proof" in response.answer.lower()
    assert "not a definitive legal finding" in response.answer.lower()
    assert "other users" in response.answer.lower()


def test_consequence_and_recommendation_are_mode_scoped():
    consequence = answer("Why could this influence my decision?")
    recommendation = answer("What should I do next?")
    consequence_text = consequence.answer.lower()
    recommendation_text = recommendation.answer.lower()
    assert consequence.intent == "CONSEQUENCE"
    assert consequence.response_mode == "DETERMINISTIC_FACT"
    assert "potential consequence" in consequence_text
    assert "consensus" in consequence_text or "urgency" in consequence_text
    assert "other users" not in consequence_text
    assert "before continuing" not in consequence_text
    assert recommendation.intent == "WHAT_SHOULD_I_DO"
    assert recommendation.response_mode == "DETERMINISTIC_FACT"
    assert "evaluate the popularity" in recommendation_text
    assert "other users" not in recommendation_text
    assert "consequence" not in recommendation_text


def test_local_model_path_falls_back_to_complete_grounded_answer():
    response = answer("Why am I seeing this warning?", prefer_local_llm=True)
    assert response.grounded
    assert "social proof" in response.answer.lower()
    assert "other users" in response.answer.lower()
    assert "confirm shaming" not in response.answer.lower()
    assert "scarcity" not in response.answer.lower()
    assert response.response_mode in {"GROUNDED_LLM", "DETERMINISTIC_FALLBACK"}
