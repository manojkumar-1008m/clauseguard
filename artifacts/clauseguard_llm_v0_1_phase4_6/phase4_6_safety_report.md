# Phase 4.6 — Safety, Bounds & Fallback Report

## 1. Input Boundary & Validation Tests

| Test Case | Expected HTTP Code | Actual HTTP Code | Status |
|---|---|---|---|
| `valid_request` | 200 | 200 | PASS |
| `oversized_context` | 422 | 422 | PASS |
| `malformed_context` | 422 | 422 | PASS |
| `oversized_question` | 422 | 422 | PASS |
| `stale_context` | 409 | 409 | PASS |

## 2. Fallback Mechanism (Operation 13)
- **Simulated Checkpoint Disruption:** Pointed checkpoint path to invalid file.
- **Service Behavior:** Instantly fell back to `LocalAnswerGenerator`.
- **Response Status:** HTTP 200 OK
- **Metadata Returned:**
  * `fallback_used`: **True**
  * `provider`: `"local_deterministic_fallback"`
  * `model`: `"deterministic-templates"`
- **Recovery:** Restoring valid checkpoint immediately reinstated `ClauseGuardDecoderAnswerProvider`.

## 3. Legal & Behavioral Safety
- Forbidden legal determination phrases tested: 0 detections in generated answers.
- `legal_overclaim_rate`: **0.0%**
- External API calls: **0**
- Pretrained weights: **0**

## Verdict: PASS
