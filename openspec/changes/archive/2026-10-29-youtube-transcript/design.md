# Design

## Context

Greenfield project: no existing code, no specs, no infrastructure. The app runs as a single container on a Linux server under Docker or Podman, reachable over plain HTTP at `http://<server-ip>:8000`. Traffic is low-volume and personal. The server may sit on a residential or a datacenter IP, so the fetch chain must be resilient to YouTube rate-limiting in both cases. See proposal.md for motivation and scope.

YouTube exposes no official, keyless caption API: the only working approach is the unofficial one (parse the watch page's `ytInitialPlayerResponse`, fetch the timedtext caption endpoints). All libraries in this space are unofficial and break when YouTube changes its pages; the libraries, not us, own that repair loop.

## Goals / Non-Goals

**Goals:**
- One small, fast container (~150–160 MB image) serving the UI and the fetch endpoint from a single process
- Resilient caption fetching: primary library + automatic yt-dlp fallback
- Structured JSON logs on stdout that let an operator reconstruct any request end-to-end
- Zero operational state: no database, no volumes, no config files required to start

**Non-Goals:**
- Audio transcription (Whisper), video/audio download, ffmpeg
- Authentication, multi-user concerns, history/persistence of transcripts
- HTTPS termination, reverse proxy, docker-compose, orchestration
- Batch processing or playlist support
- Timestamped transcript variants (clean text only for now; a future flag can extend the response)

## Decisions

### D1: Python 3.13 over JavaScript
The transcript ecosystem is Python-first: `youtube-transcript-api` is the most battle-tested keyless fetcher (8.5k stars, active releases), and `yt-dlp` (199k stars, near-daily fixes for YouTube's anti-bot changes) is a first-class Python library — giving a real two-stage fallback. The Node options are forks of the same unofficial technique with thinner maintenance and no strong fallback. The web UI is static files, so the server language costs nothing on the frontend.
- **Alternative considered:** Node 22 + `youtube-transcript-plus`. Viable for the primary path only; rejected on fallback strength.

### D2: FastAPI as the web layer
Minimal ASGI server that natively serves JSON endpoints and static files, is async (needed so the semaphore-based fetch bound and timeouts behave), and has a small, pure-Python dependency tree (keeps the slim image slim).
- **Alternative considered:** Flask (sync, would need thread handling for the bound) or raw `http.server` (too much hand-rolled routing/JSON). Both inferior for little or no size gain.

### D3: Fetch chain — `youtube-transcript-api` primary, `yt-dlp` fallback, in-process
One attempt on the primary library; on any upstream failure (429, IP block, malformed response, track-fetch error) one attempt via `yt-dlp` used as a Python library (`YoutubeDL` with `skip_download`, writing subtitles to a temp dir, `json3` format) — no CLI subprocess, so no process lifecycle to manage. Subtitle-only fetching needs no ffmpeg. The response reports which source produced the text so the log and UI can show it.
- **Alternative considered:** `yt-dlp` as a CLI subprocess — rejected: slower, more fragile (parsing, temp files), and the library API is well documented.
- **Alternative considered:** yt-dlp primary — rejected: it is heavier and slower for the common case where the lighter primary works.

### D4: Fetch hygiene for hostile (datacenter) IPs
Browser-like User-Agent on all outgoing YouTube requests, a hard timeout per attempt (30 s), and a global `asyncio.Semaphore(1)` so at most one fetch chain hits YouTube at a time; excess concurrent requests get 503 `BUSY` immediately. This keeps our footprint tiny from either kind of IP.

### D5: Container image — `python:3.13-slim`, single stage, non-root
The app has no build step (no TS compile, no native wheels), so multi-stage adds nothing: one stage installs pinned deps from `requirements.txt` (`pip install --no-cache-dir`), copies code, runs as the unprivileged `app` user, and exposes port 8000. Expected final size ~150–160 MB (measured with the pinned dep set: 169 MB amd64 / 194 MB arm64 — the base image alone is ~125–148 MB, so the estimate is a floor-boundary, not a hard target).
- **Alternative considered:** `python:3.13-alpine` (~56 MB base) — rejected: musl risk for no real benefit at this size.
- **Alternative considered:** distroless — rejected: no shell makes debugging a personal tool miserable; saves little over slim.

### D6: Frontend — one static page, no build step
`index.html` + `app.js` + `style.css`, served by FastAPI's `StaticFiles`. No framework, no bundler, no CDN. Copy button logic: try `navigator.clipboard.writeText`, catch and fall back to hidden-textarea + `execCommand("copy")` — required because plain HTTP (our normal access path) is a non-secure context where the Clipboard API does not exist. Error banner maps server error codes to human messages. All fetched content (transcript text, video title) is inserted as text (e.g., `textContent`), never as HTML, so markup-like content from YouTube cannot be rendered or executed (XSS).

### D7: API shape
Single endpoint `POST /api/transcript` with body `{"url": "..."}`.
- 200: `{"text", "video_id", "title", "language", "source": "primary"|"fallback"}`
- Errors: `{"error": {"code", "message"}}` with `INVALID_URL`/400, `VIDEO_UNAVAILABLE`/404, `NO_CAPTIONS`/404, `UPSTREAM_FAILURE`/502, `BUSY`/503.
The error taxonomy is fixed in the spec; messages are stable enough for the UI to map them.

### D8: Logging — structlog JSON to stdout
`structlog` (tiny, pure Python) configured for one JSON object per line with `timestamp` (ISO-8601, UTC), `level`, and an `event`. A request-middleware-style hook logs every HTTP call (method, path, status, ms). The fetcher logs one entry per attempt (video_id, language, source, outcome/reason, ms, char count on success) — the failed primary and the successful fallback are separate lines. Lifecycle events on start (with port) and shutdown; a top-level handler turns unhandled exceptions into an error event. No file handlers, no third log fields containing headers or credentials.
- **Alternative considered:** stdlib `logging` with a custom JSON formatter — workable; structlog gives context binding with less boilerplate for ~0 size cost.

### D9: Deployment shape
Plain `Dockerfile` (podman-compatible) + a documented one-liner: `docker run -d --name yt-transcript --restart unless-stopped -p 8000:8000 yt-transcript`. No compose file: with one container and zero persistent state, compose would only restate the run flags. Revisit if a second container (e.g., an HTTPS reverse proxy) or a volume (e.g., a cookies file) is ever added.

## Risks / Trade-offs

- [YouTube changes its internal API and the primary library breaks] → yt-dlp fallback covers most breakage; pinned versions + a README "update runbook" (`pip install -U youtube-transcript-api yt-dlp`, rebuild, rerun) keeps recovery to minutes.
- [Datacenter IP throttling (429 / bot check)] → single-flight concurrency, browser UA, timeouts, and the fallback chain; if the server IP is fully blocked, no in-container fix exists — the honest escalation path is running on a residential IP or a proxy (out of scope, documented).
- [Clipboard API absent over plain HTTP] → legacy fallback is spec'd, not optional; both paths share the same confirmation UI.
- [`yt-dlp` as a library pulls a non-trivial dep tree] → accepted: still a few MB inside a slim image, and it is the resilience we are buying.
- [Single-flight means a second user sees 503 `BUSY`] → correct for a personal tool; the UI can simply say "try again in a moment". If multi-user ever matters, the semaphore value is a one-line change.
- [Unofficial-API terms-of-service grey area] → low-volume personal use of existing public captions; noted, no mitigation at this scale.

## Migration Plan

First deployment is a normal install: `docker build -t yt-transcript .`, then the documented run one-liner, then a smoke test with a known public video (fetch + copy) and one negative test (bad URL, caption-less video). Rollback is stopping/removing the container — the app is stateless.

## Open Questions

None. (Residential vs datacenter server IP is unknown, but D3/D4 make the design correct for both.)

## Test Strategy

- **Runner:** `pytest` (installed from `requirements-dev.txt`, task 1.2)
- **Unit / API suite:** `python -m pytest tests/ -q` from the project root. Unit and API tests mock `youtube-transcript-api` and `yt-dlp`; no real YouTube traffic in the suite.
- **E2E suite (dev-only):** `python -m pytest tests/e2e/ -q` — Playwright driving the real page in headless Chromium against a locally started uvicorn instance with the upstream fetch stubbed for determinism. Playwright lives in `requirements-dev.txt` only and never enters the container image; one-time browser setup `python -m playwright install chromium` (task 5.5).
- **Naming:** unit test files `tests/test_<area>.py`, e2e tests `tests/e2e/test_ui.py`; test functions `test_<snake_case>`. Test Requirement IDs: `T-<CAPABILITY-UPPERCASE>-<NNN>`.
- **Prerequisites:**
  - `cmd: python --version` (Python 3.13)
  - `file: requirements.txt`
  - `cmd: python -m pytest --version`
  - e2e only: `cmd: python -m playwright --version`
