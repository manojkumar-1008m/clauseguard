"""Regression coverage for intent-specific Ask retrieval."""
from backend.schemas.ask import AskClauseGuardContext, AskEvidence
from backend.services.ask_clauseguard import AskClauseGuardService, DeterministicQuestionProvider
from test_ask_active_finding_isolation import mixed_context


def ask(context, question, history=None):
    return AskClauseGuardService().answer(
        "intent-routing-test",
        question,
        context,
        conversation_history=history or [],
        prefer_local_llm=False,
    )


def test_question_provider_routes_required_domains():
    provider = DeterministicQuestionProvider()
    context = mixed_context()
    assert provider.understand("Why am I seeing this warning?", context) == "WHY_WARNING"
    assert provider.understand("What evidence did you find?", context) == "WHAT_EVIDENCE"
    assert provider.understand("What should I do next?", context) == "WHAT_SHOULD_I_DO"
    assert provider.understand("How much does it cost?", context) == "FINANCIAL_IMPACT"
    assert provider.understand("Could the price increase?", context) == "PRICE_CHANGE"
    assert provider.understand("Is there data sharing?", context) == "DATA_PRIVACY"
    assert provider.understand("Are there privacy issues?", context) == "DATA_PRIVACY"
    assert provider.understand("What dark patterns are there on this page?", context) == "ALL_FINDINGS"
    assert provider.understand("Could I lose money?", context) == "FINANCIAL_LOSS"
    assert provider.understand("What happens on renewal?", context) == "RENEWAL"


def test_social_proof_finding_questions_remain_isolated():
    for question in ("Why am I seeing this warning?", "What evidence did you find?", "What should I do next?"):
        response = ask(mixed_context(), question)
        assert response.evidence_ids == ["SP-001"]
        assert "decline option" not in response.answer.lower()
        assert "limited-stock" not in response.answer.lower()


def test_price_question_uses_canonical_price_not_social_proof():
    response = ask(mixed_context(), "How much does it cost?")
    assert response.intent == "FINANCIAL_IMPACT"
    assert response.evidence_ids == ["P-001"]
    assert "149" in response.answer
    assert "other users" not in response.answer.lower()


def test_dark_patterns_enumerates_current_canonical_patterns_only():
    response = ask(mixed_context(), "What dark patterns are there on this page?")
    assert response.intent == "ALL_FINDINGS"
    assert "social proof" in response.answer.lower()
    assert "confirm shaming" in response.answer.lower()
    assert "scarcity" in response.answer.lower()
    assert "potential findings" in response.answer.lower()


def test_financial_loss_does_not_use_social_proof_or_scarcity():
    response = ask(mixed_context(), "Could I lose money?", ["A limited-stock banner indicates high demand."])
    assert response.intent == "FINANCIAL_LOSS"
    assert response.evidence_ids == ["P-001"]
    assert "no direct financial loss" in response.answer.lower()
    assert "149" in response.answer
    assert "limited-stock" not in response.answer.lower()
    assert "other users" not in response.answer.lower()


def test_renewal_uses_renewal_evidence_only():
    context = mixed_context()
    context = context.model_copy(update={
        "evidence": context.evidence + [AskEvidence(
            evidence_id="R-001",
            source="price",
            type="renewal_price",
            description="The subscription renews at INR 499/month.",
            value=499,
            currency="INR",
        )]
    })
    response = ask(context, "What happens on renewal?")
    assert response.intent == "RENEWAL"
    assert response.evidence_ids == ["R-001"]
    assert "499" in response.answer
    assert "other users" not in response.answer.lower()


def test_price_change_without_evidence_does_not_invent_increase():
    response = ask(mixed_context(), "Is there a chance of increasing in price?")
    assert response.intent == "PRICE_CHANGE"
    assert response.evidence_ids == []
    assert "does not contain verified evidence" in response.answer.lower()
    assert "price increase is verified" not in response.answer.lower()


def test_price_change_uses_only_price_change_evidence():
    context = mixed_context()
    context = context.model_copy(update={
        "evidence": context.evidence + [AskEvidence(
            evidence_id="PC-001",
            source="price",
            type="price_change",
            description="Price increased from INR 149 to INR 199.",
            value=199,
            currency="INR",
        )]
    })
    response = ask(context, "Could the price increase?")
    assert response.intent == "PRICE_CHANGE"
    assert response.evidence_ids == ["PC-001"]
    assert "199" in response.answer
    assert "other users" not in response.answer.lower()


