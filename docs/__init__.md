# `app/__init__.py` — the `app` package

## Purpose

The `app` package is the entire FastAPI application: the web layer, the
YouTube fetch chain, persistence, summarization, and structured logging. The
`__init__.py` file is **deliberately empty** — it exists only to mark the
directory as a package. It imports nothing and performs no work, so importing
`app` (or any submodule) never triggers package-level side effects.

The side effects people associate with "importing the app" actually live in
`app/main.py`, which at import time (1) configures JSON-to-stdout logging once
via `applog.setup_logging()` and (2) builds the module-level `app = create_app()`
instance (which installs the unhandled-exception hook). Entry points:
`uvicorn app.main:app` and `python -m app.main` (the Docker `CMD`).

## Public surface

Nothing is exported from the package. Consumers import submodules directly
(`from app import chain as chain_mod`, `from app.persist import derive_file_name`).
The package's effective API is the set of modules below plus the ASGI app
object `app.main.app`.

## Invariants

- **`__init__.py` must stay empty.** No imports, no re-exports, no setup —
  the side effects belong to `app/main.py` where they are deliberate and
  documented.
- **Backend modules stay FastAPI-free.** `persist.py`, `library.py`,
  `providers.py`, and `summarize.py` must not import FastAPI, so they remain
  testable directly against `tmp_path` without an app instance.
- **No blocking I/O on the event loop.** All filesystem and network work
  dispatches to worker threads (`asyncio.to_thread`, or the dedicated
  summarize executor); only `app/main.py` orchestrates this.
- **The single-flight semaphore governs only the YouTube fetch chain**
  (`app/chain.py`); read endpoints and summarization must never touch it.

## Module inventory

| Module | Role |
| --- | --- |
| [`main.py`](main.html) | app factory, middleware, API endpoints, uvicorn entry point |
| [`chain.py`](chain.html) | fetch-chain orchestration (primary → fallback, single-flight) |
| [`fetchers.py`](fetchers.html) | caption-track fetchers (primary + fallback) and text cleaning |
| [`urls.py`](urls.html) | YouTube URL/ID parsing (pure, no network) |
| [`errors.py`](errors.html) | error taxonomy (code + HTTP status + message) |
| [`persist.py`](persist.html) | title-to-file-name derivation + best-effort transcript writer |
| [`library.py`](library.html) | read side of saved transcripts (list + read) |
| [`providers.py`](providers.html) | summarization provider config (read per request) |
| [`summarize.py`](summarize.html) | provider invocation + summary file save/read |
| [`log.py`](log.html) | structlog JSON-to-stdout setup |
| [`logbus.py`](logbus.html) | in-memory ring buffer backing the SSE log viewer |
| [`static/`](static/app-js.html) | `app.js`, `index.html`, `style.css` — the no-build-step UI |

## Log events emitted

None — this file emits nothing (it has no code). See the individual module
pages for the events each emits.

## Error codes

None — this file raises and handles nothing. The taxonomy lives in
[`errors.py`](errors.html).

## Design decisions

The package layout is the accumulation of per-change decisions; the
conventions that bind all modules come from the change that first wrote a
backend module — `2026-10-30-add-transcript-persistence`, design decision 2
(a new module, pure, with **no FastAPI imports** so it is testable against
`tmp_path`). Archived design docs live under `openspec/changes/archive/`;
this page cites them by name so every link in the docs set stays inside
`docs/`. AGENTS.md now codifies the package-wide invariants: uv-managed
environment, no blocking I/O on the event loop, single-flight semaphore
scoped to the fetch chain only.

## Cross-links

- [`main.py`](main.html) — where the package's import-time side effects live
- [`errors.py`](errors.html) — the shared error taxonomy
- [`log.py`](log.html) / [`logbus.py`](logbus.html) — the shared logging stack
