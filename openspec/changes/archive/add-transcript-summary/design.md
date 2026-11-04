# Design

## Context

See proposal.md for motivation. Current-state constraints that shape the approach:

- The app is FastAPI + vanilla JS static files, no build step, no framework, no CDN; all fetched content enters the DOM via `textContent` only.
- `requests` is already a direct dependency (imported by `app/fetchers.py`); `pyproject.toml` pins are exact and managed with `uv`.
- Project conventions (AGENTS.md): no blocking I/O on the event loop (filesystem and HTTP work goes through `asyncio.to_thread`); the single-flight semaphore governs **only** the YouTube fetch chain and read endpoints must not touch it; backend modules keep FastAPI imports out (see `app/library.py`, `app/persist.py`) so they are testable against `tmp_path`.
- The error taxonomy lives in `app/errors.py` (`TranscriptError` subclasses with `code` + `status`), and the UI maps codes to messages in `ERROR_MESSAGES` in `app/static/app.js`.
- The e2e harness (tests/e2e) runs an in-process uvicorn server with the fetch chain stubbed (`chain_mod.default_chain = stub`), so network-dependent behavior is tested deterministically.
- Container: `WORKDIR /app`, code at `/app/app`, unprivileged user, compose already decouples host paths via uncommitted `.env` overrides (host-side `TRANSCRIPTS_DIR` mapping to the app-side `TRANSCRIPT_DIR`).
- Providers speak the OpenAI-compatible HTTP protocol (`POST {baseURL}/chat/completions`); some define an `apiKey`, some do not (local backends).

## Goals / Non-Goals

**Goals:**

- One-click summarization of whatever transcript is displayed (fresh fetch or saved row), with the operator choosing the backend from a config-file list of providers.
- Keys and base URLs stay server-side; the browser sees ids and display names only, and the server can only ever reach base URLs present in the config file.
- Zero new Python dependencies.
- Summaries persisted next to transcripts and re-shown when the transcript is re-displayed.
- Deterministic unit + e2e tests with no real LLM traffic.

**Non-Goals:**

