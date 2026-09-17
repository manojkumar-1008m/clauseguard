# Adversarial Miss Analysis

Date: 2026-09-12

## Reproduction Status

The previously reported aggregate result was benign clearance 100%, false positives 0%, adversarial recall 42.1%, and 22 P2 misses. That exact result is not reproducible from the checked-in repository: `tests/adversarial_cases.csv` contains 22 category variants but no executable scorer, binary expected labels, or recorded per-case predictions.

The only directly reproducible related result is the V3 hard-negative regression test: 66.7% accuracy, below its 90% floor.

The four reproducible false positives are HN-01 (clear renewal disclosure), HN-02 (self-service cancellation), HN-07 (variant availability), and HN-10 (recurring-payment toggle). Their confidence values were approximately 0.79, 0.57, 0.66, and 0.51. These are limitations in the locked V3 text-only classifier; no safety rule or threshold was changed.

## Classification of the 22 Historical Misses

No case IDs, input texts, or predictions were supplied with the historical aggregate, so assigning a specific root-cause category to each miss would fabricate evidence. The 22 misses are therefore recorded as **UNCLASSIFIED / NOT REPRODUCIBLE** pending the missing evaluation artifact.

| Historical misses | Classification | Reason |
|---:|---|---|
| P2-01 through P2-22 | Not reproducible | Per-case inputs and predictions are absent |

The permitted categories for the future rerun are: expected anti-overreach, extraction, normalization, taxonomy, model, fusion, journey, gate suppression, ground truth, and browser limitation.

## Safety Interpretation

No safety threshold was weakened and V3 was not retrained. The current failures must be resolved by restoring evidence extraction, taxonomy consistency, contract alignment, or evaluation traceability rather than by making isolated signals actionable without corroboration.
