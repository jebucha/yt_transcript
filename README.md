# yt-transcript

A small, self-hosted tool that turns a pasted YouTube URL into a plain-text
transcript with a single "copy to clipboard" action. One lightweight
container, no database. The only state is one plain-text `.txt` file per
fetched transcript, written to a bind-mounted directory. Copy works over
plain HTTP as well as HTTPS/localhost.

This project started as a random idea: a simple way to generate YouTube
transcripts locally, on your own machine or server, without relying on a
third-party transcript service.

- **Stack:** Python 3.13, FastAPI, `youtube-transcript-api` (primary fetcher)
  with `yt-dlp` (automatic fallback), static frontend (no build step).
- **Logging:** one structured JSON object per line on stdout
  (`docker logs` / `podman logs`): process lifecycle, every HTTP request,
  and every YouTube fetch attempt (video ID, language, source, outcome,
  duration, character count). A second surface lives in the browser: the
  **Show logs** button opens a live log panel — up to the 200 most recent
  entries are replayed on open, then new entries stream in live, and the
  panel displays the 200 most recent lines.
- **Error model:** `INVALID_URL` 400, `VIDEO_UNAVAILABLE` 404,
  `NO_CAPTIONS` 404, `UPSTREAM_FAILURE` 502, `BUSY` 503; the saved-transcript
  read endpoint adds `INVALID_NAME` 400 and `NOT_FOUND` 404.
- **Concurrency:** at most one YouTube fetch chain at a time; a second
  concurrent request gets `503 BUSY` immediately.

## Build and run

### Compose (primary)

```sh
docker compose up -d --build
```

`docker-compose.yml` declares everything: the image build, the fixed
container name (`yt-transcript`), the `unless-stopped` restart policy, the
port mapping, a bind mount for transcript storage, a healthcheck, and
container log rotation. After startup the container reports healthy via
`docker compose ps`; inspect output with `docker logs yt-transcript`.

**Optional host-port override.** Drop an uncommitted `.env` file (git-
ignored) next to the compose file containing e.g. `PORT=9000`, then re-run
`docker compose up -d`. Only the published host port changes — the
container still listens on 8000 internally — so open
`http://<server-ip>:9000` instead.

