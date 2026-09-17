"""Regression tests for separated observed/consequence/action answers."""
import sys

sys.path.insert(0, "tests")

from backend.services.ask_clauseguard import AskClauseGuardService, DeterministicQuestionProvider
from test_ask_active_finding_isolation import mixed_context


def test_separation_question_routes_to_canonical_composition():
    question = "Separate what ClauseGuard observed, what it thinks might happen, and what I should do next."
    context = mixed_context()
    provider = DeterministicQuestionProvider()
    assert provider.understand(question, context) == "ASSESSMENT_SEPARATION"
    response = AskClauseGuardService().answer("separation", question, context, prefer_local_llm=True)
    answer = response.answer.lower()
    assert response.model == "canonical-assessment-composition"
    assert response.grounded
    assert "observed:" in answer
    assert "might happen:" in answer
    assert "what to do:" in answer
    assert "social proof" in answer
    assert "other users" in answer
    assert "popularity" in answer or "consensus" in answer
    assert "evaluate" in answer
    assert "potential consumer-risk" in answer
    assert "confirm shaming" not in answer
    assert "scarcity" not in answer


def test_separation_missing_consequence_and_recommendation_are_local_unknowns():
    context = mixed_context().model_copy(update={
        "consequences": [],
        "recommended_action": None,
        "active_finding": mixed_context().active_finding.model_copy(update={
            "why_it_matters": None,
            "recommended_action": None,
        }),
    })
    response = AskClauseGuardService().answer(
        "separation-missing",
        "What did you observe, what could happen, and what should I do?",
        context,
    )
    answer = response.answer.lower()
    assert response.grounded
    assert "observed:" in answer and "might happen:" in answer and "what to do:" in answer
    assert "unknown" in answer
    assert "confirm shaming" not in answer


def test_separation_history_cannot_leak_unrelated_finding():
    response = AskClauseGuardService().answer(
        "separation-history",
        "Separate the evidence, possible consequence, and recommendation.",
        mixed_context(),
        conversation_history=["The decline option uses derogatory language."],
    )
    assert response.grounded
    assert "other users" in response.answer.lower()
    assert "decline option" not in response.answer.lower()
    assert response.evidence_ids == ["SP-001"]


def test_separation_switches_with_active_finding():
    response = AskClauseGuardService().answer(
        "separation-switch",
        "Separate what was observed, what might happen, and what I should do.",
        mixed_context("CONFIRM_SHAMING", ["CS-001"]),
    )
    assert response.grounded
    assert "confirm shaming" in response.answer.lower()
    assert "derogatory" in response.answer.lower()
    assert "other users" not in response.answer.lower()
    assert response.evidence_ids == ["CS-001"]
