"""Phase 4.7 UI-to-local-Ask integration contracts."""
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def subscription_context(page_id, amount=None, period=None):
    evidence = [
        {
            "evidence_id": "trial",
            "source": "price",
            "type": "free_trial",
            "description": "7-day free trial",
            "strength": "strong",
        }
    ]
    if amount is not None:
        evidence.append({
            "evidence_id": "renewal",
            "source": "price",
            "type": "renewal_price",
            "description": f"Renewal price of ₹{amount}/{period}",
            "value": amount,
            "currency": "₹",
            "strength": "strong",
        })
    return {
        "page_id": page_id,
        "journey_id": f"journey-{page_id}",
        "route": "/checkout",
        "risk_level": "CRITICAL",
        "risk_score": 9.0,
        "gate_decision": "ACTIONABLE_RISK",
        "actionable": True,
        "risk_detected": True,
        "primary_pattern": "subscription_trap",
        "evidence": evidence,
        "consequences": ["The trial may convert into a recurring subscription."],
        "recommended_action": "Review the renewal amount and cancellation terms before continuing.",
    }


def ask(ctx, question="How much will I be charged after the trial?", history=None):
    return client.post("/ask", json={
        "request_id": f"phase47-{ctx['page_id']}",
        "question": question,
        "context": ctx,
        "current_page_id": ctx["page_id"],
        "current_journey_id": ctx["journey_id"],
        "conversation_history": history or [],
        "prefer_local_llm": True,
    })


def test_local_model_metadata_and_context_a_is_grounded():
    response = ask(subscription_context("a", 999, "month"))
    data = response.json()
    assert response.status_code == 200
    assert "₹999/month" in data["answer"]
    assert data["provider"] == "clauseguard_decoder_llm"
    assert data["model_used"] == "ClauseGuardDecoderLM-v0.1"
    assert data["checkpoint_sha256"] == "2f8b756bcf4438c2add273a9e4db5f5009d977908a9af9390707c1563013dccd"


def test_context_b_and_unknown_do_not_leak_context_a():
    context_b = subscription_context("b", 499, "quarter")
    context_c = subscription_context("c")
    answer_b = ask(context_b).json()["answer"]
    answer_c = ask(context_c).json()["answer"]
    assert "₹499/quarter" in answer_b
    assert "₹999" not in answer_b
    assert "could not determine the amount" in answer_c.lower()
    assert "₹499" not in answer_c


def test_follow_up_receives_bounded_history():
    ctx = subscription_context("follow-up", 999, "month")
    response = ask(ctx, "What evidence did you find?", ["What evidence did you find?", "7-day free trial"])
    assert response.status_code == 200
    assert "evidence" in response.json()["answer"].lower()


def test_popup_and_background_contracts_are_local_and_safe():
    popup = (ROOT / "extension" / "popup.js").read_text(encoding="utf-8")
    background = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
    assert "globalThis.chrome?.runtime" in popup
    assert "runtime.sendMessage" in popup
    assert "conversation_history" in popup
    assert "prefer_local_llm: true" in popup
    assert "ASK_CLAUSEGUARD" in background
    assert "fetch(ASK_ENDPOINT" in background
    assert "innerHTML" not in popup
    assert "eval(" not in popup
    assert "openai" not in background.lower()
    assert "gemini" not in background.lower()
    assert "anthropic" not in background.lower()
    assert "extractCanonicalPattern" in popup
    assert "explanation.pattern" in popup
    assert "response_mode" in popup
    assert "result.response_mode" in popup
    assert "Other" not in popup or "\"Other\"" not in popup
