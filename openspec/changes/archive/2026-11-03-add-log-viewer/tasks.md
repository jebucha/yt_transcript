# Tasks

## 1. Log bus and tee (server foundation)

- [x] 1.1 Create `app/logbus.py` with a `LogBus`: a `collections.deque(maxlen=200)` ring buffer plus a lock-guarded subscriber registry (one thread-safe queue per subscriber, drop-on-full on publish). Provide `publish(entry)`, `snapshot()` (oldest→newest), and `subscribe()`/`unsubscribe()`. Verify with unit tests in `tests/test_log_viewer.py`: publish from multiple threads preserves entry order, `snapshot()` caps at the buffer size, and a full (slow) subscriber queue drops without blocking the publisher.
- [x] 1.2 Add `TeeStream` in `app/logbus.py`: `write(line)` forwards the line to the current `sys.stdout` (resolved lazily at write time) and, for rendered JSON entries, publishes the parsed entry to the bus; make the default stream of `setup_logging` in `app/log.py` this tee (an explicitly passed stream still bypasses the bus, as tests already do). Verify `uv run python -m pytest tests/test_logging_format.py tests/test_logging_lifecycle.py tests/test_logging_requests.py -q` still passes unchanged, plus a new unit test asserting a logged entry reaches both a captured stdout stream (via a test tee) and the bus.
- [x] 1.3 Cover the "Logging unaffected by the log viewer" scenarios: unit tests asserting a logged event appears on stdout exactly once as a single JSON line both with no subscribers and with a subscriber attached. Verify `uv run python -m pytest tests/test_log_viewer.py -q` passes (T-LOG-VIEWER-006, T-LOG-VIEWER-007).

## 2. SSE log stream endpoint

- [x] 2.1 Add `GET /api/logs` in `create_app()` (registered before the static mount): a `StreamingResponse` with `text/event-stream` that subscribes first, then replays `LogBus.snapshot()` oldest→newest, then streams live entries by polling the subscriber queue with a timeout in `asyncio.to_thread` (so a disconnect can cancel the in-flight poll), and unsubscribes in a `finally` block. Verify `uv run python -m pytest tests/test_log_viewer.py::test_live_event_delivered tests/test_log_viewer.py::test_history_replayed_on_connect tests/test_log_viewer.py::test_buffer_cap -q` passes (T-LOG-VIEWER-001, -004, -005).
- [x] 2.2 Cover the remaining endpoint scenarios: two concurrent clients both receive a logged event, and a transcript fetch succeeds normally while a stream client is connected (the endpoint never touches the fetch chain or its semaphore). Verify `uv run python -m pytest tests/test_log_viewer.py::test_multiple_clients_receive_event tests/test_log_viewer.py::test_log_stream_does_not_affect_fetch -q` passes (T-LOG-VIEWER-002, T-LOG-VIEWER-003).

## 3. Failure detail in log events

- [x] 3.1 In `app/chain.py`, add a `detail` field to the three failed `fetch_attempt` log calls: `detail=exc.message` in the `TranscriptError` branch, `detail=timeout_err.message` in the timeout branch (the constructed `UpstreamFailureError` — `asyncio.TimeoutError` has no `.message`), and `detail=generic.message` in the generic unexpected-exception branch. Verify `uv run python -m pytest tests/test_logging_fetch.py -q` passes, including the new tests asserting the timeout entry's `detail` contains the timeout message and a fetcher-raised entry's `detail` carries the error message (T-STRUCTURED-LOGGING-012, T-STRUCTURED-LOGGING-013).
- [x] 3.2 In `app/persist.py`, add `path=str(path)` and `detail=str(exc)` to the `transcript_save_failed` log call (keep `video_id` and `reason` unchanged). Verify `uv run python -m pytest tests/test_persistence.py -q` passes, including the new test asserting the failure entry carries the attempted `path` and the OS error string (T-STRUCTURED-LOGGING-014).

## 4. UI: log panel and toggle

- [x] 4.1 Add the panel markup and styles: a `#logs-toggle` button in the header area and a `#log-panel` `<pre>` at the bottom of the container (monospace, scrollable, bounded max-height), panel hidden by default, consistent with the existing visual language. Verify by running `uv run python -m app.main` and loading the page: no panel visible, toggle reads "Show logs".
- [x] 4.2 In `app/static/app.js`: open `EventSource("/api/logs")` once at page load; append each entry as one humanized line (formatter map for `server_started`, `server_stopped`, `http_request`, `fetch_attempt`, `fetch_rejected`, `transcript_saved`, `transcript_save_failed`, `unhandled_exception`; unknown events fall back to `event name + key=value` fields), all via `textContent`; trim oldest lines past a 200-line display cap; wire the toggle (hide/show + label swap). Verify by running the app: clicking the toggle shows/hides the panel, live server events appear as humanized lines, and a logged entry containing markup-like text renders as verbatim plain text.
- [x] 4.3 Add `tests/e2e/test_log_viewer.py` reusing the in-process uvicorn + stub-chain harness pattern from `tests/e2e/test_ui.py`, covering: panel hidden by default; show/hide toggle behavior; entries logged while hidden still appear on re-show; a stubbed failed fetch shows a line with video ID, source, error code, and cause detail; a failed save (point `TRANSCRIPT_DIR` at a path under an existing file so the write deterministically fails) shows a line with the target path and OS error; a synthetic in-process-logged unknown event renders via the key=value fallback; the panel grows in chronological order; the display cap drops the oldest lines; and markup-like field text is never rendered as HTML. Verify `uv run python -m pytest tests/e2e/test_log_viewer.py -q` passes (T-LOG-VIEWER-008 … T-LOG-VIEWER-017).

## 5. Integration verification

(Whole-change verification tasks — no individual requirement mapping; 5.4 cross-checks the Test Requirements of all requirements jointly.)

- [x] 5.1 Run the full non-e2e suite: `uv run python -m pytest tests/ -q --ignore=tests/e2e` — all green, no skips.
- [x] 5.2 Run the full e2e suite: `uv run python -m playwright install chromium` (if needed) then `uv run python -m pytest tests/e2e/ -q` — all green, including the pre-existing `test_ui.py` tests (the new toggle/panel must not break the existing UI flows).
- [x] 5.3 End-to-end smoke test: run `uv run python -m app.main`, open the UI, fetch a transcript with "Show logs" active, and confirm the panel shows the `http_request`, `fetch_attempt`, and `transcript_saved` lines while the server's stdout still emits one JSON object per line.
- [x] 5.4 Cross-check that every Test Requirement in the delta specs (T-LOG-VIEWER-001…017, T-STRUCTURED-LOGGING-012…014) maps to an existing, passing test at the stated file::test path.

## Workflow follow-up

- Archive the change with `/opsx-archive` after the project's review requirements are satisfied.
- Verify the archived result (specs merged into `openspec/specs/`).
