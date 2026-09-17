"""Regression tests for deterministic observation-only Ask responses."""
import sys

sys.path.insert(0, "tests")

from backend.services.ask_clauseguard import AskClauseGuardService, DeterministicQuestionProvider
from test_ask_active_finding_isolation import mixed_context


def test_observation_phrases_route_to_deterministic_fact_mode():
    provider = DeterministicQuestionProvider()
    context = mixed_context()
    questions = [
        "What did ClauseGuard observe?",
        "What did you observe?",
        "What exactly did you see?",
        "What was observed on this page?",
        "Show me what was observed.",
    ]
    for question in questions:
        assert provider.understand(question, context) == "OBSERVATION_ONLY"


def test_observation_preserves_canonical_active_evidence_only():
    response = AskClauseGuardService().answer(
        "observation-social",
        "What did ClauseGuard observe?",
        mixed_context(),
        conversation_history=["The decline option uses derogatory language."],
        prefer_local_llm=True,
    )
    answer = response.answer.lower()
    assert response.response_mode == "DETERMINISTIC_FACT"
    assert response.model == "canonical-observation-facts"
    assert response.evidence_ids == ["SP-001"]
    assert "other users" in answer
    assert "assessment is supported" not in answer
    assert "might" not in answer
    assert "should" not in answer
    assert "decline option" not in answer
    assert "confirm shaming" not in answer
    assert "scarcity" not in answer
    assert "legal" not in answer


def test_observation_preserves_confirm_shaming_active_finding():
    response = AskClauseGuardService().answer(
        "observation-shaming",
        "What exactly did you see?",
        mixed_context("CONFIRM_SHAMING", ["CS-001"]),
    )
    assert response.response_mode == "DETERMINISTIC_FACT"
    assert "derogatory language" in response.answer.lower()
    assert "other users" not in response.answer.lower()


def test_observation_supports_multiple_canonical_items():
    context = mixed_context()
    context = context.model_copy(update={
        "evidence": context.evidence + [
            context.evidence[0].model_copy(update={"evidence_id": "SP-002", "description": "Trending Now label appears near the product."})
        ]
    })
    response = AskClauseGuardService().answer("observation-multiple", "Show me what was observed.", context)
    assert response.response_mode == "DETERMINISTIC_FACT"
    assert "- " in response.answer
    assert "other users" in response.answer.lower()
    assert "trending now" in response.answer.lower()
