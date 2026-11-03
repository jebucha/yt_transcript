# Design

## Context

See proposal.md for motivation. Current state that shapes the approach:

- `app/log.py` configures structlog to write one JSON object per line through a **stream** (`setup_logging(stream)`, `PrintLoggerFactory(file=stream)`). The stream is resolved lazily when a logger is created, and tests already reconfigure structlog with a capture stream (autouse fixture in `tests/conftest.py`).
- `app/main.py` calls `applog.setup_logging()` twice (at import and in `main()`); `app/persist.py` logs from a **worker thread** (`save_transcript` via `asyncio.to_thread`); `app/chain.py` runs the fetcher *call* in a worker thread, but all of its `fetch_attempt` log calls execute on the event loop.
- Failure causes exist but are discarded at the log site: `chain.py` builds messages like *"primary fetch timed out after 30s"* and logs only `exc.code`; `persist.py` logs only `type(exc).__name__`.
- The UI is vanilla JS (no build step, no CDN), inserts all content via `textContent`, and its e2e tests run a real in-process uvicorn with the fetch chain stubbed (`tests/e2e/test_ui.py` pattern).
- Constraints: no new dependencies; stdout remains the only log *output* destination (structured-logging spec); read endpoints never touch the fetch chain's single-flight semaphore; the project deliberately avoids automatic polling (saved-list design decision 6).

## Goals / Non-Goals

**Goals:**

- Live, in-browser view of the server's structured log stream with recent-history replay, using zero new dependencies.
- Fetch and save failure log events that carry the failure cause (`detail`, plus `path` for saves) — useful in the panel *and* in `docker logs`.
- stdout output stays byte-identical in format; the in-memory mirror is internal state.

**Non-Goals:**