**Transcript storage.** Every successful fetch is also written to a
plain-text `.txt` file (named after the video title) in the host directory
bound to `/transcripts` inside the container — by default
`/home/john/transcripts`. Each file begins with the video's watch URL
(`https://www.youtube.com/watch?v=<video_id>`) as its first line, followed
by the transcript and a single trailing newline. Override the host location
with an uncommitted `.env` file (git-ignored) next to the compose file
containing e.g. `TRANSCRIPTS_DIR=/var/lib/yt-transcripts`, then re-run
`docker compose up -d`. The container-side path is fixed at `/transcripts`
(set by the image's `TRANSCRIPT_DIR` default). Persistence is best-effort:
if the host directory is missing or unwritable, the transcript is still
returned and the failure is only logged as `transcript_save_failed`; the app
never creates the directory itself.

Saved transcripts are browsable from the UI: the **Saved transcripts**
section lists every saved file (most recent first) and loads on page load,
after each successful fetch, and via its Refresh button (no polling).
Clicking a row displays the transcript in the result panel, where Copy keeps
working and the **Download** button saves it as a `.txt` file named after the
stored file (client-side, works over plain HTTP). If the transcript directory
is missing or unreadable the section simply shows an empty state.

**Host-directory permissions (native Linux).** The container runs as the
unprivileged `appuser`, so the host directory must be writable by that user.
If saves log `transcript_save_failed` with a permission error, align the host
directory's ownership/permissions with `appuser`'s uid (e.g. `chown` /
`chmod` on `/home/john/transcripts`). Docker Desktop's bind mounts are
permissive, so this only matters on a native Linux server.

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
(or press Enter), read the result, and click **Copy transcript**. The
**Show logs** button in the page header toggles a live panel of the
application's own structured log entries.

## Smoke test

```sh
# 1) The UI is served
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/   # -> 200

# 2) A known public video with captions
curl -s -X POST http://127.0.0.1:8000/api/transcript \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
# -> 200 {"text": ..., "video_id": "dQw4w9WgXcQ", "title": ..., "language": "en", "source": "primary"}

# 3) The saved-transcript list
curl -s http://127.0.0.1:8000/api/transcripts
# -> 200 {"transcripts": [{"name": "the_end_of_llms_ncm.txt", "size": ..., "modified": ...}, ...]}
#    (most recent first; an empty array when the transcript directory is empty or missing)

# 4) A bad URL
curl -s -X POST http://127.0.0.1:8000/api/transcript \
  -H "Content-Type: application/json" \
  -d '{"url": "not a url"}'
# -> 400 {"error": {"code": "INVALID_URL", "message": ...}}

# 5) The structured logs
docker logs yt-transcript        # or: podman logs yt-transcript
#    -> a "transcript_saved" event with the file path and byte count

# 6) The in-browser log stream (server-sent events)
curl -N http://127.0.0.1:8000/api/logs
#    -> up to the 200 most recent entries as `data: {...}` lines, then new
#       events stream in live (what the Show logs panel displays)

# 7) The transcript file is persisted (compose only)
ls -l /home/john/transcripts/    # -> one .txt file named after the video title
```

Stop when done: `docker compose down` (or `podman compose down`) — removes
the container and its network.

## When YouTube breaks the fetchers (library-update runbook)

Both fetchers wrap unofficial YouTube endpoints; when YouTube changes its
pages the libraries need updating. Symptoms: `UPSTREAM_FAILURE` errors even
for videos that clearly have captions.

```sh
# pin the new versions exactly (look them up in the libraries' changelogs)
uv add 'youtube-transcript-api==<new-version>' 'yt-dlp==<new-version>'
```

Then:

1. Commit the refreshed `pyproject.toml` and `uv.lock` (both are rewritten in
   one step — the diff is the reviewable change, and the pins stay exact).
2. Rebuild and re-run:
   `docker build -t yt-transcript .` followed by
   `docker rm -f yt-transcript && docker run -d --name yt-transcript --restart unless-stopped -p 8000:8000 yt-transcript`
   (podman equivalents).
3. Re-run the smoke test above and check `docker logs yt-transcript` for
   `fetch_attempt` lines with `"outcome": "success"`.

## Development

```sh
# requires uv (>= 0.13) — see https://docs.astral.sh/uv/getting-started/installation/
uv sync                                          # creates the local environment from pyproject.toml + uv.lock

# unit + API + logging tests (all upstream traffic mocked)
uv run python -m pytest tests/ -q --ignore=tests/e2e

# e2e UI tests (headless Chromium; upstream fetch stubbed)
uv run python -m playwright install chromium   # one-time
uv run python -m pytest tests/e2e/ -q

# run locally without a container
uv run python -m app.main                      # http://localhost:8000
```

## Layout

```
app/            FastAPI application
  main.py       app factory, lifecycle + request logging, API endpoints
  chain.py      fetch-chain orchestration (single-flight semaphore, attempt logging)
  fetchers.py   primary (youtube-transcript-api) + fallback (yt-dlp) + text cleaning
  urls.py       YouTube URL/ID parsing (no network)
  errors.py     error taxonomy (code + HTTP status + message)
  persist.py    title-to-file-name derivation + best-effort transcript writer
  library.py    read side of saved transcripts (list + read)
  log.py        structlog JSON-to-stdout setup
  logbus.py     in-memory ring buffer backing the SSE log viewer
  static/       index.html, style.css, app.js (no build step, no CDN)
tests/          unit/API/logging tests + tests/e2e (Playwright, dev-only)
```
