# Root Cause and Fix Report

## Operation
PAGE_INIT telemetry isolation and realtime canonical-result hardening.

## Purpose
Prevent ordinary lifecycle/interactions from becoming evidence or alerts, and prevent asynchronous results from an obsolete page load from overwriting current journey state.

## Root cause
Raw stored events were previously reconstructed as detected behavior signals. `PAGE_INIT` then became a scored `EvidenceItem`. The explanation fallback created a generic finding from non-empty evidence, and the popup used evidence presence as a potential-signal condition.

## Fix
- Forward only semantic analyzer findings from the extension.
- Reject lifecycle/raw interaction event types in `adapt_behavior_evidence`.
- Require `consumer_gate.actionable === true` for popup/page alerts.
- Associate realtime results with the active session and `page_load_id`; discard stale responses and deduplicate alert keys.

## Backend hardening
- Bound `/analyze` text to 20,000 characters.
- Add request IDs and duration/status logging without logging page text.
- Add `/ready` for model readiness while retaining `/health` as liveness.
- Report active model artifact hash, support MiniLM OFF mode, and bound vision input.

## Validation
The PAGE_INIT reproduction now returns zero evidence, zero score, `CLEAR`, and no alert. Full and focused regression results are recorded in `PRODUCTION_READINESS_REPORT.md`.
