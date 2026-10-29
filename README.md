# yt-transcript

A small, self-hosted tool that turns a pasted YouTube URL into a plain-text
transcript with a single "copy to clipboard" action. One lightweight
container, zero state, no database. Copy works over plain HTTP as well as
HTTPS/localhost.

This project started as a random idea: a simple way to generate YouTube
transcripts locally, on your own machine or server, without relying on a
third-party transcript service.

- **Stack:** Python 3.13, FastAPI, `youtube-transcript-api` (primary fetcher)
  with `yt-dlp` (automatic fallback), static frontend (no build step).
- **Logging:** one structured JSON object per line on stdout
  (`docker logs` / `podman logs`): process lifecycle, every HTTP request,
  and every YouTube fetch attempt (video ID, language, source, outcome,
  duration, character count).
- **Error model:** `INVALID_URL` 400, `VIDEO_UNAVAILABLE` 404,
  `NO_CAPTIONS` 404, `UPSTREAM_FAILURE` 502, `BUSY` 503.
- **Concurrency:** at most one YouTube fetch chain at a time; a second
  concurrent request gets `503 BUSY` immediately.

## Build and run

### Compose (primary)

```sh
docker compose up -d --build
```

`docker-compose.yml` declares everything: the image build, the fixed
container name (`yt-transcript`), the `unless-stopped` restart policy, the
port mapping, a healthcheck, and container log rotation. After startup the
container reports healthy via `docker compose ps`; inspect output with
`docker logs yt-transcript`.

**Optional host-port override.** Drop an uncommitted `.env` file (git-
ignored) next to the compose file containing e.g. `PORT=9000`, then re-run
`docker compose up -d`. Only the published host port changes — the
container still listens on 8000 internally — so open
`http://<server-ip>:9000` instead.

### Without compose

If you have no compose tooling, the raw build + run path still works:

```sh
# Docker
docker build -t yt-transcript .
docker run -d --name yt-transcript --restart unless-stopped -p 8000:8000 yt-transcript
```

```sh
# Podman
podman build -t yt-transcript .
podman run -d --name yt-transcript --restart unless-stopped -p 8000:8000 yt-transcript
```

The listen port can be overridden with the `PORT` environment variable
(default `8000`), e.g. `docker run ... -e PORT=9000 -p 9000:9000 ...`.

With a compose provider installed, podman supports the same compose path
as Docker: `podman compose up -d --build` (podman's `compose` subcommand
delegates to a provider such as podman-compose). Verified with podman
6.1.4 + podman-compose 1.6.0: the file resolves via `podman compose
config`, the service starts healthy, and the `.env` `PORT` override works.

Open `http://<server-ip>:8000`, paste a YouTube URL, click **Fetch transcript**
(or press Enter), read the result, and click **Copy transcript**.

## Smoke test

```sh
# 1) The UI is served
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/   # -> 200

# 2) A known public video with captions
curl -s -X POST http://127.0.0.1:8000/api/transcript \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
# -> 200 {"text": ..., "video_id": "dQw4w9WgXcQ", "title": ..., "language": "en", "source": "primary"}

# 3) A bad URL
curl -s -X POST http://127.0.0.1:8000/api/transcript \
  -H "Content-Type: application/json" \
  -d '{"url": "not a url"}'
# -> 400 {"error": {"code": "INVALID_URL", "message": ...}}

# 4) The structured logs
docker logs yt-transcript        # or: podman logs yt-transcript
```

Stop when done: `docker compose down` (or `podman compose down`) — removes
the container and its network.

## When YouTube breaks the fetchers (library-update runbook)

Both fetchers wrap unofficial YouTube endpoints; when YouTube changes its
pages the libraries need updating. Symptoms: `UPSTREAM_FAILURE` errors even
for videos that clearly have captions.

```sh
python3.13 -m venv .venv
.venv/bin/pip install -U youtube-transcript-api yt-dlp
# re-pin the new versions into requirements.txt (keep the pins exact)
.venv/bin/python -m pip freeze | grep -iE '^(youtube-transcript-api|yt-dlp)=='
```

Then:

1. Update `requirements.txt` with the two new pins.
2. Rebuild and re-run:
   `docker build -t yt-transcript .` followed by
   `docker rm -f yt-transcript && docker run -d --name yt-transcript --restart unless-stopped -p 8000:8000 yt-transcript`
   (podman equivalents).
3. Re-run the smoke test above and check `docker logs yt-transcript` for
   `fetch_attempt` lines with `"outcome": "success"`.

## Development

```sh
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

# unit + API + logging tests (all upstream traffic mocked)
.venv/bin/python -m pytest tests/ -q --ignore=tests/e2e

# e2e UI tests (headless Chromium; upstream fetch stubbed)
.venv/bin/python -m playwright install chromium   # one-time
.venv/bin/python -m pytest tests/e2e/ -q

# run locally without a container
.venv/bin/python -m app.main                      # http://localhost:8000
```

## Layout

```
app/            FastAPI application
  main.py       app factory, lifecycle + request logging, API endpoint
  chain.py      fetch-chain orchestration (single-flight semaphore, attempt logging)
  fetchers.py   primary (youtube-transcript-api) + fallback (yt-dlp) + text cleaning
  urls.py       YouTube URL/ID parsing (no network)
  errors.py     error taxonomy (code + HTTP status + message)
  log.py        structlog JSON-to-stdout setup
  static/       index.html, style.css, app.js (no build step, no CDN)
tests/          unit/API/logging tests + tests/e2e (Playwright, dev-only)
```
