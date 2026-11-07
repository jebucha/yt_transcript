# `app/errors.py` — error taxonomy

## Purpose

The single error taxonomy for transcript retrieval and summarization. Every
failure the app can meaningfully report is a `TranscriptError` subclass
carrying a machine-readable `code`, an HTTP `status`, and a stable
human-readable `message` the UI can display. Endpoints catch `TranscriptError`
and map it to the JSON envelope `{"error": {"code", "message"}}`.

## Public surface

`TranscriptError` (base) and its subclasses:

| Exception | Code | HTTP | Meaning |
| --- | --- | --- | --- |
| `InvalidUrlError` | `INVALID_URL` | 400 | not a recognizable YouTube URL/ID |
| `VideoUnavailableError` | `VIDEO_UNAVAILABLE` | 404 | private, deleted, region-locked, age-restricted |
| `NoCaptionsError` | `NO_CAPTIONS` | 404 | no caption tracks (or nothing left after cleaning) |
| `UpstreamFailureError` | `UPSTREAM_FAILURE` | 502 | transient YouTube problem; try again later |
| `BusyError` | `BUSY` | 503 | the single-flight slot is held by another fetch |
| `SummaryNotConfiguredError` | `NOT_CONFIGURED` | 503 | no usable providers in the config |
| `InvalidProviderError` | `INVALID_PROVIDER` | 400 | provider/model no longer in the config |
| `ProviderError` | `PROVIDER_ERROR` | 502 | the summarization backend failed |
| `InputTooLongError` | `INPUT_TOO_LONG` | 400 | transcript over the 100,000-character cap |

Plus `FALLBACK_CODES` — the frozenset of codes for which the chain makes a
fallback attempt: exactly `{"UPSTREAM_FAILURE"}`.

## Invariants

- **One base class, class-level identity.** `code` and `status` are class
  attributes; instances carry only the message (default message when none is
  passed). Adding a new failure mode means a new subclass here, not an ad-hoc
  status.
- **`FALLBACK_CODES` is transient-problems-only.** Unavailability and
  missing-captions errors re-raise straight through the chain; only
  `UPSTREAM_FAILURE` triggers the one fallback attempt.
- **Messages are stable UI contract.** The UI keeps its own `ERROR_MESSAGES`
  map by code and prefers it over the server message; the server message is
  the fallback. Wording changes ripple into the UI, so treat it as an API.
- **Not everything is a `TranscriptError`.** The saved-transcript read
  endpoints' `INVALID_NAME` (400) and `NOT_FOUND` (404) — and the body-size
  middleware's `BODY_TOO_LARGE` (413) — are plain HTTP statuses returned
  directly by `main.py`, deliberately outside this taxonomy.

## Log events emitted

None — errors are log payloads (e.g. `fetch_attempt` with `reason=<code>`),
not log emitters.

## Error codes raised/handled

All of the table above are defined here and raised by the fetch/summarize
modules; `main.py` is the sole place they are translated to HTTP responses.

## Design decisions

Resolved from the archived change design docs:

- `2026-10-29-youtube-transcript` **D7** (API shape) — the original five
  fetch errors with their fixed codes and statuses, and the
  `{"error": {"code", "message"}}` envelope.
- `add-transcript-summary` **decision 2** — the four summarization errors
  (`NOT_CONFIGURED` 503, `INVALID_PROVIDER` 400, `PROVIDER_ERROR` 502,
  `INPUT_TOO_LONG` 400) added as subclasses, while structurally invalid
  names keep the read side's plain-HTTP 400 `INVALID_NAME`.

## Cross-links

- [`chain.py`](chain.html) — where `FALLBACK_CODES` and `BusyError` matter
- [`fetchers.py`](fetchers.html) — the primary mappers of library exceptions
- [`summarize.py`](summarize.html) — the provider-side failures
- [`main.py`](main.html) — the only place errors become HTTP responses
