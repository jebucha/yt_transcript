# `app/fetchers.py` — caption-track fetchers

## Purpose

The two concrete ways to get a video's captions, plus the shared text
cleaner: `primary_fetch` via `youtube-transcript-api` (manual tracks
preferred, language fallback English → first available) and `fallback_fetch`
via `yt-dlp` used as a Python library (json3 subtitles, no download, no
ffmpeg). `fetch_video_title` performs the lightweight watch-page title lookup
the primary path needs to complete response metadata (yt-dlp provides the
title itself).

## Public surface

- `primary_fetch(video_id, requested_language="en") -> (text, language_code, title)`
- `fallback_fetch(video_id, requested_language="en") -> (text, language_code, title)`
- `fetch_video_title(video_id) -> str` — raises `UpstreamFailureError` on
  any fetch problem (the caller treats that as a transient failure).
- `clean_text(raw) -> str` — the shared output cleaner.
- Constants: `ATTEMPT_TIMEOUT` (30 s hard cap per attempt), `USER_AGENT`
  (browser-like, used on all outgoing YouTube requests).

## Invariants

- **Synchronous and blocking by design.** Both fetchers do blocking I/O and
  must be run in a worker thread with a hard timeout — `app/chain.py` does
  exactly this (`asyncio.to_thread` + `asyncio.wait_for`). Never call them
  from the event loop.
- **Every failure is a `TranscriptError` subclass.** No library exception
  type (youtube-transcript-api's, yt-dlp's, `requests`') ever escapes this
  module; each is mapped onto the taxonomy in `errors.py`.
- **Output cleaning is mandatory.** All fetched caption text passes through
  `clean_text`: HTML entities decoded, VTT headers/cue timings, bracketed
  timestamps, SSML tags, and any remaining HTML stripped, Unicode spaces
  normalized, one cue per line.
- **Primary picks manual before auto-generated, English before any other
  language.** `NoCaptionsError` when there are no tracks (or the cleaned
  text is empty).
- **Fallback uses a temp directory it removes**, json3 subtitle format,
  `skip_download`, `retries: 0`, the same 30 s socket timeout. An unreadable
  or non-json3 subtitle file is an *upstream data problem*
  (`UpstreamFailureError`), not a missing-captions case.
- **Error mapping is deliberately lossy in a safe direction**: primary maps
  unavailability-like exceptions to `VideoUnavailableError`, track-less
  videos to `NoCaptionsError`, and everything else (blocks, rate limits,
  token walls, request failures) to `UpstreamFailureError` so the chain can
  fall back. Fallback phrases its mapping on the downloaded error message.

## Log events emitted

None directly — the chain logs each attempt (`fetch_attempt`) and the fetchers
stay quiet. Failure `detail` strings shown in the log viewer originate from
the error messages built here and in the chain.

## Error codes raised/handled

Raises: `VideoUnavailableError` (404), `NoCaptionsError` (404),
`UpstreamFailureError` (502). Handles/maps: `YouTubeTranscriptApiException`
subtypes, `yt_dlp.utils.DownloadError`, `requests.RequestException`,
`OSError`/`json.JSONDecodeError` on the subtitle file.

## Design decisions

Resolved from `2026-10-29-youtube-transcript`:

- **D3** — `youtube-transcript-api` as the battle-tested keyless primary and
  `yt-dlp` *as a library* (no CLI subprocess, no process lifecycle, no
  ffmpeg for subtitle-only fetching) as the resilience fallback.
- **D4** — browser-like User-Agent on all outgoing YouTube requests and the
  hard 30 s per-attempt timeout.

Both libraries wrap unofficial YouTube endpoints; when YouTube breaks them
the recovery is the pinned-version update runbook in the README
(`uv add` with exact pins, rebuild, rerun) — the libraries, not this app,
own the repair loop.

## Cross-links

- [`chain.py`](chain.html) — the orchestrator that calls these with timeouts
- [`errors.py`](errors.html) — the taxonomy every failure maps onto
- [`__init__.py`](__init__.html) — the package layout these modules belong to
