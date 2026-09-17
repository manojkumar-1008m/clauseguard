import sys
sys.path.append('.')
from backend.services.ask_clauseguard import AskClauseGuardService, AskClauseGuardContext, AskEvidence

service = AskClauseGuardService()
print("Model loaded:", service.answer_provider._loaded)
print("SHA256:", service.answer_provider.sha256)

ctx = AskClauseGuardContext(
    request_id="demo-1",
    route="subscription",
    decision_context="checkout decision",
    risk_level="CRITICAL",
    risk_score=9.2,
    gate_decision="ACTIONABLE_RISK",
    actionable=True,
    risk_detected=True,
    primary_pattern="SUBSCRIPTION_TRAP",
    detected_patterns=["SUBSCRIPTION_TRAP"],
    evidence=[
        AskEvidence(
            evidence_id="ev-sub-1",
            source="price",
            type="subscription_renewal",
            description="7-day free trial is followed by recurring monthly charge of ₹999.",
            strength="HIGH",
            value=999.0,
            currency="₹"
        )
    ],
    consequences=["Consumer may incur recurring charges."],
    financial_exposure=999.0,
    recommended_action="Review the renewal amount and cancel before 7 days if you do not wish to continue."
)

res = service.answer_provider.generate(
    question="How much will I be charged after the trial?",
    context=ctx,
    intent="HOW_MUCH",
    evidence=list(ctx.evidence),
    force_llm=True
)
print("Answer:", res)
