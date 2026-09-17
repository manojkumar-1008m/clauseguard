# Ask ClauseGuard

## Purpose

Ask ClauseGuard explains the current ClauseGuard assessment. It does not make or modify risk decisions.

## Architecture

```text
User question
    -> deterministic question understanding
    -> relevant evidence retrieval
    -> allowlisted AskClauseGuardContext
    -> deterministic answer provider
    -> grounding validator
    -> safe answer
```

The risk path remains separate:

```text
Page signals -> Evidence Fusion -> ConsumerRiskGate -> canonical result
```

Ask consumes a snapshot of that canonical result. It cannot change risk score, risk level, actionability, evidence, regulatory findings, or journey state.

## API

`POST /ask`

Request:

```json
{
  "request_id": "optional-correlation-id",
  "question": "Could I be charged later?",
  "context": {
    "page_id": "page-load-id",
    "journey_id": "journey-id",
    "risk_level": "HIGH",
    "risk_score": 7.5,
    "gate_decision": "ACTIONABLE_RISK",
    "actionable": true,
    "risk_detected": true,
    "primary_pattern": "subscription_trap",
    "evidence": [
      {
        "evidence_id": "E2",
        "source": "price",
        "type": "renewal_price",
        "description": "Renewal price of ₹999/month",
        "value": 999,
        "currency": "₹"
      }
    ]
  },
  "current_page_id": "page-load-id",
  "current_journey_id": "journey-id"
}
```

Response:

```json
{
  "request_id": "ask-test-1",
  "answer": "The verified evidence shows...",
  "intent": "FINANCIAL_IMPACT",
  "answer_class": "ACTIONABLE_RISK",
  "grounded": true,
  "evidence_ids": ["E2"],
  "confidence": 0.95,
  "requires_context": false,
  "provider": "deterministic",
  "model": "deterministic-templates",
  "fallback_used": false,
  "error_code": null
}
```

## Safety and limits

- Questions are limited to 2,000 characters.
- Evidence is limited to 20 items and descriptions to 1,500 characters.
- Context is limited to 30,000 serialized characters.
- Answers are limited to 8,000 characters.
- Context page and journey IDs must match the current IDs when supplied.
- Context older than 30 minutes returns `CONTEXT_STALE`.
- A per-client in-memory rate limit protects the endpoint; configure with `CLAUSEGUARD_ASK_RATE_LIMIT`.
- Webpage evidence is data, never instructions.
- No raw HTML, passwords, payment data, cookies, tokens, or external URLs are accepted by the Ask contract.

## Providers

`QuestionUnderstandingProvider`, `EvidenceRetrievalProvider`, and `AnswerGenerationProvider` are explicit provider boundaries. The current production-safe provider is deterministic templates. MiniLM can remain an optional retrieval implementation, but it is not generative and cannot decide risk. An external LLM provider may be added behind `AnswerGenerationProvider`; it must receive only the allowlisted context and never an API key from the extension.

## Consumer behavior

- CLEAR pages receive clear, non-alarmist answers.
- POTENTIAL or context-required results remain potential/context-dependent.
- ACTIONABLE_RISK answers cite only selected evidence and consequences.
- Legal questions without regulatory context return jurisdiction-aware uncertainty.
- Unknown prices and historical states remain unknown.
- Grounding failure returns a safe uncertainty response.

## Deployment configuration

The current deterministic path requires no external model or secret. A hosted deployment should configure the API base URL, Ask provider, timeout, rate limit, authentication, explicit CORS origins, and LLM credentials on the backend only. Never expose provider keys in the browser extension.
