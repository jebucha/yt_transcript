# Architecture Summary — yt_transcript (Phase 1 Recon)

## Application

Small self-hosted, single-container web app (FastAPI + uvicorn, Python 3.13, uv-managed).
Pastes a YouTube URL → returns a plain-text transcript (primary: `youtube-transcript-api`,
fallback: in-process `yt-dlp` json3 subtitles) + optional LLM summarization via an
OpenAI-compatible `/chat/completions` backend. Also: saved-transcript library (plain `.txt`
files on a bind mount), SSE log viewer streaming the app's structlog JSON output, and a
vanilla-JS UI (no build step, no framework, no CDN; DOM insertion via `textContent` only).

- **Entry point**: `app/main.py` — `create_app()` (~lines 80-287) registers ALL routes; `python -m app.main` runs uvicorn (HOST default `0.0.0.0`, line 298; PORT default 8000).
- **Deployment**: Dockerfile (unprivileged `appuser`), docker-compose.yml (bind-mounts transcripts dir + `providers.json` read-only).
- **Persistence**: NO database. `.txt` and `.summary` files in `TRANSCRIPT_DIR` (default `/transcripts`), written best-effort (`app/persist.py`, `app/summarize.py`).
- **No database, no auth, no sessions, no cookies, no CORS config, no rate limiting.** The only middleware is request-logging (`app/main.py:84-107`).
- **No subprocess/shell/eval/exec/pickle/yaml/dynamic imports anywhere in app code** (grep-verified). yt-dlp runs in-process.

## Baseline comparables

yt-dlp / youtube-transcript-api (CLI libs), self-hosted "URL → transcript" web tools (e.g. Whisper Web UI, you-tube-summarizer-style apps). All comparables accept: **no authentication** (single-user local tool; whoever reaches the port is trusted), plain HTTP, single-flight/no rate limits. The app's README explicitly documents that transcript text is sent to operator-configured LLM backends (data leaves the machine by design). Calibrate findings against this; the absence of auth per se matches the comparable baseline — but auth-ABSENT + destructive/costly endpoints + network exposure can still combine into findings.

## HTTP API (all in app/main.py)

