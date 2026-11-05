# Design

## Context

See proposal.md for motivation. The implementation facts that shape the
approach:

- `POST /api/summarize` dispatches its backend call with
  `asyncio.to_thread(summarize_mod.summarize_with_provider, ...)`
  (`app/main.py:239-242`) into the loop's **default** `ThreadPoolExecutor`
  (`min(32, cpu+4)` workers), where every other endpoint's blocking work
  (file reads/writes, provider config loads, the fetch chain) runs. Each LLM
  call pins a worker for up to `DEFAULT_SUMMARY_TIMEOUT = 120 s`
  (`app/summarize.py:42`).
- `main()` runs a bare `uvicorn.run(app, host=..., port=..., log_level="warning")`
  (`app/main.py:299`); the Docker image's `CMD` is `python -m app.main`, so this
  call is the production entry point.
- `create_app()` has one piece of HTTP middleware (request logging,
  `app/main.py:84-107`). Starlette applies the first-added HTTP middleware as
  the outermost layer. There is no body-size cap anywhere in the stack (the
  only in-stack limit is h11's 16 KB *header* limit); the app's 100k-char text
  check (`app/main.py:229`) runs only after the body is fully read and parsed.
- Tests build a fresh `create_app()` per test and drive it through
  `TestClient` (each context opens its own event loop/portal), per
  `tests/test_transcript_summarization.py`.
- `requires-python >= 3.13` (`pyproject.toml`); AGENTS.md mandates `uv run` for
  all Python and `asyncio.to_thread` for blocking work.

## Goals / Non-Goals

**Goals:**
- Cap concurrent summarization backend calls at 2 without ever letting LLM
  calls occupy the shared default thread pool.
- Reject oversized request bodies (413) before the body is read or parsed.
- Add app-wide connection backpressure at the server entry point.

**Non-Goals:**
- Audit findings 3–8 (summary forgery, SSE thread pinning, symlink follow,
  title collision, prompt injection, LAN-IP leak) — separate changes.
- Authentication, per-client rate limiting, or request quotas.
- Capping *chunked* (no `Content-Length`) bodies — see Risks.
- Changes to endpoint validation order, error codes, response shapes, or the UI.

## Decisions

### D1: Bound the summarize backend call with a dedicated bounded executor, not a semaphore

The audit's literal suggestion was a module-level `asyncio.Semaphore(2)`
around the `to_thread` call; it itself notes "a dedicated executor … is the
stronger variant". We implement the executor. This requires one change:
the new constants and endpoint wiring in `app/main.py`.

```python
# app/main.py, module level
SUMMARIZE_MAX_CONCURRENCY = 2
SUMMARIZE_EXECUTOR = ThreadPoolExecutor(
    max_workers=SUMMARIZE_MAX_CONCURRENCY, thread_name_prefix="summarize"
)

# summarize_endpoint (in create_app), replacing the plain to_thread dispatch
summary = await asyncio.get_running_loop().run_in_executor(
    SUMMARIZE_EXECUTOR, contextvars.copy_context().run,
    summarize_mod.summarize_with_provider,
    provider, request.model, request.text,
)
```

**Runtime note (why `run_in_executor` instead of `to_thread(executor=...)`).**
The project's interpreter (uv-managed CPython 3.13.18) ships a modified
`asyncio.to_thread` with **no `executor` parameter**: it forwards any
`executor=` kwarg to the callable and always runs the work on the loop's
default executor. The original plan — passing `executor=SUMMARIZE_EXECUTOR`
through `asyncio.to_thread(...)` (consumed by a keyword-only `executor`
parameter added to `summarize_with_provider`) — was therefore verified to
leave the bound silently unenforced (4 concurrent requests ran 4-deep on the
default pool). `loop.run_in_executor(SUMMARIZE_EXECUTOR, ...)` is exactly
what `to_thread` does internally (context copy + `run_in_executor`), just
pointed at the bounded pool instead of the default; the explicit
`contextvars.copy_context().run` preserves `to_thread`'s context propagation
(`app/log.py` merges contextvars into log entries).
`summarize_with_provider`'s signature is therefore unchanged, and
`_call_chat_completions()` still runs synchronously inside that single worker
thread via `requests.post()`.

Rationale over the semaphore:
- **Fixes the actual failure mode directly.** The audit's failure is
  *shared-pool starvation*: LLM calls pin default-executor workers and every
  other endpoint queues behind them. A semaphore still leaves up to 2 slow LLM
  calls occupying the shared pool (120 s each); a dedicated pool removes LLM
  work from the shared pool entirely, on hosts of any core count.
- **No event-loop binding hazard.** `asyncio.Semaphore` binds to the event
  loop on first acquire and raises `RuntimeError` if later used from a
  different loop. Tests use a fresh `TestClient` (fresh loop) per test, so a
  module-level semaphore would break across tests; a per-app semaphore would
  need wiring in `create_app()`. A `ThreadPoolExecutor` is loop-independent.
- **Queuing for free.** The 2-worker pool *is* the bound: the 3rd+ validated
  request waits in the executor's work queue instead of being rejected, which
  is the spec'd behavior. Submitting via `loop.run_in_executor(...)` keeps
  the blocking work off the event loop, as the AGENTS.md `to_thread`
  convention requires.

The endpoint's local validation order (design decision 8 in the code comments)
is unchanged — the executor wraps only the backend call, after all
backend-free rejections.

### D2: Connection cap via `limit_concurrency=100` in `main()`

```python
uvicorn.run(app, host=host, port=_listen_port(),
            log_level="warning", limit_concurrency=100)
```

100 is far above legitimate usage (single operator UI, a handful of log
stream subscribers) and far below what would exhaust file descriptors or
memory; beyond it, uvicorn itself rejects new connections with 503, so no app
code is involved. Placed in `main()` because the Docker image's `CMD` is
`python -m app.main` — the documented production entry point. (Direct
`uvicorn app.main:app` invocations bypass this; see Risks.)

### D3: Body-size cap as a `Content-Length` check in middleware

```python
# app/main.py, module level
MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MiB

# in create_app(), added BEFORE the logging middleware (outermost),
# so rejections are covered by the http_request log line
@app.middleware("http")
async def limit_body_size(request, call_next):
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={
            "error": {"code": "BODY_TOO_LARGE",
                      "message": "Request body too large."}})
    return await call_next(request)
```

- **5 MiB rationale:** the app's real payload ceiling is the 100,000-char text
  cap; worst-case UTF-8 (4 bytes/char) plus JSON structure is under 1 MB, so
  5 MiB has >5× headroom while a 5 MiB body — ~15 MB peak per the audit's
  measured 3× amplification — cannot threaten a 1 GB container.
- **Header check only, checked before anything reads the body.** This is
  zero-overhead and fires before Starlette's full-body `b"".join` + JSON parse,
  which is where the memory spike occurs. It applies to every route (only the
  two JSON POSTs carry bodies; static/GET routes are untouched in practice).
- **Error shape** follows the app's existing `{"error": {code, message}}`
  envelope; 413 is the standard status for oversized bodies.
- `MAX_BODY_BYTES` is a module-level constant read at request time so tests can
  monkeypatch it (matching how the codebase already tests env-driven config).
- Alternative considered: capping uvicorn itself. Uvicicorn has no body-size
  option (h11 caps headers only), and a reverse-proxy cap is deployment
  configuration, not code. Rejected.

### D4: Tests

- `tests/test_transcript_summarization.py`:
  - `test_summarize_backend_concurrency_bounded` — monkeypatch
    `summarize_with_provider` with a stub that tracks peak concurrent
    invocations (counter + short sleep); fire 4 concurrent requests; assert
    peak ≤ 2 and all responses 200.
  - `test_summarize_does_not_starve_other_endpoints` — stub the backend with a
    ~1 s delay, keep 2 calls in flight (both bounded slots busy), and assert a
    concurrent `GET /api/transcripts` returns promptly.
- `tests/test_http_request_limits.py` (new file):
  - `test_oversized_body_rejected_with_413` — assert `MAX_BODY_BYTES` is 5 MiB,
    then monkeypatch it small and send an over-limit body; assert 413,
    `BODY_TOO_LARGE`, and that the endpoint stub was never invoked.
  - `test_body_under_limit_processed_normally` — a valid small request reaches
    the endpoint and is handled as usual.
  - `test_entry_point_sets_connection_limit` — monkeypatch `uvicorn.run`, call
    `main()`, assert `limit_concurrency=100` was passed.

All test commands run through `uv run` per AGENTS.md.

## Test Strategy

Tests use a fresh `create_app()` per test and drive it through FastAPI's
`TestClient`, which opens its own event loop/portal (see existing pattern in
`tests/test_transcript_summarization.py`). All commands below are executed from
the repository root via `uv run`.

| Scenario | Test file | Runner command |
|----------|-----------|----------------|
| Excess concurrent summarize requests queued, peak ≤ 2 | `tests/test_transcript_summarization.py` | `python -m pytest tests/test_transcript_summarization.py::test_summarize_backend_concurrency_bounded -q` |
| Other endpoints responsive while summarize in flight | `tests/test_transcript_summarization.py` | `python -m pytest tests/test_transcript_summarization.py::test_summarize_does_not_starve_other_endpoints -q` |
| Oversized body rejected with 413 + BODY_TOO_LARGE | `tests/test_http_request_limits.py` | `python -m pytest tests/test_http_request_limits.py::test_oversized_body_rejected_with_413 -q` |
| Valid body processed normally, empty body unaffected | `tests/test_http_request_limits.py` | `python -m pytest tests/test_http_request_limits.py::test_body_under_limit_processed_normally -q` |
| Entry point passes limit_concurrency=100 to uvicorn | `tests/test_http_request_limits.py` | `python -m pytest tests/test_http_request_limits.py::test_entry_point_sets_connection_limit -q` |

The full non-e2e suite (`uv run python -m pytest tests/ -q --ignore=tests/e2e`)
and the e2e suite (`uv run python -m pytest tests/e2e/ -q`) are also run to
confirm no regressions. A manual smoke test with curl confirms 413 rejection
for >5 MiB bodies and normal operation for valid requests.

## Risks / Trade-offs

- [Chunked bodies (no `Content-Length`) bypass the cap] → Accepted limitation:
  the middleware can only see a declared length without consuming the stream
  (which would interfere with the endpoint's own read). The threat-model
  clients — `curl --data-binary`, browsers, the app's own UI — all send
  `Content-Length`. A streamed body cap or proxy limit is future hardening,
  not required for the audit's reproduced attack.
- [Queued summarize requests can wait up to 2 × summary timeout (~4 min worst
  case) behind slow LLM calls] → The UI disables the Summarize button while a
  request is in flight, so organic users rarely queue; rejecting instead
  (429) was considered and rejected as it adds a new error code/UX for a rare
  case and the audit's fix also queues.
- [Interpreters with a slow LLM call in flight may take up to one call's
  duration longer to exit, since executor threads run to completion] → Existing
  behavior already had this property via the default pool; uvicorn's graceful
  shutdown already waits for in-flight requests. No mitigation needed.
- [`uvicorn app.main:app` (non-`main()` entry) skips the connection cap] →
  `python -m app.main` is the documented and Docker image entry point; noted
  in the runbook rather than duplicated configuration.
- [5 MiB is a fixed constant, not configurable] → Consistent with the existing
  `MAX_INPUT_CHARS` ceiling; if an operator ever needs more, it is a one-line
  follow-up.

## Migration Plan

Single self-contained release: no data, format, or API-contract changes
(413 is a new response only for requests that previously crashed/OOM'd the
process). Rollback is reverting the commit. Per AGENTS.md, bump the minor
version (`uv version --bump minor`) at archive time since this ships
user-visible behavior.

## Open Questions

None.
