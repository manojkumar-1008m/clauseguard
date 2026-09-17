# ClauseGuard Final Architecture Audit

Date: 2026-09-12
Status: Architecture reconciliation complete; one locked-model regression remains.

## Executive Result

The deterministic analyzers, evidence adapters, intelligence layer, regulatory layer, V3 model, and explanation service now meet one backend `/analyze` runtime contract. `/analyze` accepts image evidence, invokes the ConsumerRiskGate, constructs ExplanationContext, and invokes the explanation engine.

## Ownership

| Component | Calculates risk? | Intended role | Validation status |
|---|---:|---|---|
| TextPredictor | Yes, text prediction only | Specialized analyzer | Pass |
| EvidenceFusionEngine | Yes, final 0-10 fusion score | Canonical evidence-risk owner | Public owner |
| dark_pattern_risk.py | Yes | Component score | Component only |
| financial_risk.py | Yes | Component score | Component only |
| transparency_risk.py | Yes | Component score | Component only |
| regulatory_risk.py | Yes | Component score | Component only |
| historical_risk.py | Yes | Component score | Component only |
| overall_risk.py | Yes, 0-100 aggregate | Compatibility-only internal caller | Not returned by fusion or `/analyze` |
| ConsumerRiskGate | Yes, decision mapping | Post-risk consumer decision gate | Used by `/analyze` |
| ExplanationEngine | No | Evidence-grounded explanation | Existing standalone endpoint |

No module was deleted. The 0-100 compatibility module remains callable internally but is no longer reachable through fusion responses or extension rendering.

## Safety Findings

- Regulatory output is qualified and provenance-aware.
- Vision creates image evidence; it does not calculate final risk.
- Explanation engine is deterministic and does not independently infer raw risks.
- Journey fields exist in backend schemas and adapters, and both extension clients forward available metadata; unknown context remains explicit when unavailable.
- There is no MiniLM or GPT-OSS-120B dependency.

## Decision

`NOT READY FOR MINILM`. The blockers are listed in `FINAL_VALIDATION_REPORT.md`.
