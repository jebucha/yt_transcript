# Security Audit Report — yt_transcript (run-1)

**Target:** `/home/john/repos/yt_transcript` (FastAPI + vanilla JS, self-hosted YouTube transcript tool, v0.3.0)
**Date:** 2026-11-05 · **Method:** 6 parallel hunting agents → adversarial validation (7 agents) → this report
**Prior runs:** none (first run; coverage improves with additional runs — a second run is recommended)

## Executive summary

The app is small, clean, and defensively written in the places that matter most: no code-execution primitives anywhere, a strict video-ID gate that eliminates SSRF via `/api/transcript`, read-side path discipline (resolve-and-contain), `textContent`-only DOM rendering, and an API key that demonstrably never leaves the server. Its core weakness is architectural: **it exposes an unauthenticated API on `0.0.0.0` by default, and several endpoints give any network peer a cheap, unbounded way to degrade or corrupt the service.** One HIGH finding (unbackpressured LLM endpoint that can freeze every endpoint and burn the operator's backend indefinitely) and three MEDIUMs (unbounded request bodies, client-named summary writes, unbounded SSE thread pinning) dominate. Nothing here is exploitable from the internet — every finding is gated on a peer reaching the port — but on a default-configured LAN deployment, a guest device or compromised IoT client can act on all of them.

## Baseline

Comparable software: yt-dlp / youtube-transcript-api (CLI), self-hosted "URL → transcript" web tools, local LLM UIs. All comparables accept the no-auth single-user model, so "no authentication" per se is **not** reported as a finding. The findings below are the deltas: capabilities a no-auth tool need not have (unbackpressured expensive endpoints, client-named writes, unbounded connections, oversized-body acceptance) plus two data-hygiene issues (spec-sanctioned overwrite made attacker-triggerable; LAN topology in public git history).

## Findings

| # | Severity | Title |
|---|----------|-------|
| 1 | **HIGH** | `/api/summarize` has no backpressure: app-wide freeze + unbounded LLM cost burn |
| 2 | **MEDIUM** | No request-body size limit: 3× memory amplification → container OOM |
| 3 | **MEDIUM** | Unauthenticated arbitrary `.summary` creation/overwrite via client-chosen `name` |
| 4 | **MEDIUM** | Unbounded SSE `/api/logs` subscribers pin the shared thread pool |
| 5 | **LOW** | Write side follows symlinks (local foothold + remote trigger → file writes as `appuser`) |
| 6 | **LOW** | Saved `.txt` overwrite via title collision (attacker-published video) |
| 7 | **LOW** | Indirect prompt injection → poisoned, persisted summary |
| 8 | **LOW** | Public git history discloses internal LAN LLM-backend topology |

### 1. HIGH — `/api/summarize`: no backpressure → app-wide freeze + unbounded cost

`POST /api/summarize` (app/main.py:201) accepts up to 100,000 chars of arbitrary text and dispatches a blocking `requests.post(..., timeout=120s)` (app/summarize.py:104) into the **default** asyncio thread pool — the same pool every other endpoint uses for `asyncio.to_thread` work (reads, saves, provider loads, the fetch chain). There is **no semaphore, rate limit, or concurrency cap** on this endpoint (the fetch chain has one; summarize was deliberately exempted), and `uvicorn.run` sets no `limit_concurrency`. Each request holds a pool thread for up to `SUMMARY_TIMEOUT` (120s, env-overridable), and the pool is `min(32, cpu+4)` threads.

**Attack (reproduced):** a LAN peer fires ≥ pool-size concurrent `POST /api/summarize` requests (trivial curl loop). On a 12-core test host (16-thread pool), 24 concurrent requests froze `GET /api/transcripts` from 37 ms to no-response-for-60s, and the fetch chain's `asyncio.wait_for(30s)` (app/chain.py:84) expired on *queue wait alone* → spurious `502 UPSTREAM_FAILURE` with YouTube healthy; `POST /api/transcript` hangs on the untimed `await asyncio.to_thread(save_transcript, ...)` (app/main.py:121). Impact self-recovers ≤120 s after the flood stops; the attacker can repeat indefinitely. Independently, each request spends up to ~100k input + 16,384 output tokens of the operator's backend — **unbounded cost/quota burn on a paid API**, or saturation of a local inference server (the app's documented deployment).

**Fix:** cap concurrent summarize calls (small semaphore) and/or give the LLM calls a dedicated executor; set a `limit_concurrency` on uvicorn. See FINDINGS-DETAIL.md.

### 2. MEDIUM — No request-body size limit → OOM DoS

Neither the app, FastAPI, nor the bare `uvicorn.run` call limits request bodies. Starlette reads the entire JSON body into memory and pydantic parses it **before** the app's 100k-char check runs (app/main.py:229). **Measured amplification: 3.00×** (10 MB → +30 MB … 500 MB → +1.5 GB peak VmHWM, five data points, real app). A ~320 MB body OOMs a 1 GB container; ~660 MB a 2 GB one. `restart: unless-stopped` (docker-compose.yml) makes a single large upload a self-sustaining kill-loop. A secondary robustness issue in the same class: deeply-nested JSON (~2 KB, nesting ≥ ~951) triggers `RecursionError` in FastAPI's 422-detail rendering → 500 (process survives; no segfault on CPython 3.13 — the C scanner hard-caps at 9998 levels, verified).

**Fix:** reject bodies above a small `Content-Length` cap in middleware (5 MiB is ample), and cap streamed/chunked reads. See FINDINGS-DETAIL.md.

### 3. MEDIUM — Unauthenticated arbitrary `.summary` creation/overwrite

`POST /api/summarize` validates `name` only with `is_structurally_invalid_name` (app/main.py:205; app/library.py:68-83) — **no requirement that `<name>.txt` exists, no `.txt` suffix check** (the read side has one; the write side doesn't). After the LLM call succeeds, `save_summary` unconditionally writes `<TRANSCRIPT_DIR>/<name>.summary` (app/summarize.py:200). Any peer can: (a) overwrite the operator's trusted saved summary with attacker-shaped model output — the UI **auto-loads** saved summaries when a transcript is opened (app/static/app.js:313, 415-434), presenting the poisoned text as the operator's previous summary; (b) plant orphan `.summary` files invisible in the library list but readable via `GET /api/transcripts/{name}/summary`. There is **no delete endpoint and no backup** — the original summary is unrecoverable. Reproduced live (mock backend): seeded summary replaced in one unauthenticated POST.

**Fix:** require `name.endswith(".txt")` **and** that the transcript file exists (regular file, contained) before writing. See FINDINGS-DETAIL.md.

### 4. MEDIUM — Unbounded SSE subscribers pin the shared thread pool

Every `GET /api/logs` subscriber loops `await asyncio.to_thread(queue.get, timeout=0.5)` (app/main.py:270) — one blocking default-pool worker per connection for its entire lifetime (0.5 s blocked each 0.5 s). Subscriber count is unbounded (app/logbus.py:65; no cap; `uvicorn` has no `limit_concurrency`). **Reproduced:** 40 idle `curl -N` connections took `GET /api/transcripts` from 3 ms to 0.6–1.0 s; with backlog > 30 s, every fetch attempt spuriously 502s (the `wait_for` budget includes queue wait). A few dozen open "Show logs" panels on a 2–4-core box (pool 6–8) produce the same organically.

**Fix:** drain the per-subscriber `queue.Queue` on the event loop with `get_nowait()` + `await asyncio.sleep(0.5)` instead of a blocking `to_thread` poll (publish is already lock-guarded and non-blocking, so this is safe). See FINDINGS-DETAIL.md.

### 5. LOW — Write side follows symlinks

`save_transcript` (app/persist.py:99) and `save_summary` (app/summarize.py:200) use plain `open(path, "w")` — no `O_NOFOLLOW`/`lstat` pre-check (the read side *does* resolve-and-contain). A local party with write access to the bind-mounted transcript dir (shared mount, co-tenant, low-priv user) plants a symlink; any unauthenticated HTTP peer then triggers the write (directly via `name` on summarize; via a colliding-title video on transcript) and the app **creates or overwrites the symlink target outside `TRANSCRIPT_DIR` as `appuser`** — including `/app` itself (Dockerfile:22 `chown -R appuser /app`), i.e. code tampering persisting across container restarts. Reproduced end-to-end over HTTP (dangling symlinks included). Rated LOW: requires a local foothold the stock single-tenant deployment does not grant to anyone besides the operator.

**Fix:** open with `os.O_NOFOLLOW` (plus resolve-and-contain to mirror the read side) in both writers.

### 6. LOW — Saved `.txt` overwrite via title collision

`derive_file_name` (app/persist.py:52-66) names files from the **sanitized title only** — `video_id` is appended only on >255-byte overflow. Sanitization lowercases and collapses every non-`[A-Za-z0-9_]` run to `_`, so the collision class is very wide (case, punctuation, whitespace). An attacker who enumerates saved names (`GET /api/transcripts`) can publish a YouTube video whose title sanitizes identically (e.g. victim `My Great Video` ← attacker upload `my great video!!!`) and fetch it through `POST /api/transcript`, overwriting the victim's saved transcript (plain `"w"`, app/persist.py:99). Downgrades from the hunters' MEDIUM: last-write-wins on identical derived names is an **explicit, tested spec decision** (openspec/specs/transcript-persistence/spec.md:91); the attack needs a real, visible, ToS-adjacent attacker YouTube upload; the data is recoverable by re-fetching the original video; and the attacker's differing watch-URL header line (rendered in the UI) plus `fetch_attempt` logs give two built-in detection signals.

**Fix:** always append `_<video_id>` to derived names (as the overflow branch already does).

### 7. LOW — Indirect prompt injection → poisoned, persisted summary

Attacker-controlled YouTube captions enter the LLM request as the raw user message with **no delimiters and no "treat as data" instruction** (app/summarize.py:46-52, 159-162; flow: app.js:92 → app.js:463-472). A compliant model emits the attacker's framing as the summary, which is displayed as the app's authoritative output **and persisted to `<name>.summary`, auto-re-displayed on every later open** of the transcript (app.js:313); no delete endpoint exists to clear it. Bounded (verified): no XSS (`textContent`-only), no auto-navigation/auto-fetch of model output, and **nothing sensitive in model context** (key travels in the `Authorization` header, out of context). Residual impact is display-only social engineering; the injection text is visible in the adjacent transcript panel; re-summarizing overwrites the poison.

**Fix:** wrap the transcript in explicit data delimiters and instruct the model to ignore embedded instructions; mark the summary panel as model-generated.

### 8. LOW — Public git history discloses internal LAN LLM-backend topology

The public repo's history (commit `7ddc615`, pushed at `origin/main` tip) contains, in `openspec/changes/archive/add-transcript-summary/tasks.md:40`: *"verified 2026-11-04 against two live backends from `providers.json` (`radai` on **192.168.1.79:8000** and `lmstudio` on **192.168.1.192:1234**)"* — internal IPs, ports, and provider names, permanent in history. Verified: `providers.json`/`providers.json.bk` (with the weak `apiKey "12345"`) were **never** committed. Impact is confined to RFC1918 (no internet routability, no credentials) — value is locating the inference hosts for an actor already on the LAN, which the documented weak key then makes usable.

**Fix:** history rewrite (or at minimum, amend the note and keep host-specific facts out of archived artifacts); rotate the `"12345"` key to a real one.

## Hardening notes (not findings)

- **NUL byte in `{name}` → 500** instead of the documented 400/404 (unhandled `ValueError` from `Path.resolve()`; app/library.py:107, app/summarize.py:232 catch only `OSError|UnicodeDecodeError`). No leak, no crash, no state change — contract violation + stderr traceback spam.
- **Deep-nested JSON → 500** on ~2 KB bodies (RecursionError in 422 rendering; process survives; CPython 3.13 hard-caps at 9998 levels, no segfault — the suspected process-kill was disproven by testing to 500k levels).
- **`/docs`, `/redoc`, `/openapi.json` exposed** (FastAPI defaults never disabled) — full API inventory; near-zero delta for a no-auth tool, but disabling them costs one line.
- **`parse_video_ref` uses `re.match` with `$`** (app/urls.py:18) — a trailing `\n` (`%0a`) bypasses the 11-char match and yields a 12-char ID. Dead sink today (requests re-encodes it; YouTube rejects; clean 404), but `fullmatch` is the correct form.
- **U+2028/U+2029** survive into the log→SSE→DOM pipeline invisibly (urlsplit strips only LF/CR/TAB). No visible line-forgery in current browsers (tested), but it becomes operator-visible log forgery if a client honors LS/PS as line breaks. Strip non-printables from logged paths.
- **Fallback error-classification miss:** the unavailable-phrase list (app/fetchers.py:184-194) contains `"video unavailable"` but YouTube says `"This video is unavailable"` — genuine 404s surface as misleading 502 "rate-limiting" (observed live during the F-1 flood; operators will misdiagnose incidents).
- **`youtube-transcript-api` session has no timeout** (app/fetchers.py:154-157) — a blackholed connection leaks a worker thread (the 30 s `wait_for` abandons the future but not the thread). Not remotely triggerable.
- **Torn reads** during transcript save: `open("w")` truncates before writing (sub-millisecond window, tested; never old+new mix). Write temp + `os.replace` if it matters.
- **10k-char `name`** → ENAMETOOLONG (handled) but logs a ~20 KB line — trivial log-volume amplification by any peer.
- **Single-flight 503 monopoly:** a peer can keep the fetch chain ~100 % occupied with a fetch loop, denying the operator new fetches (reads/summarize unaffected).
- **No delete endpoint:** saved data can never be removed through the API (retention, not a vulnerability).
- **Working-tree `providers.json`** carries `apiKey "12345"` over plain HTTP to LAN IPs — correctly git-ignored and never committed, but rotate it or keep backends loopback-only.
- **`HOST` defaults to `0.0.0.0`** (app/main.py:298) — pin to the intended interface; binding to localhost would eliminate findings 1–4, 6 and 7 in one stroke.

## Positive patterns (verified)

- **No code-execution surface at all:** no subprocess/shell/eval/exec/pickle/yaml/dynamic imports anywhere in app code (grep-verified, re-verified).
- **SSRF-gate is sound:** the user URL is reduced to a strict 11-char ID on allowlisted hosts (app/urls.py:23-53) before any outbound call; the watch URL is rebuilt from the ID — no user string ever reaches a URL host.
- **Read-side path discipline:** structural reject → `.txt` suffix → `resolve()` + `is_relative_to` + `is_file()` (app/library.py:95-105); held up against NUL, newlines, unicode, case, symlinks, directory-named-`.txt`, and double-encoding (live-tested).
- **`api_key` demonstrably never leaves the server:** stripped from `/api/providers`, absent from all error bodies (backend error text discarded, only status kept), exception logs carry type names only, and a full SSE-stream sweep found zero key/URL leakage (live-tested with a recording mock backend).
- **DOM hygiene:** `textContent`-only rendering, no `innerHTML`/`eval`/`postMessage`/`document.write`; log-injection via crafted request paths was live-tested through all four hops (JSON escape → SSE framing → JSON.parse → textContent) and held.
- **No semaphore lock leaks:** every exception/cancellation path in the fetch chain releases the lock (verified against the real `FetchChain`); bounded timeouts everywhere except the one noted above.
- **No config TOCTOU:** `providers.json` is loaded once per request and the same instance is used for validation and the call.
- **Clean container posture:** unprivileged `appuser`, `providers.json` mounted read-only, no secrets in image layers, healthcheck localhost-only.
- **Zero CVEs at pinned versions** (all direct + transitive deps checked against OSV, exact uv.lock pins).
- **Error taxonomy is honest:** clean structured 400/404/502/503 bodies; no stack traces, paths, or config in client-visible errors.

## Next steps

See the suggestions in the conversation; remediation of findings 1–4 are all small, localized changes (see FINDINGS-DETAIL.md for concrete patches). A second audit run is recommended to catch what this run's agents didn't reach.
