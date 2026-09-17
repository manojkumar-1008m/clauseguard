# Real-World End-to-End Validation

## Status

**Regression-clean controlled MVP validated through end-to-end consumer scenarios.**

This was a validation-only operation. No V3 model, thresholds, Evidence Fusion
weights, ConsumerRiskGate logic, or MiniLM architecture was changed.

## Environment

- Windows, Python 3.13.2, pytest 8.4.1
- FastAPI TestClient and local Uvicorn API
- Node.js runtime for DarkShield and extension simulations
- CPU inference
- MiniLM: `sentence-transformers/all-MiniLM-L6-v2`
- Canonical endpoint: `POST /analyze`

## Scenarios

Seven scenarios were submitted through `/analyze`, including text, price, DOM,
behavior, and image evidence where applicable. Each scenario was run with the
real MiniLM backend and again with MiniLM forced into deterministic fallback.

| Scenario | Result | Risk / gate | Notes |
|---|---|---|---|
| Benign product page | Pass | `0.0`, LOW, CLEAR | No actionable claim |
| Subscription trap | Pass | `8.0`, CRITICAL, ACTIONABLE_RISK | Renewal evidence and consequence grounded |
| Late additional fee | Pass | `2.0`, LOW, CLEAR | `$79` and `$578` came from observed price evidence |
| Cancellation obstruction | Pass | `6.45`, HIGH, ACTIONABLE_RISK | DOM and repeated-retention behavior correlated |
| Visual countdown only | Pass | `1.0`, LOW, POTENTIAL | Non-actionable; no automatic actionable classification |
| Countdown plus urgency/scarcity | Pass | `5.0`, HIGH, ACTIONABLE_RISK | Stronger corroborating evidence present |
| Benign social proof/scarcity | Pass | `2.0`, LOW, POTENTIAL | Potential signal only, not actionable or definitive legal claim |
| Mixed text + price + DOM + behavior | Pass | `10.0`, CRITICAL, POTENTIAL | `requires_context=true` preserved |

Scenario checks: **7/7 passed**. Evidence IDs in every final explanation were
verified to be a subset of the IDs in `ExplanationContext`.

## Pipeline Coverage

The validation exercised:

`consumer input -> extension-shaped payload -> text/V3 analysis -> price analysis -> DOM/behavior/image evidence -> Evidence Fusion -> Intelligence -> regulatory assessment -> canonical risk -> ConsumerRiskGate -> ExplanationContext -> MiniLM ranking/fallback -> consumer explanation`

The extension popup test confirmed that the `/analyze` response reaches the UI
and renders the final explanation.

## MiniLM ON/OFF Invariance

For every scenario, these fields were identical between MiniLM enabled and
forced fallback runs:

- risk score and risk level
- `ConsumerRiskGate` result
- Evidence Fusion evidence and canonical output fields
- regulatory assessment
- intelligence/pattern status
- explanation context
- V3-backed response contract

Only semantic-layer metadata and ranking availability differed. MiniLM remained
an evidence-ranking aid and did not generate facts, prices, legal conclusions,
or risk decisions.

## Grounding and Traceability

Actionable explanations referenced observed evidence IDs and descriptions only.
Observed monetary values, renewal terms, and fee totals matched the input price
signals. No unsupported regulatory violation or certainty claim was produced.
Context-required mixed evidence remained context-required, and the deterministic
fallback preserved the same explanation facts.

## Browser and Extension Validation

- Standalone DarkShield JavaScript tests: passed
- Popup/runtime simulation against the local API: passed
- `/analyze` request and response path: passed
- Extension-visible response latency: approximately 4.6 seconds cold in the test
  environment

## Performance

- First MiniLM-enabled `/analyze`: approximately 5.0 seconds
- Cached MiniLM-enabled `/analyze`: approximately 37.5 ms
- Forced fallback `/analyze`: approximately 14.1 ms
- MiniLM embedding inference on the measured request: approximately 23.5 ms
- MiniLM process RSS during measurement: approximately 535 MB

The first load is CPU and model-startup dominated. No optimization was attempted.

## Regression Results

- Focused MiniLM/invariance tests: passed
- Full Python regression: **755 passed, 23 warnings**
- Existing DarkShield tests: passed
- Extension popup runtime: passed

Warnings were existing dependency deprecations from Pydantic, FastAPI, and
Starlette/httpx. No validation failures remain.

## Known Limitations

- This is controlled local-fixture validation, not production traffic or real
  browser-store deployment.
- Vision coverage used the existing image-evidence contract and did not run a
  live camera or screenshot capture in this operation.
- Some benign unsupported signals remain `POTENTIAL` by design; they are not
  escalated to actionable risk without sufficient corroboration.
- The report does not establish production readiness.