def test_privacy_without_evidence_is_explicitly_not_assessed():
    response = ask(mixed_context(), "Is there data sharing?", ["The popularity warning was justified."])
    assert response.intent == "DATA_PRIVACY"
    assert response.evidence_ids == []
    assert "does not contain verified evidence" in response.answer.lower()
    assert "social proof" not in response.answer.lower()
    assert "limited-stock" not in response.answer.lower()


def test_privacy_uses_only_privacy_evidence():
    context = mixed_context()
    context = context.model_copy(update={
        "evidence": context.evidence + [AskEvidence(
            evidence_id="PR-001",
            source="text",
            type="data_sharing",
            description="The privacy notice says data may be shared with third-party analytics providers.",
        )]
    })
    response = ask(context, "Are there privacy issues?")
    assert response.intent == "DATA_PRIVACY"
    assert response.evidence_ids == ["PR-001"]
    assert "third-party analytics" in response.answer.lower()
    assert "other users" not in response.answer.lower()


def test_history_cannot_change_routed_intent_or_evidence():
    context = mixed_context()
    history = [
        "Why was this flagged?",
        "The page emphasizes other users' activity.",
    ]
    response = ask(context, "Is there data sharing?", history)
    assert response.intent == "DATA_PRIVACY"
    assert response.evidence_ids == []
    assert "other users" not in response.answer.lower()


def test_active_finding_switch_still_routes_finding_questions():
    response = ask(mixed_context("CONFIRM_SHAMING", ["CS-001"]), "What evidence did you find?")
    assert response.intent == "WHAT_EVIDENCE"
    assert response.evidence_ids == ["CS-001"]
    assert "derogatory" in response.answer.lower()


def test_structured_active_finding_facts_bypass_llm_and_history():
    context = mixed_context()
    questions = {
        "Which finding is currently active?": ("ACTIVE_FINDING", "social proof"),
        "What pattern was detected?": ("DETECTED_PATTERN", "social proof"),
        "How many potential findings are there?": ("FINDING_COUNT", "3"),
        "What is the severity?": ("FINDING_SEVERITY", "Potential"),
        "Are these findings confirmed or potential?": ("FINDING_STATUS", "Potential"),
        "What evidence belongs to this finding?": ("FINDING_EVIDENCE", "other users"),
        "Is the finding supported by multiple evidence sources?": ("FINDING_SOURCES", "one evidence source"),
        "Show me all detected findings.": ("ALL_FINDINGS", "Social Proof"),
    }
    for question, (intent, expected) in questions.items():
        response = ask(context, question, ["The decline option uses derogatory language."])
        assert response.intent == intent
        assert response.model == "canonical-structured-facts"
        assert expected.lower() in response.answer.lower()
        assert "decline option" not in response.answer.lower()


def test_structured_source_support_uses_canonical_sources():
    context = mixed_context()
    context = context.model_copy(update={
        "evidence": [
            context.evidence[0].model_copy(update={"source": "dom"}),
            context.evidence[1], context.evidence[2], context.evidence[3],
            context.evidence[0].model_copy(update={"evidence_id": "SP-002", "source": "text"}),
        ]
    })
    response = ask(context, "Is the finding supported by multiple evidence sources?")
    assert response.intent == "FINDING_SOURCES"
    assert "multiple evidence sources" in response.answer.lower()
    assert response.evidence_ids == ["SP-001", "SP-002"]


def test_final_scope_matrix_never_uses_unrelated_finding_evidence():
    context = mixed_context()
    cases = {
        "Could the price increase later?": ("PRICE_CHANGE", "does not contain verified evidence"),
        "Are there any additional charges?": ("ADDITIONAL_CHARGE", "no verified additional charge"),
        "Did you find any confirm shaming?": ("PATTERN_EXISTS", "confirm shaming"),
        "Did you find any scarcity?": ("PATTERN_EXISTS", "scarcity"),
        "Did you find any subscription trap?": ("PATTERN_EXISTS", "no verified subscription trap"),
        "Did you find any fake urgency?": ("PATTERN_EXISTS", "no verified fake urgency"),
        "Is there any data privacy issue?": ("DATA_PRIVACY", "does not contain verified evidence"),
    }
    for question, (intent, expected) in cases.items():
        response = ask(context, question, ["The decline option uses derogatory language."])
        assert response.intent == intent
        assert expected in response.answer.lower()
        assert "decline option" not in response.answer.lower()
