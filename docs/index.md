# yt-transcript — code documentation

Per-file documentation for every file in `app/`, plus deployment configs
(`Dockerfile`, `docker-compose.yml`) and the provider configuration template.
One page per Python module, one per static UI file, one per deploy/config file —
module-level and invariant-forward: what each file is *for*, the rules that must
keep holding, and the "design decision N" items behind them (resolved from the
archived change design docs under `openspec/changes/archive/`). Written for a
returning human and for an AI agent working the repo; open this file in a browser.

## System flow

```
browser (app/static: index.html + app.js + style.css - no build, no CDN)
  |
  |  POST /api/transcript {"url": ...}
  v
app/main.py  (FastAPI: 5 MiB body cap -> request logging -> routes)
  |
  v
app/urls.py   parse_video_ref(url)        pure, no network, before the slot
  |
  v
app/chain.py  FetchChain.run - asyncio.Semaphore(1), single flight
  |   slot already held? -> 503 BUSY immediately (reject, don't queue)
  |
  | attempt 1
  v
app/fetchers.py  primary_fetch   (youtube-transcript-api)
  |
  | only on UPSTREAM_FAILURE: exactly one fallback attempt
  v
app/fetchers.py  fallback_fetch  (yt-dlp library, json3, no download)
  |
  | success
  v
app/persist.py  save_transcript   best-effort, worker thread
  |
  v
/transcripts/<title>.txt           bind-mounted; the app never creates it
  ^
  |  read side (never touches the fetch slot)
  |
  |  GET /api/transcripts            app/library.py - list
  |  GET /api/transcripts/{name}     app/library.py - read
  |  GET /api/transcripts/{name}/summary  app/summarize.py - read
  |  POST /api/summarize             app/summarize.py - backend call,
  |                                  app/providers.py config read per request,
  |                                  dedicated 2-worker executor
  |
  |  GET /api/providers              app/providers.py - secret-free listing
  |  GET /api/logs (SSE)             app/logbus.py - 200-entry ring buffer
  v
app/log.py  structlog: one JSON object per line -> stdout
  (every module's events: server_*, http_request, fetch_*, *_saved,
   summary_*, config_load_failed, unhandled_exception)

app/errors.py - code + HTTP status + message; the taxonomy every failure
maps to
```

```
operator
  |
  |  docker compose up -d --build
  v
Dockerfile       → single-stage image (astral/uv:python3.13-bookworm-slim)
  |
  v
docker-compose.yml → service definition, port mapping, volumes, healthcheck
  |
  |  PROVIDERS_CONFIG: ./providers.json:/app/providers.json:ro (mounted)
  v
providers.json.example → config shape for summarization providers
```

## Contents

### Python modules

| Page | What it covers |
| --- | --- |
| [`app/__init__.py`](__init__.html) | the package: role, import-time side effects, module inventory |
| [`app/main.py`](main.html) | app factory, middleware, API endpoints, uvicorn entry point |
| [`app/chain.py`](chain.html) | fetch-chain orchestration: primary → fallback, single-flight |
| [`app/fetchers.py`](fetchers.html) | the two caption-track fetchers and text cleaning |
| [`app/urls.py`](urls.html) | YouTube URL/ID parsing (pure, no network) |
| [`app/errors.py`](errors.html) | the error taxonomy (code + status + message) |
| [`app/persist.py`](persist.html) | title-to-file-name derivation + best-effort writer |
| [`app/library.py`](library.html) | read side of saved transcripts (list + read) |
| [`app/providers.py`](providers.html) | summarization provider config (read per request) |
| [`app/summarize.py`](summarize.html) | provider invocation + summary file save/read |
| [`app/log.py`](log.html) | structlog JSON-to-stdout setup |
| [`app/logbus.py`](logbus.html) | in-memory ring buffer backing the SSE log viewer |

### Static UI files

| Page | What it covers |
| --- | --- |
| [`app/static/app.js`](static/app-js.html) | the frontend script: behavior, state, DOM contract |
| [`app/static/index.html`](static/index-html.html) | the single static page: the DOM contract |
| [`app/static/style.css`](static/style-css.html) | the self-contained stylesheet |

### Deployment configs

| Page | What it covers |
| --- | --- |
| [`Dockerfile`](deploy/Dockerfile.html) | single-stage image build (unprivileged, podman-compatible) |
| [`docker-compose.yml`](deploy/compose-yml.html) | declarative deployment: ports, volumes, healthcheck |

### Config artifacts

| Page | What it covers |
| --- | --- |
| [`providers.json.example`](providers-json-example.html) | summarization provider config shape (mounted read-only) |

## Keeping the HTML in sync

Markdown is the single source of truth; the `.html` files are generated
output. After editing any page, re-render with:

```
uv run python docs/generate.py
```

and commit the regenerated HTML. The generator is `docs/generate.py`
(stdlib + the dev-only `markdown` dependency) — it wraps every page in the
shared shell (sidebar nav + `style.css`) and renders the `fenced_code` and
`tables` extensions only.
