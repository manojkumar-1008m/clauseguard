"""tests/test_phase8_7_explanation.py
Comprehensive test suite for ClauseGuard Phase 8.7: Consumer Explanation & Action Engine.

Validates:
1. Free trial -> renewal explanation
2. Paid trial -> renewal explanation
3. Additional fee explanation
4. Late disclosure explanation
5. Price increase explanation
6. Price decrease explanation
7. No meaningful change
8. Urgency explanation
9. Scarcity explanation
10. Social proof explanation
11. Misdirection explanation
12. Obstruction explanation
13. Sneaking explanation
14. Forced action explanation
15. Context-required case
16. Benign / no-risk case
17. Multi-signal case
18. Duplicate evidence handling
19. Contradiction handling
20. Missing financial data handling
21. Evidence IDs preserved for traceability
22. No legal conclusions / objective tone
23. Practical action generation
24. Multiple findings and prioritization
25. Full API endpoint test (/explain)
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.evidence import (
    ConsumerConsequence,
    EvidenceConflict,
    EvidenceFusionRequest,
    EvidenceFusionResponse,
    EvidenceGroup,
    EvidenceItem,
    FinancialImpact,
)
from backend.schemas.explanation import (
    ConsumerExplanationFinding,
    ExplanationRequest,
    ExplanationResponse,
)
from backend.services.explanation_engine import ConsumerExplanationEngine


@pytest.fixture
def engine():
    return ConsumerExplanationEngine()


@pytest.fixture
def client():
    return TestClient(app)


# --------------------------------------------------------------------------
# 1. Free trial -> renewal
# --------------------------------------------------------------------------
def test_free_trial_renewal_explanation(engine):
    resp = engine.explain(ExplanationRequest(text="7-day free trial, then ₹999/month."))
    assert resp.risk_status in ("financial_notice", "risk_detected")
    assert "Free trial" in resp.title
    assert "₹999" in resp.summary or "999" in resp.summary
    assert "cancellation" in resp.recommended_action.lower() or "renewal" in resp.recommended_action.lower()
    assert len(resp.evidence_ids) > 0
    assert resp.findings[0].type == "subscription_risk"


# --------------------------------------------------------------------------
# 2. Paid trial -> renewal
# --------------------------------------------------------------------------
def test_paid_trial_renewal_explanation(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="MEDIUM",
        risk_score=3.0,
        financial_signal=True,
        financial_impact=FinancialImpact(
            trial_price=99.0,
            trial_duration_days=7,
            renewal_price=999.0,
            billing_period="month",
            currency="INR",
        ),
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="price",
                type="paid_trial",
                pattern="subscription_trap",
                description="7-day trial for ₹99",
                value=99.0,
                currency="INR",
            ),
            EvidenceItem(
                evidence_id="E002",
                source="price",
                type="renewal_price",
                pattern="subscription_trap",
                description="Renewal at ₹999/month",
                value=999.0,
                currency="INR",
            ),
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert "Paid trial" in resp.title
    assert "₹99" in resp.summary
    assert "₹999" in resp.summary
    assert resp.findings[0].type == "subscription_risk"
    assert "cancellation" in resp.recommended_action.lower() or "renewal" in resp.recommended_action.lower()


# --------------------------------------------------------------------------
# 3. Additional fee
# --------------------------------------------------------------------------
def test_additional_fee_explanation(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="MEDIUM",
        risk_score=3.0,
        financial_signal=True,
        financial_impact=FinancialImpact(
            initial_price=499.0,
            additional_cost=79.0,
            known_total=578.0,
            currency="INR",
        ),
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="price",
                type="additional_fee",
                description="Processing fee ₹79",
                value=79.0,
                currency="INR",
                metadata={"late_disclosed": False},
            )
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert "Additional fee" in resp.title
    assert "₹79" in resp.summary
    assert "578" in resp.financial_consequence or "578" in resp.consumer_consequence
    assert "review" in resp.recommended_action.lower() or "breakdown" in resp.recommended_action.lower()


# --------------------------------------------------------------------------
# 4. Late disclosure
# --------------------------------------------------------------------------
def test_late_disclosure_explanation(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="MEDIUM",
        risk_score=3.5,
        financial_signal=True,
        financial_impact=FinancialImpact(
            initial_price=499.0,
            additional_cost=79.0,
            known_total=578.0,
            currency="INR",
        ),
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="price",
                type="late_disclosure",
                description="Processing fee ₹79 disclosed after base price",
                value=79.0,
                currency="INR",
                metadata={"late_disclosed": True},
            )
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert "later" in resp.title.lower() or "late" in resp.title.lower()
    assert "disclosed later" in resp.title.lower() or "later" in resp.summary.lower()
    assert "illegal" not in resp.summary.lower()
    assert "violating" not in resp.summary.lower()
    assert "check the final price" in resp.recommended_action.lower()


# --------------------------------------------------------------------------
# 5. Price increase
# --------------------------------------------------------------------------
def test_price_increase_explanation(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="LOW",
        risk_score=1.0,
        financial_signal=True,
        financial_impact=FinancialImpact(
            previous_price=999.0,
            current_price=1299.0,
            price_change=300.0,
            price_change_percentage=30.03,
            currency="INR",
        ),
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="price",
                type="price_increase",
                description="Price increased from ₹999 to ₹1299",
                value=300.0,
                currency="INR",
            )
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert "Price changed" in resp.title
    assert "increased" in resp.summary.lower()
    assert "300" in resp.consumer_consequence
    assert "30.03%" in resp.consumer_consequence
    assert "verify" in resp.recommended_action.lower()
    assert "deceptive" not in resp.summary.lower()


# --------------------------------------------------------------------------
# 6. Price decrease
# --------------------------------------------------------------------------
def test_price_decrease_explanation(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="LOW",
        risk_score=0.5,
        financial_signal=True,
        financial_impact=FinancialImpact(
            previous_price=999.0,
            current_price=799.0,
            price_change=-200.0,
            price_change_percentage=-20.02,
            currency="INR",
        ),
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="price",
                type="price_decrease",
                description="Price dropped from ₹999 to ₹799",
                value=-200.0,
                currency="INR",
            )
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert "Price decreased" in resp.title
    assert "decreased" in resp.summary.lower()
    assert "save" in resp.consumer_consequence.lower() or "save" in resp.financial_consequence.lower()


# --------------------------------------------------------------------------
# 7. No meaningful change
# --------------------------------------------------------------------------
def test_no_meaningful_change(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="LOW",
        risk_score=0.0,
        financial_signal=False,
        evidence=[],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert resp.risk_status == "no_strong_signal"
    assert "No strong consumer-risk signal detected" in resp.title
    assert resp.disclaimer is None


# --------------------------------------------------------------------------
# 8. Urgency with DOM countdown timer
# --------------------------------------------------------------------------
def test_urgency_with_dom_countdown(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="HIGH",
        risk_score=6.0,
        is_corroborated=True,
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="text",
                type="urgency",
                pattern="urgency",
                description="Text contains hurry language",
            ),
            EvidenceItem(
                evidence_id="E002",
                source="dom",
                type="countdown_timer",
                pattern="urgency",
                description="Live countdown timer active",
            ),
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert "Urgency" in resp.title
    assert "countdown element" in resp.summary.lower()
    assert "countdown" in resp.recommended_action.lower()
    assert "fake" not in resp.summary.lower()


# --------------------------------------------------------------------------
# 9. Scarcity
# --------------------------------------------------------------------------
def test_scarcity_explanation(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="MEDIUM",
        risk_score=3.0,
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="text",
                type="scarcity",
                pattern="scarcity",
                description="Only 2 items remaining in stock",
            )
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert "Scarcity" in resp.title
    assert "stock" in resp.summary.lower() or "quantity" in resp.summary.lower()
    assert "verify stock" in resp.recommended_action.lower()


# --------------------------------------------------------------------------
# 10. Social Proof
# --------------------------------------------------------------------------
def test_social_proof_explanation(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="LOW",
        risk_score=2.0,
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="text",
                type="social_proof",
                pattern="social_proof",
                description="1,249 people bought this today",
            )
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert "Social-proof" in resp.title
    assert "other users" in resp.summary.lower() or "popularity" in resp.summary.lower()
    assert "fake" not in resp.summary.lower()
    assert "evaluate the product independently" in resp.recommended_action.lower()


# --------------------------------------------------------------------------
# 11. Misdirection
# --------------------------------------------------------------------------
def test_misdirection_explanation(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="MEDIUM",
        risk_score=3.0,
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="ui",
                type="misdirection",
                pattern="misdirection",
                description="High-tier option styled brightly, standard option grayed out",
            )
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert "Misdirection" in resp.title
    assert "draws attention" in resp.summary.lower()
    assert "review all available options" in resp.recommended_action.lower()


# --------------------------------------------------------------------------
# 12. Obstruction
# --------------------------------------------------------------------------
def test_obstruction_explanation(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="MEDIUM",
        risk_score=3.0,
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="behavior",
                type="obstruction",
                pattern="obstruction",
                description="Cancellation requires phone call",
            )
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert "Friction" in resp.title or "Obstruction" in resp.title
    assert "more steps" in resp.summary.lower()
    assert "cancellation controls" in resp.recommended_action.lower()


# --------------------------------------------------------------------------
# 13. Sneaking
# --------------------------------------------------------------------------
def test_sneaking_explanation(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="MEDIUM",
        risk_score=3.0,
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="dom",
                type="sneaking",
                pattern="sneaking",
                description="Pre-checked warranty checkbox in cart",
            )
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert "Preselected" in resp.title
    assert "preselected" in resp.summary.lower()
    assert "review all selected items" in resp.recommended_action.lower()


# --------------------------------------------------------------------------
# 14. Forced Action
# --------------------------------------------------------------------------
def test_forced_action_explanation(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="MEDIUM",
        risk_score=3.0,
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="ui",
                type="forced_action",
                pattern="forced_action",
                description="Must create account to view shipping price",
            )
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert "Required step" in resp.title
    assert "requires an additional action" in resp.summary.lower()
    assert "alternative path" in resp.recommended_action.lower()


# --------------------------------------------------------------------------
# 15. Context-Required Case
# --------------------------------------------------------------------------
def test_context_required_explanation(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="LOW",
        risk_score=1.0,
        requires_context=True,
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="text",
                type="urgency",
                pattern="urgency",
                description="Offer valid today only",
            )
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert resp.requires_context is True
    assert "context" in resp.summary.lower() or "context" in resp.title.lower()
    assert "review the surrounding page" in resp.recommended_action.lower()


# --------------------------------------------------------------------------
# 16. Benign Case
# --------------------------------------------------------------------------
def test_benign_policy_text(engine):
    resp = engine.explain(ExplanationRequest(text="30-day return policy."))
    assert resp.risk_status == "no_strong_signal"
    assert "No strong consumer-risk" in resp.title
    assert resp.disclaimer is None


# --------------------------------------------------------------------------
# 17. Multi-signal case (Corroborated text + price)
# --------------------------------------------------------------------------
def test_multi_signal_corroborated_explanation(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="HIGH",
        risk_score=7.0,
        is_corroborated=True,
        potential_pattern="subscription_trap",
        dark_pattern="subscription_trap",
        financial_signal=True,
        financial_impact=FinancialImpact(
            trial_price=0.0,
            trial_duration_days=7,
            renewal_price=999.0,
            billing_period="month",
            currency="INR",
        ),
        evidence_groups=[
            EvidenceGroup(
                group_id="G001",
                pattern="subscription_risk",
                evidence_ids=["E001", "E002", "E003"],
                sources=["text", "price"],
                corroborated=True,
            )
        ],
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="text",
                type="subscription_trap",
                pattern="subscription_trap",
                description="Automatic renewal language detected",
            ),
            EvidenceItem(
                evidence_id="E002",
                source="price",
                type="free_trial",
                pattern="subscription_trap",
                description="7-day free trial",
                value=0.0,
                currency="INR",
            ),
            EvidenceItem(
                evidence_id="E003",
                source="price",
                type="renewal_price",
                pattern="subscription_trap",
                description="Recurring renewal price ₹999/month",
                value=999.0,
                currency="INR",
            ),
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert "Free trial leads to recurring subscription" in resp.title
    assert "₹999/month" in resp.summary
    assert "7-day" in resp.summary
    assert "recurring" in resp.consumer_consequence.lower()
    assert set(resp.evidence_ids) >= {"E001", "E002", "E003"}


# --------------------------------------------------------------------------
# 18. Duplicate evidence handling
# --------------------------------------------------------------------------
def test_duplicate_evidence_handling(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="HIGH",
        risk_score=6.0,
        financial_impact=FinancialImpact(
            renewal_price=999.0,
            currency="INR",
        ),
        evidence=[
            EvidenceItem(evidence_id="E001", source="price", type="renewal_price", description="₹999/month renewal", value=999.0, currency="INR"),
            EvidenceItem(evidence_id="E002", source="price", type="displayed_price", description="₹999/month renewal", value=999.0, currency="INR"),
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    # Evidence summary bullets should not be duplicated identically
    assert len(resp.evidence_summary) == len(set(resp.evidence_summary))


# --------------------------------------------------------------------------
# 19. Contradiction handling
# --------------------------------------------------------------------------
def test_contradiction_handling(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="MEDIUM",
        risk_score=3.5,
        conflicts=[
            EvidenceConflict(
                type="evidence_conflict",
                sources=["text", "price"],
                description="Text states 'free trial' but price analyzer found ₹99 trial fee",
                resolution="preserve_both",
            )
        ],
        evidence=[
            EvidenceItem(evidence_id="E001", source="text", type="free_trial", description="Free trial claim"),
            EvidenceItem(evidence_id="E002", source="price", type="paid_trial", description="Trial price ₹99", value=99.0, currency="INR"),
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    conflict_findings = [f for f in resp.findings if f.type == "contradiction"]
    assert len(conflict_findings) == 1
    assert "Conflicting terms" in conflict_findings[0].title
    assert "clarify" in conflict_findings[0].recommended_action.lower()


# --------------------------------------------------------------------------
# 20. Missing financial data handling
# --------------------------------------------------------------------------
def test_missing_financial_data(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="LOW",
        risk_score=1.5,
        financial_impact=None,
        evidence=[
            EvidenceItem(
                evidence_id="E001",
                source="text",
                type="urgency",
                pattern="urgency",
                description="Limited time offer",
            )
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert resp.financial_consequence is None
    assert resp.title is not None
    assert resp.summary is not None


# --------------------------------------------------------------------------
# 21. Evidence IDs preserved for traceability
# --------------------------------------------------------------------------
def test_evidence_ids_preserved(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="MEDIUM",
        risk_score=3.0,
        evidence=[
            EvidenceItem(evidence_id="E001", source="price", type="additional_fee", description="Fee ₹79", value=79.0),
            EvidenceItem(evidence_id="E002", source="text", type="drip_pricing", description="Additional fee statement"),
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert "E001" in resp.evidence_ids
    assert "E002" in resp.evidence_ids


# --------------------------------------------------------------------------
# 22. No legal conclusions / objective tone
# --------------------------------------------------------------------------
def test_no_legal_conclusions_enforced(engine):
    resp = engine.explain(ExplanationRequest(text="Ticket price is ₹499. A processing fee of ₹79 applies."))
    text_corpus = (
        resp.title + " " + resp.summary + " " + (resp.consumer_consequence or "")
        + " " + (resp.financial_consequence or "") + " " + resp.recommended_action
    ).lower()

    forbidden_terms = ["illegal", "unlawful", "scam", "fraud", "violating", "guilty", "crime"]
    for term in forbidden_terms:
        assert term not in text_corpus, f"Found forbidden term '{term}' in explanation output!"
    assert resp.disclaimer == "This is a consumer-risk signal, not a legal determination."


# --------------------------------------------------------------------------
# 23. Practical action generation
# --------------------------------------------------------------------------
def test_practical_action_generation(engine):
    resp = engine.explain(ExplanationRequest(text="7-day free trial, then ₹999/month."))
    action = resp.recommended_action
    assert len(action) > 10
    assert not action.isupper()
    assert "DO NOT" not in action
    assert "cancellation" in action.lower() or "terms" in action.lower()


# --------------------------------------------------------------------------
# 24. Multiple findings and prioritization
# --------------------------------------------------------------------------
def test_multiple_findings_prioritization(engine):
    fusion_resp = EvidenceFusionResponse(
        source="evidence_fusion",
        risk_level="CRITICAL",
        risk_score=8.5,
        financial_signal=True,
        financial_impact=FinancialImpact(
            previous_price=999.0,
            current_price=1299.0,
            price_change=300.0,
            price_change_percentage=30.03,
            initial_price=499.0,
            additional_cost=79.0,
            known_total=578.0,
            trial_price=0.0,
            trial_duration_days=7,
            renewal_price=999.0,
            billing_period="month",
            currency="INR",
        ),
        evidence=[
            EvidenceItem(evidence_id="E001", source="price", type="price_increase", description="Price change ₹300", value=300.0),
            EvidenceItem(evidence_id="E002", source="price", type="free_trial", description="7-day trial", value=0.0),
            EvidenceItem(evidence_id="E003", source="price", type="renewal_price", description="Renewal ₹999", value=999.0),
            EvidenceItem(evidence_id="E004", source="price", type="additional_fee", description="Fee ₹79", value=79.0),
            EvidenceItem(evidence_id="E005", source="text", type="urgency", pattern="urgency", description="Hurry up"),
        ],
    )
    resp = engine.explain(ExplanationRequest(fusion_response=fusion_resp))
    assert len(resp.findings) >= 3
    # Verify priority ordering
    priorities = [f.priority for f in resp.findings]
    assert priorities == sorted(priorities), "Findings must be sorted by priority ascending"


# --------------------------------------------------------------------------
# 25. Full API endpoint test (/explain)
# --------------------------------------------------------------------------
def test_explain_api_endpoint(client):
    req_body = {"text": "7-day free trial, then ₹999/month."}
    response = client.post("/explain", json=req_body)
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "consumer_explanation"
    assert "Free trial" in data["title"]
    assert len(data["findings"]) >= 1
    assert "disclaimer" in data
    assert data["disclaimer"] == "This is a consumer-risk signal, not a legal determination."
