# Proposal

## Why

We want a small, self-hosted tool that turns a pasted YouTube URL into a plain-text transcript with a single "copy to clipboard" action. It will run as one lightweight container on a Linux server (Docker or Podman) and must be cheap to run and trivial to operate.

## What Changes

- New containerized web application (greenfield project): one process serving a static web page and a single transcript API endpoint.
- Web interface: paste a YouTube URL, fetch the transcript, view it, and copy it to the clipboard. Copy must work over plain HTTP (non-secure context) as well as HTTPS/localhost.
- Server-side transcript retrieval from YouTube caption tracks: primary path via `youtube-transcript-api`, automatic fallback via `yt-dlp` when the primary fails (e.g., rate-limited or blocked).
- Captions only: no audio download, no speech-to-text. Videos without caption tracks produce a clear, user-facing error.
- Structured JSON logging to stdout covering process lifecycle, incoming web requests, and each YouTube fetch attempt (no log files, no external collector dependency).
- Container packaging: single-stage Dockerfile on `python:3.13-slim`, non-root user, podman-compatible. No docker-compose for the initial scope.

## Capabilities

### New Capabilities
- `transcript-retrieval`: Accepts a YouTube video URL, resolves its video ID, fetches the caption track (manual preferred, then auto-generated), and returns clean plain text plus metadata; falls back from the primary library to yt-dlp on failure; produces distinct, actionable errors for invalid URLs, unavailable videos, missing captions, and upstream rate-limiting/blocking.
- `web-interface`: A single static web page where the user pastes a YouTube URL, requests the transcript, sees loading and error states, reads the result, and copies it to the clipboard with visible feedback; copy works in both secure and non-secure contexts.
- `structured-logging`: Structured JSON log lines on stdout for process lifecycle events, every incoming web request, and every YouTube fetch attempt, suitable for `docker logs` / `podman logs`.

### Modified Capabilities
(none — greenfield project, no existing specs)

## Impact

- Code: new greenfield application under the project root (web server, fetch chain, static frontend, Dockerfile, run instructions).
- Runtime dependencies: Python 3.13, FastAPI (or equivalent minimal ASGI server), `youtube-transcript-api` (pinned), `yt-dlp` (pinned).
- Container: new image based on `python:3.13-slim`, expected total size roughly 150–160 MB, non-root runtime user, port 8000.
- External systems: outbound HTTPS to YouTube (watch page and timedtext caption endpoints); no inbound dependencies, no database, no state.
- Out of scope: audio transcription (Whisper), video/audio download, authentication, persistence, HTTPS termination, docker-compose, batch processing.
