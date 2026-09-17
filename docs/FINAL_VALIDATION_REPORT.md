# ClauseGuard Final Validation Report

Date: 2026-09-12

## Commands and Counts

### Python

- `pytest -q`: collection error on `DarkShield/test_full.txt` because it is non-UTF8 binary content.
- `python -m pytest -q`: 749 passed, 1 failed, 0 skipped, 0 errors after collection, 0 xfailed, 12 warnings.
- The remaining failure is the locked V3 hard-negative regression: 66.7% accuracy, below the 90% test floor.

### DarkShield JavaScript

Run from `DarkShield/`:

- `test_b1_audit_fixes.js`: 10 passed, 0 failed.
- `test_b1_comprehensive.js`: 19 passed, 10 failed. Failures are caused by missing browser event API stubs in the harness.
- `test_b2_feature_extraction.js`: 20 passed, 0 failed.
- `test_b3_behavior_sequence.js`: 25 passed, 0 failed.
- `test_b4_audit_fixes.js`: 36 passed, 0 failed.
- `test_b4_cross_container.js`: 51 passed, 0 failed.
- `test_b4_dom_analyzer.js`: 42 passed, 0 failed.
- `test_b4_dynamic_dom_diff.js`: 51 passed, 0 failed.
- `test_b4_visual_prominence.js`: 60 passed, 0 failed.
- `test_fix_verification.js`: failed; output did not provide a passing result.

### Browser and extension scripts

- `scripts/test_pipeline_e2e.js`: failed because no backend was listening on `127.0.0.1:8000`.
- `scripts/test_user_scenarios.js`: failed due missing popup DOM elements after the backend connection failure.
- `scripts/test_popup_runtime.js`: failed due missing popup DOM elements in the simulation.
- `scripts/verify_popup.js`: failed function-definition contract checks.
- No real browser -> extension -> backend -> gate -> explanation E2E was completed.

## Verified Runtime Checks

- V3 artifact loads from `model/clauseguard_model_v3.joblib`.
- Runtime version is `clauseguard-text-v3`.
- Model loader cache identity is stable.
- Preprocessing collapses whitespace in the normal preprocessing module.
- `/analyze` returns HTTP 200 for a real renewal-price request and returns a 0-10 score plus a gate decision.
- At score 7.0, fusion and the gate both report HIGH under the canonical 3/5/8 thresholds.
- `/analyze` now returns the deterministic explanation engine result and a populated ExplanationContext.

## Blockers

1. Browser E2E has not been completed against a live backend and real extension runtime.
2. DarkShield harnesses still have incomplete browser API stubs.
3. The V3 hard-negative regression remains below its test floor: 8/12 benign cases classified negative (66.7%), with HN-01, HN-02, HN-07, and HN-10 as false positives.
4. The historical adversarial figure is not reproducible from checked-in artifacts.

## Final Decision

`NOT READY FOR MINILM`.
