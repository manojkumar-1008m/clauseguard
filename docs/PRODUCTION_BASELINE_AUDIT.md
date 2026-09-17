# ClauseGuard Production Baseline Audit

## Snapshot

- Audit date: 2026-09-13
- Branch: `master`
- Workspace: Windows, repository under `clauseguard/`
- Worktree: dirty; the repository files are currently untracked from the parent workspace, and unrelated files exist in the parent Downloads directory. No destructive git operation was performed.
- Existing baseline before this hardening pass: PAGE_INIT telemetry isolation had already been implemented and documented.

## Actual structure

- Backend: `backend/main.py`, schemas, model loader, text/price/evidence/intelligence/regulatory/gate/explanation services, and MobileNetV3 vision service.
- Current extension: `extension/`, Manifest V3, one popup, one content script, one service worker, and copied analyzer/journey modules.
- Historical extension: `DarkShield/extension/`, retained for its existing runtime tests and not selected by the current `extension/manifest.json`.
- Models: V3 text artifact preferred by `backend/model_loader.py`; V2/V1 fallback artifacts remain present. MiniLM is lazy and explanation-only. Vision is a separate `/vision/predict` endpoint and is not automatically called by `/analyze`.
- Data: versioned train/validation/test CSVs and model metadata/release reports.
- Tests: Python backend/integration/security/model suites plus DarkShield JavaScript runtime tests.
- Configuration: backend and extension API endpoints were localhost constants; model and MiniLM path selection already had limited environment support.

## Canonical request path

The current browser path is:

`content.js -> background.js session/journey storage -> popup or debounced background request -> POST /analyze -> EvidenceFusionEngine -> intelligence/regulatory/consequence processing -> ConsumerRiskGate -> ExplanationContext -> explanation/MiniLM -> popup or page alert`

Raw lifecycle events remain telemetry. Semantic analyzer findings are the only behavior payload forwarded after the PAGE_INIT repair.

## Known findings before this hardening pass

1. PAGE_INIT had previously crossed the extension payload boundary as detected behavior evidence. This was fixed by using analyzer findings only and rejecting lifecycle event types in the backend adapter.
2. The backend had no explicit request identity/readiness endpoint or bounded `/analyze` text contract.
3. Realtime result commits did not yet verify that the page load and journey were still current when an asynchronous response returned.
4. Full live unpacked-Chrome validation was unavailable in the integrated browser environment.

## Validation baseline

The existing regression baseline was green after the PAGE_INIT repair. This hardening pass will rerun the full suite, focused telemetry/model/MiniLM/security tests, JavaScript syntax checks, and DarkShield runtime tests. Live Chrome status will be reported separately and will not be represented as passed unless the unpacked extension is actually loaded.
