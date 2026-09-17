# ClauseGuard Dataset Registry

Date: 2026-09-12

## Locked V3 Assets

| Asset | Role | Status |
|---|---|---|
| `data/train_v3.csv` | V3 training data | Present; not modified |
| `data/validation_v3.csv` | V3 validation data | Present; not modified |
| `data/final_test_v3.csv` | V3 final test data | Present; not modified |
| `data/hard_test_v3.csv` | V3 hard/generalization data | Present; not modified |
| `model/clauseguard_model_v3.joblib` | Serialized V3 model | Present; loaded during validation |
| `model/release_metadata_v3.json` | V3 release metadata | Present |

## Additional Evaluation Assets

- `tests/adversarial_cases.csv`: 22 case variants with expected categories; no executable scorer or binary outcome labels were found.
- `tests/hard_negative_regression.csv`: hard-negative regression set used by the robustness test.
- `data/raw/`: source and manifest assets used for dataset construction.

## Integrity Notes

The validation operation did not train, rewrite, or replace any model or dataset. `model/model_metadata.json` now identifies the V3 artifact and its 1-3 gram pipeline consistently with the release metadata. The serialized model artifact itself was not altered.
