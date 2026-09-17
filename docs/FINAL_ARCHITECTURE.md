# ClauseGuard Final Architecture

This document records the architecture that is present, not an unimplemented target.

## Current Flow

```text
text / price / DOM / behavior / image payloads
        -> evidence adapters
        -> EvidenceFusionEngine
        -> IntelligenceEngine
        -> RegulatoryEngine
        -> component risk calculators
        -> ConsumerRiskGate
        -> ExplanationContext
        -> ConsumerExplanationEngine
```

## Contracts

- Evidence is represented by `EvidenceItem` with source, provenance, context, temporal, and journey fields.
- Evidence fusion exposes a 0-10 `risk_score` and LOW/MEDIUM/HIGH/CRITICAL levels.
- The legacy `overall_risk.py` module remains available only for direct internal compatibility callers; it is not returned by EvidenceFusion or `/analyze`.
- `ExplanationContext` is a verified, read-only schema and contains no model authority over risk.

## Runtime Boundary

The intended future boundary is:

```text
Canonical Risk Result -> ExplanationContext -> deterministic or future MiniLM explanation
```

`/analyze` now constructs this boundary and returns the structured explanation, while `/explain` remains available for compatibility.

## Extension Boundary

The standard extension and DarkShield construct explicit evidence payloads and use `/analyze` for the canonical production risk path. Browser-local storage is not used by backend services.

## Hardening additions

- Lifecycle and raw interaction events are telemetry only and are rejected by the behavior adapter.
- Realtime results are committed only when tab, session, and page-load identity remain current; alert keys suppress duplicates.
- `/analyze` has a bounded text payload, request IDs, duration/status logging without page content, and `/ready` model readiness reporting.

## Ask ClauseGuard

Ask is a separate explanation path: `question -> intent -> evidence retrieval -> allowlisted AskClauseGuardContext -> deterministic answer provider -> grounding validator`. It consumes the canonical post-gate result and cannot modify scoring, actionability, evidence, regulatory output, or journey state. MiniLM remains optional retrieval/ranking support and is never treated as a generator or risk authority.