- Client-side (browser) log events — only server-side events are streamed.
- UI log filtering, level selection, search, or export.
- Durable log history (surviving restarts) — memory only.
- Preserving raw yt-dlp stderr in fetch logs (the fetcher's error mapping already discards it; error code + chain-level detail cover the diagnostic value).
- DEBUG-level events — the logger filters at INFO; nothing changes.

## Decisions

1. **Transport: server-sent events, not polling or WebSocket.** `GET /api/logs` returns a `StreamingResponse` with `text/event-stream`; the browser uses the native `EventSource` (auto-reconnect included). Alternatives considered: polling with a cursor — adds the exact pattern the project deliberately avoided for the saved list, and latency is bounded below by the poll interval; WebSocket — requires a new dependency, bidirectionality is not needed, and reconnect handling is manual. SSE is one-way (which is all this needs), instant, and dependency-free.

2. **Delivery seam: a tee stream in front of stdout.** `LogBus` (new `app/logbus.py`) holds a bounded ring buffer (`collections.deque(maxlen=200)`) and a set of subscribers. A `TeeStream` object implements `write()`: it forwards each complete line to the *current* `sys.stdout` — resolved lazily at write time, never the import-time or `sys.__stdout__` handle, matching the lazy stream resolution the capsys-based tests rely on (`tests/test_logging_requests.py` captures after a no-arg `setup_logging()`) — **and**, when the line is the rendered JSON entry, publishes the parsed entry to the bus. The default stream of `setup_logging` becomes this tee (passing an explicit stream, as tests do, still bypasses the bus entirely). Alternatives considered: a structlog processor that pushes to the bus — couples the processor pipeline to the viewer and loses the existing stream-based test hook; a `logging`-style handler — this project uses structlog's factory/stream design, and the stream seam is where the app already plugs in test streams. The tee keeps `log.py`'s public shape and makes "stdout is still written" structurally obvious.

3. **Thread-safe fan-out.** Log calls arrive from worker threads (persistence, fetchers) and the event loop; SSE generators run on the event loop. The bus guards the deque and subscriber list with a lock, and each subscriber gets a thread-safe `queue.Queue`; the per-connection async generator polls its queue via `queue.get(timeout=…)` in a loop, run in an executor (`asyncio.to_thread`), so a log written from a worker thread wakes the stream without busy-waiting and without ever blocking the logging thread — and a client disconnect can cancel the in-flight poll instead of leaving a default-executor thread (shared with `save_transcript` and the transcript list/read endpoints) blocked in `get()` indefinitely. Fan-out is drop-on-full per subscriber (a slow or dead tab loses lines, never stalls the app). Entry order in the buffer matches log-call order because publishing is serialized by the lock.

4. **Replay on connect.** The `/api/logs` generator first subscribes to the bus, then flushes the ring buffer oldest→newest, then streams live entries. Subscribe-before-snapshot closes the race where an entry logged between the snapshot and the subscribe would be lost on the first connect; the small duplicate window this ordering can introduce is the same reconnect trade-off already accepted in Risks. One entry per SSE event: `data: <single JSON line>\n\n`. No sequence numbers or `Last-Event-ID` handling in the MVP (see Risks).

5. **Failure detail fields.** `chain.py` failure events gain a `detail` field with the message built at each failure site, sourced per branch: the `TranscriptError` branch logs `detail=exc.message`; the timeout branch logs `detail=timeout_err.message` (the constructed `UpstreamFailureError`, which carries the timeout duration — the raw `asyncio.TimeoutError` has no `.message`); the generic branch logs `detail=generic.message` (the constructed `UpstreamFailureError` naming the unexpected exception type). `persist.py` save-failure events gain `path=str(path)` and `detail=str(exc)` (the OS error string, which embeds the failing path). `reason` fields are untouched. The fetchers are **not** modified to preserve raw yt-dlp stderr.

6. **UI shape.** A `#logs-toggle` button ("Show logs" ⇄ "Hide logs") in the page header area and a `#log-panel` `<pre>` (monospace, scrollable, bounded max-height) at the bottom of the container. `EventSource("/api/logs")` is opened once at page load — panel visibility is purely a display concern, so entries logged while hidden are still present when the panel is re-shown (spec scenario). Rendering: a small event-name → formatter map for the known events (`server_started`, `server_stopped`, `http_request`, `fetch_attempt`, `fetch_rejected`, `transcript_saved`, `transcript_save_failed`, `unhandled_exception`) producing one line of `time  LEVEL  event  key fields`; unknown events fall back to `time  LEVEL  event  key=value ...`. Every string enters the DOM via `textContent`. The panel trims its oldest lines when it exceeds its display cap (200 lines, matching the server buffer).

7. **Endpoint placement.** `GET /api/logs` is registered in `create_app()` alongside the other API routes, before the static mount (so route precedence is preserved). It takes no parameters, performs no filesystem work, and never touches the fetch chain or its semaphore — the spec's "does not affect the fetch chain" scenario.

## Test Strategy

- **Runner:** pytest, invoked as `uv run python -m pytest` from the repo root in the locked uv environment.
- **Full non-e2e suite:** `uv run python -m pytest tests/ -q --ignore=tests/e2e`.
- **Full e2e suite:** `uv run python -m pytest tests/e2e/ -q` (headless Chromium; in-process uvicorn harness with the fetch chain stubbed — no network required).
- **Prerequisite (e2e only):** `cmd: uv run python -m playwright install chromium` — typed, idempotent probe (exits 0 when Chromium is already installed).
- The delta specs' Test Requirement blocks carry these commands directly; every block's pass criterion is exit code 0 with no skipped tests.

## Risks / Trade-offs

- [Cross-thread delivery is the fiddliest part (worker thread → event loop wake-up)] → all thread-safety lives inside `LogBus`; unit tests log from multiple threads while a subscriber is actively drained, and assert order and no-deadlock.
- [A dead/slow subscriber blocks the logging path] → per-subscriber drop-on-full queues; unsubscribing on generator exit (`finally`); the logging thread never awaits anything.
- [Memory growth from long-running servers] → hard `maxlen` on the ring buffer and on the client panel; entries are small JSON lines.
- [SSE reconnect after a network blip can re-append already-shown lines (replay from the buffer)] → accepted for a debug panel; no dedup in the MVP. Revisit only if it becomes visually annoying.
- [The in-memory mirror could be misread as violating "stdout SHALL be its only log output"] → it is internal state, not an output destination; the `log-viewer` spec's "Logging unaffected by the log viewer" requirement pins stdout behavior with and without subscribers (T-LOG-VIEWER-006/007), and the existing format tests keep running against the real stream.
- [E2E display-cap and fallback tests need many synthetic events] → the e2e harness already runs the app in-process (it patches the fetch chain the same way); tests emit synthetic log entries through the app's own logger, no network needed.
- [Each open SSE connection holds one default-executor thread during its poll, sharing the executor with `save_transcript` and the transcript list/read endpoints] → acceptable for a single-operator debug panel; revisit (connection cap or an asyncio-native queue bridge) only if concurrent connection counts grow.
- [New unauthenticated read surface: `GET /api/logs` streams every server log entry to any client] → consistent with the app's existing unauthenticated read endpoints; log content is constrained by the structured-logging "No sensitive data in logs" requirement (T-STRUCTURED-LOGGING-009) and the panel renders every field via `textContent` (T-LOG-VIEWER-017); no extra controls in the MVP.

## Migration Plan

No migration: one new read-only endpoint, one new UI panel, two enriched log fields. Deploy as usual (docker compose / `uv run python -m app.main`). Rollback is a plain revert — no state, schema, or data to migrate; clients on the old static files simply lack the toggle.