- Streaming/partial summaries, multi-turn follow-up questions, or per-summary prompt customization (the instruction is fixed server-side).
- Enabling Download for freshly fetched transcripts (the `name` field lands in the fetch response, but the Download button's enabled predicate is intentionally unchanged).
- Provider health checks, failover between providers, or provider management UI.
- AuthN/authZ for the app itself (unchanged: it is a personal tool).

## Decisions

### 1. Plain HTTP via `requests` — no `openai` SDK

The backend call is `POST {baseURL}/chat/completions` with body `{"model": <id>, "messages": [{"role": "system", "content": <fixed instruction>}, {"role": "user", "content": <transcript text>}], "max_tokens": 16384}`, sent with `requests.post(url, json=..., timeout=...)` from a worker thread. `Authorization: Bearer <key>` is attached only when the provider defines an `apiKey`. The response's `choices[0].message.content` must be a non-empty string after stripping whitespace: a 2xx response whose content is empty or whitespace-only raises the failure type with reason `empty_response` — a backend that "succeeds" with no content (observed with thinking models that exhaust the output budget in reasoning, and with gateways that return reasoning in a side field alongside empty content) is a failed summarization, not a successful one.

- **Why**: every configured provider is OpenAI-compatible, so the SDK buys nothing; the app already depends on `requests`, and AGENTS.md forbids adding dependencies casually. A per-call `requests.post` (no shared `Session`) keeps the call thread-safe without any locking.
- **Alternatives**: `openai` SDK with custom `base_url` (new heavy dependency, still plain HTTP under the hood); `httpx` (not a declared app dependency — it is only a test dep for Starlette's TestClient).

### 2. Module layout follows the library/persist split

- `app/providers.py` — FastAPI-free: resolves the config path (`PROVIDERS_CONFIG` env var, default `providers.json` in the working directory), reads + parses + validates the file, returns a plain structure of usable providers (`id`, display `name`, `base_url`, optional `api_key`, ordered `models`) plus the default provider id. Missing file, unreadable file, malformed JSON, or no usable provider → an "empty" result, never an exception.
- `app/summarize.py` — FastAPI-free: the backend call (`summarize_with_provider(...)` taking the provider entry, model id, text, and timeout → summary string, raising a narrow failure type with a machine-readable reason), the fixed summarization instruction, the input cap (100,000 chars) and output cap (`max_tokens=16384`) as module constants, and the summary file save/read (best-effort save, resolve-and-contain read, reusing `is_structurally_invalid_name` and `transcript_dir()`).
- `app/main.py` — thin endpoints wiring the two modules through `asyncio.to_thread`, mapping failures onto the existing `JSONResponse({"error": {"code", "message"}})` shape.
- `app/errors.py` — new `TranscriptError` subclasses: `SummaryNotConfiguredError` (`NOT_CONFIGURED`, 503), `InvalidProviderError` (`INVALID_PROVIDER`, 400), `ProviderError` (`PROVIDER_ERROR`, 502), `InputTooLongError` (`INPUT_TOO_LONG`, 400). Structurally invalid names keep the read-side's `INVALID_NAME` 400.

- **Why**: mirrors `library.py`/`persist.py` — pure, directly testable against `tmp_path` and a mocked HTTP layer, with zero FastAPI import leakage.
- **Alternative rejected**: one module mixing config, HTTP, and files (less testable, breaks the established pattern).

### 3. Config is read per request, never at startup

The summarization endpoints read the config file on every request (through `asyncio.to_thread`); `GET /api/providers` and `POST /api/summarize` each get the current state. A missing/malformed file means "not configured" (empty list / 503), never a startup failure.

- **Why**: the app must boot without any config (summarization is an optional feature that degrades gracefully); edits take effect without a restart; the file is tiny, so per-request reads are negligible. This matches how the transcript directory is treated (read on every request, best-effort).
- **Alternatives rejected**: read-at-startup (breaks boot on a malformed file, no hot reload); mtime cache (complexity for no observable gain).

### 4. The client sends text + name; the server never re-reads the transcript file

`POST /api/summarize` body: `{"text": <displayed transcript>, "name": <transcript file name>, "provider": <id>, "model": <id>}`. The server summarizes the `text` as given — that is the spec's "currently displayed transcript" — and uses `name` only for the alongside save.

- **Why**: the displayed text is the source of truth (a file could in principle differ from what is on screen), and avoiding a file read keeps the endpoint one filesystem-write away from working even if the transcript file vanished.
- Consequence: the client needs a trustworthy name for *fresh* fetches too, which is why the fetch response gains `name` (decision 5).
- **Alternative rejected**: name-only request where the server reads the file (diverges from "what is displayed"; fails when the file is missing).

### 5. Fetch response gains the derived `name`

`POST /api/transcript` computes `name = derive_file_name(title, video_id)` — the existing pure function in `app/persist.py` — and includes it in the response. It is computed from the title/video id, not read back from disk, so the client gets the name even when the best-effort save fails (missing/unwritable directory).

- **Why**: the client must reference the just-fetched transcript by its persisted file name for the alongside save; deriving it server-side is the single source of truth for the name, so the UI can never guess it wrong.
- **UI consequence, carefully scoped**: the client stores the fetch name in a *new* variable (`currentTranscriptName`) and leaves `currentSavedName` untouched. Download's enabled predicate (`currentSavedName` non-empty) therefore stays exactly as specified by the transcript-library capability — fresh fetches still do not enable Download.

### 6. Summary files: `<name>.summary`, non-`.txt`, best-effort save, contained read

Successful summarization writes the summary text verbatim (UTF-8) to `<name>.summary` in `transcript_dir()`, overwriting on re-summarize. Save failure does not change the 200 response (best-effort, logged). The read endpoint `GET /api/transcripts/{name}/summary` applies the read-side discipline in order: structural reject (400 `INVALID_NAME`), resolve-and-contain, regular-file check (404 `NOT_FOUND` when absent), and reads verbatim.

- **Why**: the `.summary` extension keeps the saved-transcript list untouched (it lists only `.txt`); the read path reuses the exact traversal-safety rules of `app/library.read_transcript`; best-effort save mirrors the transcript save behavior.
- **Alternative rejected**: a `<name>.summary.txt` name (would appear in the saved list as a transcript) or a separate summaries directory (new path config, new containment rules, no benefit).

### 7. Secret-free provider listing; ids are validated against the *current* config

`GET /api/providers` returns `{"default": <id|null>, "providers": [{"id", "name", "models": [<ids>]}]}`. `apiKey` and `baseURL` never leave the server. `POST /api/summarize` re-validates the provider/model ids against the config it just read, so deleting a provider from the file takes effect on the very next click (400 `INVALID_PROVIDER`), and the server can only ever send traffic to base URLs present in the config file — a tampered client cannot point it elsewhere.

- **Why**: the config file holds secrets; the UI only needs labels and ids. Ids-as-opaque-handles also makes the SSRF surface exactly "configured base URLs".
- **Default**: an explicit top-level `"default"` key in the config wins; otherwise the first provider in file order (JSON object order, preserved by Python's parser). Model ids are listed in the same JSON object order of each provider's `models` map, and only the map's keys are used.

### 8. Endpoint validation order

1. `name` structural reject → 400 `INVALID_NAME` (no filesystem access),
2. read config; empty → 503 `NOT_CONFIGURED`,
3. provider/model ids not in config → 400 `INVALID_PROVIDER` (no backend call),
4. `text` over 100,000 chars → 400 `INPUT_TOO_LONG` (no backend call),
5. backend call → 502 `PROVIDER_ERROR` on unreachable / timeout / non-2xx / malformed body / empty content,
6. best-effort summary save, then 200 `{"summary": ...}`.

Cheap, local checks precede the expensive network call, and every rejection path is backend-free (spec scenarios test exactly this). When several rejections apply, the first failing step in this order wins — e.g. a missing config *and* overlong text is 503 `NOT_CONFIGURED`, not 400 `INPUT_TOO_LONG`.

### 9. No new locking; the fetch chain stays untouched

Summarize requests run independently (each in its own `asyncio.to_thread` worker); two concurrent summarizes are allowed. The single-flight semaphore is not touched, per the AGENTS.md constraint, and the endpoint never invokes the fetch chain.

- **Why**: the call is pure I/O wait against an independent backend; queueing summaries behind transcript fetches (or behind each other) would add latency with no resource benefit at this app's scale.
- **Alternative rejected**: a summarization single-flight semaphore (no shared resource to protect; complexity without benefit).

### 10. Timeouts and caps

- `SUMMARY_TIMEOUT` env var (seconds) bounds the backend call (connect + read), default **120** — sized for local 27B-class models on LAN hardware, not cloud latency. Non-numeric values fall back to the default (same style as `PORT` handling).
- Input cap: 100,000 characters (≈25k tokens) — above it the request is rejected with `INPUT_TOO_LONG` rather than risking an opaque provider 400. Output cap: `max_tokens: 16384`.
- **Output cap sizing (set during manual testing)**: the configured backends include thinking models, and on their serving stacks reasoning tokens are drawn from the same `max_tokens` budget as content. At `max_tokens: 600`, a long transcript (observed at ~90k chars) exhausted the budget in reasoning, the backend returned an *empty* `content`, and the endpoint accepted that empty string as a successful 200 and saved it as a 0-byte `.summary` file — the summary silently never appeared in the UI while every log line read as success. The cap is therefore sized at `16384`: headroom for reasoning plus a full summary, while the fixed instruction keeps actual output short and the summary stays bounded server-side.
- **Note**: a model whose context window is smaller than the transcript will return an HTTP error, which surfaces as `PROVIDER_ERROR`; the README tells operators to pick models with adequate context.

### 11. UI state machine

- On page load: one `fetch("/api/providers")` (no polling — same convention as the saved list). The picker is a `<select>` with one option per provider/model pair, labeled `<display name> — <model id>`; the default entry is pre-selected.
- Summarize button enabled ⟺ a transcript is displayed **and** ≥ 1 provider is configured. While a request is in flight, button + picker are disabled and the button shows the spinner (reusing the fetch button's pattern).
- `currentSummary` state: set on summarize success; cleared (panel hidden) in `renderResult` and `displaySavedTranscript`; in `displaySavedTranscript`, after the transcript loads, a best-effort `GET /api/transcripts/{name}/summary` populates the panel (404 or network error → panel hidden, page unaffected).
- Summary panel: dedicated region in the result section, plain-text insertion only, with its own copy button reusing the existing `copyText` (Clipboard API + legacy fallback) and the "Copied!" confirmation pattern.
- Errors: new entries in `ERROR_MESSAGES` for `NOT_CONFIGURED`, `INVALID_PROVIDER`, `PROVIDER_ERROR`, `INPUT_TOO_LONG`; shown in the existing error banner.
- The provider call seam for e2e mirrors `chain_mod.default_chain = stub`: `summarize_with_provider(...)` delegates its HTTP dispatch to a module-level function (`_call_chat_completions`) that the e2e fixture replaces with a recording stub (success and failure modes). The stub sits *below* `summarize_with_provider`, so the real function's `summary_completed`/`summary_failed` emission still runs (the log-viewer e2e scenarios need those lines in the panel); unit tests instead pass a mocked HTTP layer directly.

### 12. Deployment

- Repo ships a **keyless sample** `providers.json.example` at the root (example providers with localhost URLs, no keys, a `default` key); the real `providers.json` is git-ignored (it may carry API keys) and is created locally by copying the sample, or a key-bearing file is kept out of the repo and pointed at via `PROVIDERS_CONFIG` in the uncommitted `.env`. On a fresh clone the default compose mount source (`./providers.json`) does not exist: Docker auto-creates an empty directory at the source, the app's per-request read fails, logs one `config_load_failed`, and degrades to "not configured" — consistent with the boot-without-config requirement (decision 3). The README's "Summarization" section documents the copy step.
- `docker-compose.yml`: third volume `"${PROVIDERS_CONFIG:-./providers.json}:/app/providers.json:ro"` — host side overridable (`.env`), container side fixed at the working-directory default, read-only since the app never writes the config. Local dev needs no change: the default path is `providers.json` in the working directory.
- README gains a short "Summarization" section: config shape, env vars (`PROVIDERS_CONFIG`, `SUMMARY_TIMEOUT`), error messages, and the note that transcript text is sent to the configured backends.

### 13. Logging

`app/summarize.py` emits `summary_completed` (info: provider, model, duration_ms, `chars_in`, `chars_out`) and `summary_failed` (error: provider, model, duration_ms, `reason` ∈ {`unreachable`, `timeout`, `http_error`, `malformed_response`, `empty_response`}, `detail`) around the backend call, and logs a failed summary save as `summary_save_failed` (error: `name`, `path`, `reason`, `detail` — the OS error). A failed provider-config load (malformed JSON) is logged by `app/providers.py` as `config_load_failed` (error: `path`, `reason`, `detail` — the parse error, never the file contents); a missing file is the normal "not configured" state, not a logged failure. Both follow the existing `transcript_save_failed` convention. The log-viewer's `LOG_FORMATTERS` in `app.js` gains one-line humanized formatters for all four. No transcript/summary text, no config file contents, no keys — enforced by construction (the logged fields never include them) and by dedicated tests.

## Test Strategy

- `app/providers.py` and `app/summarize.py` are unit-tested against `tmp_path` with a mocked HTTP layer (no FastAPI, no network): config read/validation, request shape, auth headers, caps, save/read discipline, log events.
- Endpoints are tested with Starlette's TestClient: status codes and the error shape, rejection precedence, no side effects, no fetch-chain interaction.
- E2E (Playwright against an in-process uvicorn server) stubs the fetch chain and the summarize HTTP dispatch seam and points `PROVIDERS_CONFIG` at a temporary config — deterministic, no real LLM traffic.
- Every spec scenario carries a Test Requirement block (id/file/command/pass); the integration gate is the full non-e2e and e2e suites passing with no skips (tasks 6.1–6.2).

## Risks / Trade-offs

- **Local backends are slow or hang** → 120 s default timeout (tunable via `SUMMARY_TIMEOUT`); spinner + error banner keep the UI honest; the operator can raise the timeout for slow hardware.
- **Model context window < transcript length** → provider returns an HTTP error, surfaced as `PROVIDER_ERROR`; the 100k-char input cap bounds the worst case and the README documents picking adequately-contexted models. The cap is a heuristic (chars ≠ tokens), not a guarantee.
- **A backend returns empty content** (reasoning exhausts the budget on an unusually long input, or a model declines) → treated as a backend failure: 502 `PROVIDER_ERROR`, `summary_failed` with reason `empty_response`, and no `.summary` file written (decision 1). The `16384` cap makes this rare; the rejection makes it visible in the logs and the error banner instead of a silent 0-byte save.
- **Real config committed to the repo** → the repo ships only the keyless sample (`providers.json.example`); `providers.json` is git-ignored; the README shows how to keep a real key-bearing file out of git via `PROVIDERS_CONFIG` + `.env`.
- **Stale picker after a config edit** (page loaded before the edit) → the next click gets a clean 400 `INVALID_PROVIDER` ("provider no longer configured — reload the page"); no silent failure, no auto-refetch machinery.
- **Concurrent summarizes** hit the backend in parallel → acceptable at personal-tool scale (decision 9); if a shared local backend throttles, that surfaces as `PROVIDER_ERROR`, and a limit can be added later without spec changes.
- **`requests` per-call connections** (no shared `Session`) → tiny overhead per summarize; avoids cross-thread session-state concerns entirely.

## Migration Plan

1. Ship as an additive change: new modules, three new endpoints, one additive field on `POST /api/transcript`, new UI region. No existing endpoint's response shape changes; no data migration.
2. Deploy: rebuild the image, add the compose volume mount (or run unchanged — missing config degrades to "not configured"), drop a real `providers.json` in place.
3. Rollback: revert the release. Pre-existing `.summary` files are inert (ignored by the list, read endpoints gone); no cleanup needed.
4. Version: minor bump via `uv version --bump minor` before archive, per repo convention.

## Open Questions

- The exact fixed summarization instruction wording (topic / key points / conclusion, in the transcript's language) will be settled at implementation time; it does not change any spec scenario (tests assert shape, not wording).
- Whether the operator prefers 120 s or a larger default `SUMMARY_TIMEOUT` once they have observed real backend latency — tunable post-deploy via env var, no code change.
