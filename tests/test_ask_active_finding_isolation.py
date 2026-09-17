"""Regression tests for deterministic active-finding Ask isolation."""
from backend.services.ask_clauseguard import (
    AskClauseGuardService,
    GroundingValidator,
    LocalAnswerGenerator,
)
from backend.schemas.ask import AskClauseGuardContext


def mixed_context(active_pattern="SOCIAL_PROOF", active_ids=None):
    return AskClauseGuardContext(
        page_id="finding-page",
        journey_id="finding-journey",
        risk_level="POTENTIAL",
        risk_score=3.0,
        gate_decision="POTENTIAL",
        risk_detected=True,
        primary_pattern=active_pattern,
        active_finding={
            "pattern": active_pattern,
            "description": "The page emphasizes other users' activity.",
            "why_it_matters": "Popularity signals may create a false sense of consensus or urgency.",
            "recommended_action": "Evaluate the popularity claim independently before continuing.",
            "evidence_ids": active_ids or ["SP-001"],
        },
        evidence=[
            {"evidence_id": "SP-001", "source": "dom", "type": "social_proof", "pattern": "SOCIAL_PROOF", "description": "The page emphasizes other users' activity."},
            {"evidence_id": "SC-001", "source": "dom", "type": "scarcity", "pattern": "SCARCITY", "description": "Limited-stock banner indicates high demand."},
            {"evidence_id": "CS-001", "source": "behavior", "type": "confirm_shaming", "pattern": "CONFIRM_SHAMING", "description": "Decline option uses derogatory language."},
            {"evidence_id": "P-001", "source": "price", "type": "displayed_price", "description": "Base displayed price of INR 149.0", "value": 149, "currency": "INR"},
        ],
        consequences=["Popularity signals may create a false sense of consensus or urgency."],
        recommended_action="Evaluate the popularity claim independently before continuing.",
    )


def answer(context, question, history=None):
    return AskClauseGuardService().answer(
        "isolation-test",
        question,
        context,
        conversation_history=history or [],
        prefer_local_llm=False,
    )


def test_social_proof_evidence_excludes_other_findings():
    response = answer(mixed_context(), "give me the evidence you referred")
    assert response.grounded
    assert response.evidence_ids == ["SP-001"]
    assert "other users" in response.answer.lower()
    assert "decline option" not in response.answer.lower()
    assert "limited-stock" not in response.answer.lower()


def test_social_proof_next_action_and_loss_stay_on_active_finding():
    action = answer(mixed_context(), "what should i do next")
    loss = answer(mixed_context(), "is this loss for me")
    assert "decline" not in action.answer.lower()
    assert "limited" not in action.answer.lower()
    assert "no direct financial loss" in loss.answer.lower()
    assert "149" in loss.answer
    assert "hidden fee" not in loss.answer.lower()


def test_finding_switch_rebuilds_evidence_context():
    social = answer(mixed_context(), "give me the evidence")
    shaming = answer(mixed_context("CONFIRM_SHAMING", ["CS-001"]), "give me the evidence")
    assert social.evidence_ids == ["SP-001"]
    assert shaming.evidence_ids == ["CS-001"]
    assert "other users" in social.answer.lower()
    assert "derogatory" in shaming.answer.lower()


def test_history_cannot_authorize_excluded_evidence():
    response = answer(mixed_context(), "give me the evidence", ["The decline option uses derogatory language."])
    assert "decline option" not in response.answer.lower()
    assert response.evidence_ids == ["SP-001"]


def test_grounding_validator_rejects_excluded_finding_claim():
    context = mixed_context()
    validator = GroundingValidator()
    selected = [context.evidence[0]]
    excluded = [context.evidence[2]]
    assert not validator.validate("The decline option uses derogatory language.", context.model_copy(update={"evidence": selected}), selected, excluded)
    assert validator.validate("The page emphasizes other users' activity.", context.model_copy(update={"evidence": selected}), selected, excluded)


def test_local_generation_cannot_surface_excluded_pattern_terms():
    response = answer(mixed_context(), "give me the evidence you referred", history=[])
    assert response.grounded
    assert "scarcity" not in response.answer.lower()
    assert "confirm shaming" not in response.answer.lower()
    assert "other users" in response.answer.lower()
