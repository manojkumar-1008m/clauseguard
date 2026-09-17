# Security Audit

## Verified
- Manifest V3; no `tabs`, cookies, history, webRequest, debugger, or notification permissions.
- Backend host permission is limited to `http://127.0.0.1:8000/*`.
- Popup uses `textContent`/DOM construction and no `innerHTML`, `eval`, `document.write`, or `new Function`.
- Input/form metadata is sanitized; typed values, passwords, tokens, and payment-card fields are excluded.
- URLs and query parameters are sanitized by the service worker.
- CORS is not wildcarded.
- Backend errors return safe public messages; request logs contain IDs/status/timing, not page content.
- `/analyze` text is bounded to 20,000 characters.
- URL fragments are dropped from active journey routes to avoid retaining token-like data.
- Vision requests accept only supported image media types and are capped at 5 MiB.
- MiniLM fallback metadata uses stable reason codes rather than raw exception text.

## Residual risks
- The extension currently runs against localhost and is intended for controlled development/demo use.
- Content scripts cannot inspect cross-origin iframe content; this is a limitation, not a bypass.
- A live Chrome permission/message-origin audit remains pending.
- Production deployment still needs HTTPS, authentication/rate limiting, retention controls, dependency scanning, and operational monitoring.