| # | Route | Line | Params | Notes |
|---|-------|------|--------|-------|
| 1 | `POST /api/transcript` | 109 | `{url: str}` | Runs fetch chain (`app/chain.py`): single-flight semaphore (503 BUSY if occupied), 30s/attempt, primary→fallback. Best-effort file save (`app/persist.py:save_transcript`). |
| 2 | `GET /api/transcripts` | 136 | — | Lists `.txt` files (`app/library.py:33-65`), mtime desc. |
| 3 | `GET /api/providers` | 145 | — | Reads `providers.json` **per request** (`app/providers.py:91`); returns id/name/models only — strips base_url and api_key. |
| 4 | `GET /api/transcripts/{name}` | 160 | path `name` | Structural reject (`app/library.py:is_structurally_invalid_name` 68-83: empty, `.`, `/`, `\`, `..` segments), then `.txt` suffix + `resolve()` + `is_relative_to(base)` + `is_file()` (`library.py:86-108`). |
| 5 | `GET /api/transcripts/{name}/summary` | 179 | path `name` | Same guard stack in `app/summarize.py:read_summary` (212-233). |
| 6 | `POST /api/summarize` | 200 | `{text, name, provider, model}` | Name structural check (205) → `load_providers` (211) → provider+model MUST exist in config (219-228) → 100,000-char text cap (229, `summarize.py:36`) → `summarize_with_provider` (239-242) → best-effort `save_summary` (251, `summarize.py:191-209`). **NO semaphore/rate limit; each call up to SUMMARY_TIMEOUT (default 120s).** |
| 7 | `GET /api/logs` | 254 | — | SSE (`text/event-stream`), replays last 200 entries from in-memory ring buffer (`app/logbus.py`, DEFAULT_BUS) then live fan-out, 0.5s poll. `f"data: {json.dumps(entry)}\n\n"` (267, 275). **Infinite stream, unbounded subscriber count (check logbus queue bounds).** |
| 8 | `/` static | 286 | — | `StaticFiles(directory=app/static, html=True)`, mounted last. |
| 9 | `/docs`, `/redoc`, `/openapi.json` | FastAPI defaults | — | **NOT disabled** — unauthenticated interactive API inventory. |

No Query/Header/Cookie/Form/UploadFile params anywhere. No WebSocket. No request-size limit.

## Trust model

- **Actors**: (a) any HTTP client reaching the port — fully trusted by design (no auth); (b) browser UI — same capabilities, same-origin; (c) local operator — chooses TRANSCRIPT_DIR, `providers.json` (outbound URL set + API keys), env vars; (d) YouTube upstream — supplies titles (feed file names) and transcript text; (e) LLM backend — operator-chosen.
- **Env vars** (read at call time): `HOST`, `PORT`, `TRANSCRIPT_DIR`, `PROVIDERS_CONFIG` (redirects which config file is trusted), `SUMMARY_TIMEOUT`.
- **Outbound calls**: (1) `https://www.youtube.com/watch?v={id}` title scrape `requests.get` with `allow_redirects=True` (`app/fetchers.py:82-107`); (2) youtube-transcript-api and yt-dlp against the same validated-ID URL (`fetchers.py:148-174`, `212-299`); (3) LLM `{base_url}/chat/completions` `requests.post` with `Authorization: Bearer <apiKey>` (`app/summarize.py:80-144`; user text goes in the message body, fixed server-side prompt).
- **Video ID is the only user string that reaches YouTube**: `parse_video_ref` (`app/urls.py:23-53`) accepts only `youtube.com`/`youtube-nocookie.com`/`youtu.be` → 11-char ID `^[A-Za-z0-9_-]{11}$`. No arbitrary outbound URL via /api/transcript.
- **File writes**: `persist.py:save_transcript` → `<TRANSCRIPT_DIR>/<derived>.txt`, name server-derived from YouTube title (sanitized to Unicode `\w` runs collapsed to `_`, 255-byte cap, `persist.py:23-66`) + video_id; plain `"w"` overwrite, **write side follows symlinks** (no resolve/containment on write). `summarize.py:save_summary` → `<TRANSCRIPT_DIR>/<name>.summary` with **client-supplied flat name**, structural check only (no resolve/containment — acceptable given no separators, but asymmetric vs reads).
- **Log flow**: structlog JSON to stdout (`app/log.py`) → TeeStream into `logbus` ring buffer → SSE to ANY client. Middleware logs raw `request.url.path` (client-controlled). Any stdout line parseable as JSON is published (`logbus.py:99-104`). Unhandled-exception handler logs a last line (`app/log.py:55-60`).
- **Client rendering**: `app/static/app.js` — `textContent` only (lines 76,81,100,101,228,247-250,301,303,356,401,408,619...), no innerHTML/eval/postMessage/document.write (grep-verified); `EventSource("/api/logs")` JSON.parses and textContent-renders (631-643); `URL.createObjectURL` on local blob (324-335); fetch URLs built with `encodeURIComponent` (286, 417).

## Working-tree notes (non-app)

- `providers.json` present in working tree (git-ignored) with **plaintext apiKey `"12345"`** and LAN base URLs (`192.168.1.x`). `providers.json.bk` also present. `providers.json.example` is committed keyless. **Check git history for whether a real-key config was ever committed.**
- Exact-pinned deps in pyproject.toml + uv.lock; `requests`, `yt-dlp==2026.10.26`, `youtube-transcript-api==1.2.4`, FastAPI 0.162.0, uvicorn 0.54.0, structlog.

## Key file map (starting points)

- `app/main.py` — routes, middleware, SSE, app factory
- `app/chain.py` — fetch orchestration, semaphore, timeouts, logging
- `app/fetchers.py` — outbound YouTube calls, `clean_text`, yt-dlp temp dir
- `app/urls.py` — `parse_video_ref` (the URL→ID gate)
- `app/errors.py` — error taxonomy → HTTP status map
- `app/persist.py` — file name derivation, transcript save
- `app/library.py` — list/read transcripts, structural name check
- `app/summarize.py` — LLM call, 100k cap, summary save/read
- `app/providers.py` — config loading per request
- `app/log.py`, `app/logbus.py` — logging, SSE bus
- `app/static/app.js`, `index.html` — client
- `Dockerfile`, `docker-compose.yml`, `providers.json*`
