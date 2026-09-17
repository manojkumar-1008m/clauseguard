# ClauseGuard Risk Contract

The verified Evidence Fusion contract is a bounded 0-10 score with LOW, MEDIUM, HIGH, and CRITICAL levels. Component calculators feed deterministic fusion and must not override it.

The legacy `overall_risk.py` module uses 0-100 internally for compatibility callers. Its result is not included in EvidenceFusion responses or `/analyze`, and it cannot override the canonical result.

The ConsumerRiskGate consumes the 0-10 fusion score on `/analyze`. Legacy `/fuse-evidence` and `/explain` remain compatibility/testing endpoints; production extension clients use `/analyze`.
