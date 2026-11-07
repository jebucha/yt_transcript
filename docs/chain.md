# `app/chain.py` — fetch chain orchestration

## Purpose

Coordinates one transcript fetch: parse the URL, try the primary fetcher once,
and on a transient upstream failure (`UPSTREAM_FAILURE`) try the fallback
fetcher exactly once. A global single-flight semaphore guarantees at most one
chain hits YouTube at a time; concurrent callers are rejected immediately
with `BusyError` (HTTP 503) rather than queued. Every attempt — success or
failure — is logged as exactly one structured `fetch_attempt` entry.

## Public surface

- `FetchChain` — the orchestrator; `run(url) -> FetchResult`.
- `FetchResult` — frozen dataclass: `text`, `video_id`, `title`, `language`,
  `source` (`"primary"` | `"fallback"`).
- `default_chain` — the module-level chain used by the HTTP API
  (patchable in tests).
- `REQUESTED_LANGUAGE` — `"en"`; the language requested from the fetchers.

## Invariants

- **Single-flight, reject-don't-queue.** If the semaphore is already locked,
  the caller is rejected immediately (`BusyError`, a `fetch_rejected`
  warning log) — the chain never makes a second user wait behind the first.
- **The semaphore governs only the YouTube fetch chain.** No other code —
  read endpoints, summarization, log streaming — may acquire it.
- **Parse before acquiring.** `parse_video_ref` is pure (no network) and runs
  before the semaphore, so an invalid URL never consumes the fetch slot.
- **Exactly one fallback attempt, only for transient codes.** Fallback runs
  only when the primary's error code is in `FALLBACK_CODES`
  (`{"UPSTREAM_FAILURE"}`); `VIDEO_UNAVAILABLE`/`NO_CAPTIONS` re-raise
  straight through.
- **The semaphore is always released** (`finally`), even on failure.
- **Every attempt is logged once**, with video id, requested language, source,
  outcome (+ failure `reason` and `detail`), duration in ms, and — on success
  — the transcript character count.
- **Hard timeout per attempt.** Each fetcher call runs in a worker thread
  (`asyncio.to_thread`) under `asyncio.wait_for` with `ATTEMPT_TIMEOUT`
  (30 s); a timeout is re-raised as `UpstreamFailureError` and *can* trigger
  the fallback. Any other unexpected exception is likewise wrapped into
  `UpstreamFailureError` (defensive: anything unexpected is upstream).

## Log events emitted

- `fetch_attempt` — info on success (`outcome=success`, `chars`), error on
  failure (`outcome=failure`, `reason`, `detail`).
- `fetch_rejected` — warning when a concurrent caller is rejected as busy.

## Error codes raised/handled

Raises: `InvalidUrlError` (from `urls.py`, pre-semaphore), `BusyError`
(503, when the slot is held), `UpstreamFailureError` (502, on timeout,
unexpected exception, or final fetcher failure). Re-raises without fallback:
`VideoUnavailableError`, `NoCaptionsError`.

## Design decisions

Resolved from `2026-10-29-youtube-transcript`:

- **D3** — fetch chain: `youtube-transcript-api` primary, `yt-dlp` fallback,
  in-process (the library API, not a CLI subprocess); the response reports
  which source produced the text.
- **D4** — fetch hygiene for hostile IPs: browser-like User-Agent, hard 30 s
  timeout per attempt, global `asyncio.Semaphore(1)` with immediate
  503 `BUSY` for excess concurrent requests, keeping the footprint tiny.

The `fetch_attempt` log schema (video id, language, source, outcome/reason,
duration, char count) comes from the same change's **D8** (logging); the
failure `detail` field was added by `2026-11-03-add-log-viewer` decision 5.

## Cross-links

- [`fetchers.py`](fetchers.html) — the two fetchers the chain dispatches to
- [`urls.py`](urls.html) — the pure parse step that runs first
- [`errors.py`](errors.html) — the taxonomy and `FALLBACK_CODES`
- [`main.py`](main.html) — the endpoint that drives `default_chain`
