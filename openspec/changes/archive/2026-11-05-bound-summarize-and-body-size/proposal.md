# Proposal

## Why

The security audit (`security-audits/run-1/`) found two resource-exhaustion
vulnerabilities in the HTTP layer. Finding 1 (HIGH): `POST /api/summarize` has
no concurrency bound — each request pins a default-executor thread for up to
the 120 s LLM timeout, so ~16 concurrent requests freeze every other endpoint
and burn the operator's LLM quota indefinitely. Finding 2 (MEDIUM): there is no
request-body size limit — Starlette reads and parses the whole body before any
endpoint check, and the audit measured 3× memory amplification, so a single
large upload OOM-kills a small container (and compose restarts it, so it loops).

## What Changes

- Bound concurrent summarization backend calls to 2, using a dedicated bounded
  thread pool (separate from the default executor) so in-flight LLM calls can
  never starve the threads other endpoints share. Excess summarize requests
  wait for a free slot instead of being rejected.
- Set `limit_concurrency=100` on `uvicorn.run` in `main()` as app-wide
  connection backpressure (uvicorn rejects beyond that with 503).
- Reject requests whose `Content-Length` exceeds 5 MiB with 413 and error code
  `BODY_TOO_LARGE` in app middleware, before the body is read or parsed.

No changes to endpoint validation order, response shapes, or the UI.

## Capabilities

### New Capabilities

- `http-request-limits`: bounds on inbound HTTP traffic — the oversized-body
  rejection (413 `BODY_TOO_LARGE`) and the server connection-concurrency cap.

### Modified Capabilities

- `transcript-summarization`: the summarize endpoint gains a concurrency-bound
  requirement (bounded concurrent backend calls, queued excess, no shared-pool
  starvation); existing requirements are unchanged.

## Impact

- `app/main.py`: new module-level bounded executor for LLM calls;
  `summarize_endpoint` dispatches through it; new body-size middleware in
  `create_app()`; `main()` passes `limit_concurrency` to `uvicorn.run`.
- `tests/test_transcript_summarization.py`: new concurrency-bound tests.
- New `tests/test_http_request_limits.py`: body-size rejection tests.
- No dependency, API-shape, or data-format changes. Findings 3–8 of the audit
  are explicitly out of scope for this change.
