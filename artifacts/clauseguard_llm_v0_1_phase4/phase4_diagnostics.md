# Phase 4 Diagnostics

- Causal masking and target shifting: All prompt tokens through <ANSWER> are masked with -100.
- First active label is strictly the first token of the answer.
- EOS completion is actively trained and verified at answer boundary.
- Zero left-padding contamination during generation.
- Model capacity restored to 5.88M parameters (within 5–7M range).
- Standalone from-scratch model; runtime context remains authoritative.
