# `app/main.py` — FastAPI application

## Purpose

The web layer: the app factory, HTTP middleware, all API endpoints, the
static-UI mount, and the `python -m app.main` entry point. It wires together
the fetch chain, persistence, library, providers, summarization, and logging
modules without containing their logic — endpoint bodies are thin dispatchers
that map module results onto JSON responses.

## Public surface

- `create_app() -> FastAPI` — builds the app (lifespan, middleware, routes).
- `app` — module-level instance; the ASGI object for `uvicorn app.main:app`.
- `main()` — the production entry point (Docker `CMD`): re-sets up logging,
  installs the exception hook, runs uvicorn with `limit_concurrency=100`.
- Request models: `TranscriptRequest` (`url`), `SummarizeRequest`
  (`text`, `name`, `provider`, `model`).
- Constants: `MAX_BODY_BYTES` (5 MiB, monkeypatchable in tests),
  `SUMMARIZE_MAX_CONCURRENCY` / `SUMMARIZE_EXECUTOR`, `LOG_POLL_TIMEOUT`,
  `_listen_port()`.
- Endpoints: `POST /api/transcript`, `GET /api/transcripts`,
  `GET /api/transcripts/{name}`, `GET /api/transcripts/{name}/summary`,
  `GET /api/providers`, `POST /api/summarize`, `GET /api/settings`,
  `POST /api/settings`, `GET /api/logs` (SSE), and the static UI mounted
  at `/`.

## Invariants

- **Import-time setup once.** `setup_logging()` runs at import so every entry
  point (uvicorn, `python -m app.main`, tests) emits the same JSON format;
  loggers are created lazily via `get_logger()`, so tests can reconfigure
  afterwards.
- **Middleware order is meaningful.** The body-size limit is added *before*
  the request-logging middleware (Starlette runs first-added outermost), so a
  413 rejection still produces an `http_request` log line. The body-size check
  reads only the `Content-Length` header — it fires before any body is read.
- **No blocking I/O on the event loop.** Every filesystem or network call is
  dispatched with `asyncio.to_thread`, *except* the summarization backend
  call, which runs on the dedicated 2-worker `SUMMARIZE_EXECUTOR`
  (`loop.run_in_executor` with `contextvars.copy_context().run`) so slow LLM
  calls never occupy the default executor shared by every other endpoint.
- **Read endpoints never touch the fetch chain or its semaphore.** Listing,
  reading transcripts/summaries, listing providers, reading/writing the
  settings, and streaming logs are all independent of in-flight fetches.
- **Provider config is read per request** (never at startup); the
  `GET /api/providers` response is secret-free — API keys and base URLs never
  leave the server.
- **Structural name reject (400 `INVALID_NAME`) is applied before any
  filesystem access** on every `{name}` route; a plain miss is a 404.
- **Static mount is registered last** so the API routes take precedence.
- **Persistence and summary saves are best-effort and post-response:**
  failures are logged, never returned to the client. The fetch response
  always carries the derived `name` (computed, not read back from disk).

## Log events emitted

`server_started` (info, with port), `server_stopped` (info),
`http_request` (info; error at 500 with a re-raise),
`unhandled_exception` (error, via the excepthook from `log.py`).

## Error codes raised/handled

Catches `TranscriptError` from the chain and summarize modules and maps each
to its `status`/`code`/`message` JSON envelope. Additionally returns
`413 BODY_TOO_LARGE` (body-size middleware), `400 INVALID_NAME`,
`400 INVALID_BODY` / `500 WRITE_FAILED` (`POST /api/settings`), and
`404 NOT_FOUND` (plain HTTP, not taxonomy entries). The settings body is
validated before any filesystem access: a non-object body or a
missing/non-boolean `autoSummarize` is rejected without touching the disk.

## Design decisions

Resolved from the archived change design docs:

- `2026-10-29-youtube-transcript` D2 (FastAPI as the web layer), D8
  (structlog JSON logging, request/lifecycle/unhandled-exception events).
- `2026-10-30-add-transcript-persistence` decisions 1, 4, 5 — the persistence
  hook sits in the endpoint after a successful fetch; the write is
  best-effort (logged, never raised); it runs in a worker thread with plain
  overwrite.
- `2026-11-02-add-saved-transcript-list` decision 3 (step 1) — the structural
  reject is the hard 400 rule applied before filesystem access.
- `add-transcript-summary` decisions 3 (config read per request), 4
  (displayed text is the source of truth), 5 (fetch response carries the
  derived `name`), 6 (best-effort summary save), 7 (secret-free provider
  listing), 8 (validation order on `POST /api/summarize`), 9 (no new locking;
  fetch chain untouched).
- `2026-11-03-add-log-viewer` decisions 2–4 — the SSE log stream over the
  in-memory bus (tee stream, subscribe-before-snapshot replay, bounded poll).
- `2026-11-05-bound-summarize-and-body-size` D1 (bounded summarize executor,
  including the runtime note on why `run_in_executor` instead of
  `to_thread(executor=...)`), D2 (`limit_concurrency=100` in `main()`), D3
  (5 MiB `Content-Length` cap as outermost middleware).
- `add-auto-summarize` D3 — `GET /api/settings` / `POST /api/settings` are
  thin wrappers over `app/settings.py` via `asyncio.to_thread`; the body is
  validated first, a write failure is `500 WRITE_FAILED`, and neither
  endpoint touches the fetch chain or the single-flight semaphore.

## Cross-links

- [`chain.py`](chain.html) — the fetch chain this module drives
- [`errors.py`](errors.html) — the error taxonomy it maps to HTTP
- [`persist.py`](persist.html) / [`library.py`](library.html) — write and read side of transcripts
- [`providers.py`](providers.html) / [`summarize.py`](summarize.html) — the summarization feature
- [`settings.py`](settings.html) — the `GET`/`POST /api/settings` persistence
- [`log.py`](log.html) / [`logbus.py`](logbus.html) — logging setup and the SSE source
- [`app/static/app.js`](static/app-js.html) — the UI that consumes these endpoints
