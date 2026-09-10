# ClauseGuard Text Model V3 Master Evaluation Report

- **Model Version:** `clauseguard-text-v3`
- **Final Test Samples:** 504 (Untouched, Locked)
- **Accuracy:** 95.63%
- **F1 Score:** 0.9600
- **Dark Pattern Recall:** 97.06%
- **Precision:** 94.96%
- **ROC-AUC:** 0.9861
- **Brier Score:** 0.0511

## Domain Performance

| Domain | Samples | Accuracy | F1 | Recall | FP | FN |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| compliance/privacy | 58 | 96.6% | 0.982 | 100.0% | 2 | 0 |
| ecommerce | 446 | 95.5% | 0.954 | 96.3% | 12 | 8 |

## Error Analysis

- **DOMAIN_SHIFT:** 9 errors
- **VOCABULARY_GAP:** 7 errors
- **REQUIRES_CONTEXT:** 5 errors
- **CONTEXT_FAILURE:** 1 errors
