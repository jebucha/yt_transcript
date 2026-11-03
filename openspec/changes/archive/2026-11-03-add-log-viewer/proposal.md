# Proposal

## Why

Fetch failures and disk-persistence failures are only visible today via `docker logs`, and the log events that do exist answer "what" but not "why": a failed fetch is logged with an error *code* (e.g. `UPSTREAM_FAILURE`) while the built-up cause message (e.g. "primary fetch timed out after 30s") is discarded, and a failed transcript save is logged with only the exception *type name* — no file path, no OS message. Worse, a failed save is invisible in the UI entirely: the endpoint returns 200 regardless. This change makes the server's structured log stream viewable in the browser with a show/hide toggle, and enriches the two failure events so the panel can actually explain failures.

## What Changes

- New in-browser log viewer: a "Show logs" / "Hide logs" toggle and a scrollable panel that displays the server's structured log events live, rendered as humanized one-line entries (timestamp, level, event, key fields) rather than raw JSON.
- New `GET /api/logs` server-sent events endpoint streaming log entries to subscribed browser tabs, with an in-memory ring buffer so opening the panel replays recent history (capped, INFO level and above only).
- Log routing: the existing structlog stream is tee'd so every log line still goes to stdout (unchanged `docker logs` behavior) and is additionally mirrored in memory for the log viewer. No file logging is introduced.
- `fetch_attempt` failure log events gain a `detail` field carrying the error message that already exists on the raised exception (timeout, fetcher failure cause).
- `transcript_save_failed` log events gain a `path` field (the target file path) and a `detail` field (the OS error string). The machine-readable `reason` (exception type name) is unchanged.
- No new dependencies: streaming uses FastAPI's built-in `StreamingResponse`; the UI stays vanilla JS with no build step and inserts all content via `textContent` only.

## Capabilities

### New Capabilities

- `log-viewer`: the in-browser log panel and its server support — the SSE log stream endpoint, the in-memory ring buffer fed by a tee of the structured log stream, and the show/hide UI toggle with humanized rendering of known event types.

### Modified Capabilities

- `structured-logging`: the "Fetch operation logging" and "Persistence operation logging" requirements are extended by new (added) requirements — the base requirement text is unchanged, but failure events must additionally carry the cause detail (`detail`) and, for save failures, the target `path`.

## Impact

- **Code**: `app/log.py` (tee stream + in-memory log bus), `app/main.py` (new `/api/logs` route, tee wiring), `app/chain.py` (log `detail` on fetch failures), `app/persist.py` (log `path` + `detail` on save failure), `app/static/index.html` / `style.css` / `app.js` (toggle + panel + humanized renderer).
- **API**: one new read-only endpoint, `GET /api/logs` (`text/event-stream`). Existing endpoints unchanged.
- **Dependencies**: none added.
- **Tests**: new unit tests for the ring buffer/tee and API test for the SSE stream; new e2e UI tests for the toggle and panel; existing logging tests in `tests/test_logging_fetch.py` and `tests/test_persistence.py` extended for the new fields.
- **Constraints preserved**: stdout remains the only log *output* destination (the in-memory mirror is internal state, not output); no file logging; textContent-only DOM insertion; no build step or CDN.
