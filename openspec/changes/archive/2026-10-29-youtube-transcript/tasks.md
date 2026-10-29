# Tasks

## 1. Project scaffolding

> Note: 1.1–1.2 implement proposal-level items (project layout, pinned dependencies) and intentionally map to no capability spec requirement.

- [x] 1.1 Create the project layout (`app/` Python package, `app/static/` for the frontend, `tests/`) and verify the expected directories and a minimal importable `app` package exist
- [x] 1.2 Add a pinned `requirements.txt` (fastapi, uvicorn, structlog, youtube-transcript-api, yt-dlp) and a `requirements-dev.txt` (pytest) and verify a clean install succeeds (`pip install -r requirements.txt -r requirements-dev.txt` in a fresh venv)

## 2. Structured logging foundation

- [x] 2.1 Configure structlog for one JSON object per line on stdout (ISO-8601 timestamp, level, event) and add startup (with listen port), shutdown, and unhandled-exception log events; verify by starting the server and checking the stdout startup line parses as JSON containing the port, and by raising a simulated unhandled exception and checking an error-level JSON line appears
- [x] 2.2 Add HTTP request logging (method, path, status, duration ms) for every incoming request; verify by making a few requests to a stub route and checking each produces one JSON line with all four fields, and that no line contains raw request headers

## 3. Transcript fetch chain

- [x] 3.1 Implement YouTube reference parsing/normalization (watch URL, `youtu.be` short link, bare video ID) returning the video ID, with `INVALID_URL` raised for anything else without any network call; verify with unit tests covering all three accepted forms plus non-YouTube and empty input asserting no fetcher is invoked
- [x] 3.2 Implement the primary fetcher over `youtube-transcript-api` (prefer manual over auto-generated tracks, language fallback English → first available, strip timestamps/VTT/SSML/HTML entities, 30 s timeout, browser-like User-Agent); verify with unit tests (library mocked) covering manual-preferred, auto-only, non-English fallback reporting the actual language, and output containing no timestamp markers or markup
- [x] 3.3 Implement the fallback fetcher using `yt-dlp` as a Python library (`skip_download`, `json3` subtitle format, temp output dir, no ffmpeg) producing the same clean text; verify with a unit test (yt-dlp mocked) mapping a `json3` payload to clean transcript text
- [x] 3.4 Implement the fetch chain orchestration: one primary attempt, one fallback attempt on upstream failure, `source` reported as primary/fallback, and a global single-flight semaphore returning `BUSY` when a chain is already in flight; verify with unit tests covering primary success, primary failure → fallback success (source = fallback), both failing → `UPSTREAM_FAILURE`, and a second concurrent request → `BUSY`
- [x] 3.5 Map every failure to the spec error taxonomy (`INVALID_URL` 400, `VIDEO_UNAVAILABLE` 404, `NO_CAPTIONS` 404, `UPSTREAM_FAILURE` 502, `BUSY` 503) with human-readable messages; verify with unit tests asserting code + message for each taxonomy entry, including private video and no-captions inputs
- [x] 3.6 Log one structured entry per fetch attempt (video ID, requested language, fetcher source, outcome with failure reason, duration, character count on success) so a fallback chain yields two entries; verify with a unit test (captured log output) asserting the failed-primary + successful-fallback pair and that no entry contains headers or credentials

## 4. HTTP API

- [x] 4.1 Implement `POST /api/transcript` accepting `{"url": "..."}` and returning the exact success shape (`text`, `video_id`, `title`, `language`, `source`) and error shape (`error.code`, `error.message`) per the design; verify with API tests (fetch chain mocked) asserting the 200 body fields and each error code/status pair end to end
- [x] 4.2 Serve the static frontend from the root path via FastAPI static files; verify `GET /` returns 200 with the index page content type using a placeholder page at this stage

## 5. Web interface

- [x] 5.1 Build the single static page (`index.html` + `style.css`): URL input, fetch button with loading indicator, error region, scrollable transcript panel, copy button; verify in a browser that all regions render and that the page references no external network resources
- [x] 5.2 Implement the request flow in `app.js`: fetch on button click and on Enter in the input, button disabled plus visible loading indicator in flight, re-enabled on response, and no request sent for empty input; verify manually against a running local server, confirming the disabled/loading states and that an empty input triggers no network request
- [x] 5.3 Implement result display (transcript text, video title, language) and the copy button: `navigator.clipboard.writeText` with a hidden-textarea + `execCommand("copy")` fallback, "Copied!" confirmation after success, and the button disabled until a transcript is shown; verify by copying in both a secure context (localhost) and a non-secure one (`http://<non-localhost-ip>:8000`) and confirming the full transcript is on the clipboard in both cases (e.g., paste into a text field / `pbpaste`)
- [x] 5.4 Implement the error banner mapping all five error codes to human-readable messages (upstream failure suggesting retry later), keeping the input editable and the fetch button re-enabled; verify by triggering each error (bad URL, a no-caption video, a private video, two simultaneous requests for `BUSY`) and confirming the displayed message matches the cause
- [x] 5.5 Add the dev-only Playwright e2e harness and suite: `playwright` in `requirements-dev.txt`, `tests/e2e/test_ui.py` with a fixture that starts a local uvicorn instance with the upstream fetch stubbed, one-time `python -m playwright install chromium`; implement the e2e tests declared in the web-interface Test Requirement blocks (Playwright never enters the container image); verify `python -m pytest tests/e2e/ -q` passes all web-interface e2e tests in headless Chromium

## 6. Container packaging

> Note: 6.1–6.2 implement proposal-level items (container packaging, run documentation) and intentionally map to no capability spec requirement; acceptance criteria live in proposal.md (Impact) and design.md (D5, D9).

- [x] 6.1 Write the single-stage `Dockerfile` (`python:3.13-slim`, `pip install --no-cache-dir -r requirements.txt`, copy code, non-root user, `EXPOSE 8000`, uvicorn `CMD`) plus a `.dockerignore`; verify `docker build` succeeds and the built image is roughly 150–160 MB via `docker images`
  - Size deviation (accepted 2026-10-29): measured 169 MB (linux/amd64) / 194 MB (linux/arm64, this machine) via `podman images`. The 150–160 MB estimate is not attainable with the task-mandated pinned dependency set (the `python:3.13-slim` base alone is ~125–148 MB); build success, non-root user, `EXPOSE 8000`, and the uvicorn `CMD` all verified.
- [x] 6.2 Write the README with the build + run one-liners for both Docker and Podman (`run -d --name yt-transcript --restart unless-stopped -p 8000:8000`), a smoke test, and the library-update runbook for when YouTube breaks the fetchers; verify every documented command runs as written

## 7. End-to-end verification

- [x] 7.1 Run the full definition of done in a container: build, run with `-p 8000:8000`, open the UI, paste a known public YouTube URL, fetch, and copy the transcript to the clipboard; verify the response and UI are correct and that `docker logs yt-transcript` shows the JSON request line and fetch-attempt line(s) with video ID, language, source, duration, and char count
- [x] 7.2 Run the negative paths in the container: non-YouTube URL, a video with no captions, and a concurrent second request while one is in flight; verify the UI shows the right error message for each and `docker logs` records each attempt with its failure reason or `BUSY` outcome

## Workflow follow-up

- Archive the change once implementation is reviewed and the end-to-end checks pass.
- Verify the archived result (specs landed in `openspec/specs/`).
