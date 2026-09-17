# Phase 4.5 — Training Report

## Model Identity
- **Architecture**: 6-layer Decoder-only Transformer
- **Parameters**: 5,885,952 (Target: 5–7M)
- **Training Duration**: 1051.8s
- **Best Validation Loss**: 0.1888

## Staged Curriculum Progression
| Stage | Examples | Initial Loss | Final Loss | Status |
|---|---|---|---|---|
| Stage A | 10 | 8.323 | 0.3489 | PASSED |
| Stage B | 100 | 8.355 | 2.8073 | PASSED |
| Stage C | 500 | 8.346 | 3.3809 | PASSED |
| Stage D | 2000 | 8.366 | 2.9842 | PASSED |