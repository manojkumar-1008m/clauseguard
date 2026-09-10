# Phase B1 — Event & Session Foundation

## Objective
Strengthen the Behavior Analyzer's interaction data layer without changing its existing detection rules.

## Changes
- Added durable `session_id` scoped to a browser tab.
- Added `event_id`, `page_load_id`, `tab_id`, and `window_id`.
- Added structured element metadata: tag, role, text, aria-label, visibility, disabled state, and input type.
- Added sanitized `route` separate from the origin-only URL field.
- Added `PAGE_INIT`, `CLICK`, `INPUT_CHANGE`, and SPA navigation events.
- Added `history.pushState` and `history.replaceState` observation.
- Added per-session event storage with a 500-event cap.
- Preserved legacy `behaviorEvents` and `behaviorAnalysis` storage keys for popup compatibility.
- Added tab cleanup when a tab closes.
- Avoided capturing input values; checkbox/radio changes record only the boolean checked state.
- Updated the analyzer to accept both the legacy string element schema and the new structured element schema.

## Session semantics
A session persists across page navigations in the same tab. A new session is created when a tab has no active session or the previous session has been inactive for 30 minutes. Closing a tab removes its active tab-to-session mapping.

## Validation
- JavaScript syntax checks pass for content, background, and analyzer files.
- Existing analyzer scenario suite passes.
- B1 foundation checks pass.
- Existing detection rules and risk-scoring logic were not intentionally changed in this phase.

## Next phase
B2 — Better Behavioral Features: screen/flow counting, repeated-offer sequences, dead ends, confirmation loops, and stronger cancellation-flow features.
