"""Regression tests for multipart reasoning answer completeness."""
import sys

sys.path.insert(0, "tests")

from backend.services.ask_clauseguard import AskClauseGuardService
from test_ask_active_finding_isolation import mixed_context


QUESTIONS = [
    "Explain the current assessment in simple language, including the evidence, potential consequence, and what I should do.",
    "Based on everything ClauseGuard has observed, what exactly makes you think this page could influence my decision, and which pieces of evidence support that conclusion?",
    "Explain the warning, evidence, consequence, and recommended action.",
    "What did you observe, why does it matter, and what should I do?",
]


def test_multipart_questions_include_requested_components():
    service = AskClauseGuardService()
    for index, question in enumerate(QUESTIONS):
        response = service.answer("completeness", question, mixed_context(), prefer_local_llm=False)
        answer = response.answer.lower()
        assert response.grounded
        assert "other users" in answer
        assert "confirm shaming" not in answer
        assert "scarcity" not in answer
        assert response.response_mode == "DETERMINISTIC_FACT"
        if index < 3:
            assert response.intent == "WHAT_EVIDENCE"
            assert "matter" not in answer
            assert "consequence" not in answer
            assert "before continuing" not in answer
        else:
            assert response.intent == "ASSESSMENT_SEPARATION"
            assert "social proof" in answer
            assert "potential" in answer
            assert "matter" in answer or "consequence" in answer
            assert "evaluate" in answer or "before continuing" in answer


def test_multipart_local_model_path_uses_complete_grounded_fallback():
    response = AskClauseGuardService().answer(
        "completeness-local",
        QUESTIONS[0],
        mixed_context(),
        prefer_local_llm=True,
    )
    answer = response.answer.lower()
    assert response.grounded
    assert "other users" in answer
    assert response.intent == "WHAT_EVIDENCE"
    assert response.response_mode == "DETERMINISTIC_FACT"
    assert "matter" not in answer
    assert "consequence" not in answer
    assert "before continuing" not in answer
    assert "confirm shaming" not in answer
