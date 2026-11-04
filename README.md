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
  read endpoints add `INVALID_NAME` 400 and `NOT_FOUND` 404; summarization
  adds `NOT_CONFIGURED` 503, `INVALID_PROVIDER` 400, `PROVIDER_ERROR` 502,
  and `INPUT_TOO_LONG` 400.
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

## Summarization

With one click, the UI summarizes the transcript currently displayed — a
freshly fetched one or a saved one clicked from the library — using an
OpenAI-compatible LLM backend of your choice. **The displayed transcript
text is sent to the backend you configure**, so point the config at
backends you trust (typically your own local servers).

**Provider config.** The backends are listed in a JSON file — copy
`providers.json.example` to `providers.json` and edit it to your real
providers (or point `PROVIDERS_CONFIG` at your own file). The file is
re-read on every request, so edits take effect without a restart. Shape:

```json
{
  "default": "radai",
  "provider": {
    "radai": {
      "name": "Radai",
      "options": {
        "baseURL": "http://localhost:8000/v1",
        "apiKey": "sk-..."
      },
      "models": {
        "qwen3.5": "Qwen 3.5 27B"
      }
    }
  }
}
```

- `provider` maps provider ids to entries with a display `name`,
  `options.baseURL` (required — the OpenAI-compatible root, e.g.
  `http://localhost:11434/v1`), an optional `options.apiKey` (omit for
  keyless local backends), and a `models` map (its keys are the model ids,
  shown in the picker in file order). Unknown fields are ignored.
- `default` (optional) names the provider pre-selected in the picker;
  without it, the first provider in the file is the default.
- API keys and base URLs never reach the browser — the picker shows ids
  and display names only, and the app only ever calls base URLs present in
  the file.

**Environment variables.**

| Variable | Read by | Default | Meaning |
| --- | --- | --- | --- |
| `PROVIDERS_CONFIG` | the app (inside the container) | `providers.json` in the working directory (`/app/providers.json` in the image) | path to the provider config file |
| `SUMMARY_TIMEOUT` | the app | `120` | backend-call timeout in seconds (connect + read), sized for local 27B-class models; raise it for slower hardware |

With compose, the host-side config path is overridable through the
uncommitted `.env` file: `PROVIDERS_CONFIG=/etc/yt-transcript/providers.json`
bind-mounts that host file to the fixed container path `/app/providers.json`
(read-only).

**Keeping a key-bearing config out of git.** `providers.json` is
git-ignored; the committed `providers.json.example` is a keyless sample.
Keep your real file elsewhere (e.g.
`/etc/yt-transcript/providers.json`) and point the host-side
`PROVIDERS_CONFIG` at it from `.env` (git-ignored) — or, for local dev, set
`PROVIDERS_CONFIG` in the shell when running `uv run python -m app.main`.

**Behavior and limits.** Summarization runs independently of the
transcript fetch chain (it is not subject to the single-flight `BUSY`
limit). The transcript must be at most 100,000 characters (`INPUT_TOO_LONG`
above that) and the output is bounded to 16384 tokens; if the model's context
window is smaller than the transcript, the backend's HTTP error surfaces as
`PROVIDER_ERROR`. A successful summary is saved as `<name>.summary` next to
the transcript (best-effort — a save failure only logs
`summary_save_failed`), stays out of the saved-transcript list (which shows
`.txt` files only), and is re-shown when the transcript is clicked again.
Every summarization is logged as `summary_completed` / `summary_failed`
(structured logs and the in-browser log panel); a malformed config file
logs `config_load_failed` and degrades to "not configured".

**Error messages.** `NOT_CONFIGURED` 503 — no usable providers found in the
config file. `INVALID_PROVIDER` 400 — the picked provider or model is no
longer in the config (reload the page after a config edit).
`PROVIDER_ERROR` 502 — the backend was unreachable, timed out, returned an
HTTP error, sent a malformed response, or returned empty content (a thinking
model can spend its whole output budget reasoning and produce nothing); please
try again.
`INPUT_TOO_LONG` 400 — the transcript exceeds the 100,000-character cap.

**A note on keys.** If a `baseURL` is not `localhost`/loopback and the
provider carries an `apiKey`, use `https://` so the key does not cross the
network in the clear.

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
  providers.py  summarization provider config (read per request)
  summarize.py  provider invocation + summary file save/read
  log.py        structlog JSON-to-stdout setup
  logbus.py     in-memory ring buffer backing the SSE log viewer
  static/       index.html, style.css, app.js (no build step, no CDN)
tests/          unit/API/logging tests + tests/e2e (Playwright, dev-only)
```
