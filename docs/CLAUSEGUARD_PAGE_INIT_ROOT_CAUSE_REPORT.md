# ClauseGuard PAGE_INIT Root-Cause Report

## Observed symptom

On a benign JioHotstar-like page, the unified popup showed `Potential Signal` and an evidence row for `PAGE_INIT`, although the journey contained only one page-load event.

## Reproduction

The reproduction posted the benign fixture text from `tests/jiohotstar_regression_page.html` to `/analyze` with one behavior signal:

```json
{"type":"PAGE_INIT","detected":true,"strength":"weak","reason":"PAGE_INIT"}
```

Before the fix:

- V3 text prediction: `prediction=0`, confidence `0.46`, no pattern.
- Price analysis: no monetary entities.
- Evidence Fusion: `risk_score=0.9`, `risk_level=LOW`, one behavior evidence item.
- ConsumerRiskGate: `CLEAR`, `actionable=false`, `risk_detected=false`.
- Explanation: nevertheless produced `Consumer risk signal detected` with `PAGE_INIT` as evidence.
- Popup: treated `evidence_count > 0` as `Potential Signal`.

After the fix:

- V3 and price results are unchanged.
- Evidence Fusion: `risk_score=0.0`, `risk_level=LOW`, `evidence_count=0`.
- ConsumerRiskGate: `CLEAR`, `actionable=false`.
- Explanation: `No strong consumer-risk signal detected`.
- No actionable alert is sent.

## Pipeline trace

1. `extension/content.js` emits `PAGE_INIT` to establish page/session context.
2. `extension/background.js` normalizes and stores it in the tab-isolated journey session.
3. The local behavior analyzer retains the event as telemetry and does not create a behavior finding.
4. The former popup and realtime worker rebuilt every stored event as `{detected: true}` behavior evidence. This was the first incorrect transformation.
5. `backend/services/evidence_adapters.py` accepted the raw type and created `EvidenceItem(type="PAGE_INIT", pattern="PAGE_INIT")`.
6. Evidence Fusion preserved that item and assigned a small non-zero score.
7. The gate correctly returned `CLEAR`; it did not bypass the safety boundary.
8. The explanation fallback incorrectly used any non-empty evidence to create a generic finding.
9. Popup rendering then interpreted non-empty evidence as a potential signal.

## Root cause matrix

| Component | Can generate PAGE_INIT? | Can generate risk? | Incorrectly promoted it? |
|---|---:|---:|---:|
| Content script | Yes | No | No |
| Background/session | Stores it | No | No |
| Journey manager | Preserves context | No | No |
| Local behavior analyzer | Sees it | Internal findings only | No |
| V3 text model | No | Signal only | No; fixture predicted 0 |
| Price analyzer | No | Financial evidence | No |
| Vision | Not called by `/analyze` | Visual evidence endpoint | No |
| Behavior adapter | Accepted it | Evidence item | **Yes, primary cause** |
| Evidence Fusion | Scored accepted item | Canonical score | Contributing consequence |
| Intelligence/regulatory | Receives fused evidence | Assessments | No independent PAGE_INIT finding |
| ConsumerRiskGate | Receives result | Gate decision | No; returned CLEAR |
| Explanation engine | Receives non-empty evidence | Finding text | **Yes, secondary cause** |
| MiniLM | Ranks explanation evidence | Explanation only | No |
| Popup | Renders response | Alert presentation | **Yes, symptom amplifier** |

## Primary and secondary causes

**Primary root cause:** the extension crossed the telemetry boundary by converting raw stored events, including `PAGE_INIT`, into detected behavior evidence. The backend adapter then accepted the lifecycle event as a scored `EvidenceItem`.

**Secondary causes:**

- The popup/realtime payload builder used raw events instead of analyzer-produced semantic behavior findings.
- The adapter had no lifecycle-event defense.
- The explanation fallback created a generic finding for any remaining evidence, even when the gate was `CLEAR` and `risk_detected=false`.
- Popup signal presentation used evidence presence as a potential-signal condition.

## Model, MiniLM, and vision findings

The V3 model was involved in the request but was not responsible: the exact benign fixture produced class `0`, confidence `0.46`, and no mapped pattern. No model artifact, threshold, preprocessing, or score was changed.

MiniLM remained explanation-only. The existing MiniLM invariance coverage remains unchanged, and the fix does not pass MiniLM output into risk or gate logic.

The `/analyze` endpoint does not capture screenshots or invoke MobileNetV3. The separate `/vision/predict` endpoint is not part of this reproduced request.

## Architectural fix

- `extension/popup.js` and `extension/background.js` now forward only `session.analysis.behaviors`, not every stored event.
- `backend/services/evidence_adapters.py` drops lifecycle/raw interaction event types (`PAGE_INIT`, `NAVIGATION`, `INPUT_CHANGE`, `CLICK`, `SCROLL`, `HOVER`, and `TAB_ACTIVE`) before `EvidenceItem` creation.
- `PAGE_INIT` remains available as tab-isolated telemetry and journey context.
- Genuine semantic behavior findings, such as cancellation obstruction, continue through the canonical evidence pipeline.

This preserves the distinction:

`telemetry != evidence != model signal != corroborated signal != actionable risk`

## Tests

Added `tests/test_page_init_root_cause.py` covering PAGE_INIT-only, benign video text, raw normal interactions, adapter filtering, and semantic behavior retention.

Executed successfully:

- Root-cause tests: `6 passed`
- Focused adapter/fusion/gate/analyze tests: `68 passed`
- Extension/security tests: `28 passed`
- DarkShield runtime scripts: passed
- Full Python regression: `766 passed`
- Extension JavaScript syntax checks: passed

## Live Chrome result

The repository-level browser/runtime scripts passed. A live Chrome extension load and DevTools inspection were not available in this validation environment, so no live Chrome result is claimed here. The exact backend reproduction and extension script syntax checks provide deterministic coverage of the reported transformation.

## Remaining limitations

The current popup remains manually analyzable, while the background worker performs debounced realtime analysis. A packaged Chrome/Playwright run should still be performed in an environment with Chrome extension-loading support to verify service-worker messaging and visual presentation end to end.