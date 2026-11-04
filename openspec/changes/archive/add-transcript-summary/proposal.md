# Proposal

## Why

Fetched transcripts are long (10k–30k tokens for hour-plus videos), and reading a full transcript to learn what a video is about is exactly what a summary exists to avoid. The operator already runs several OpenAI-compatible LLM backends locally (Radai, LM Studio, local GGUF servers), so summarization should be a one-click feature whose backend is chosen from a configurable list of providers — with transcript text sent only to the operator-configured backends and no new Python dependency.

## What Changes

- **Summarize feature in the UI**: a provider/model picker plus a "Summarize" button in the result actions (next to Copy/Download), and a summary panel with its own copy button. The button summarizes whatever transcript is currently displayed — a freshly fetched one or a saved one clicked from the library. The summary clears whenever a new transcript is displayed.
- **New `providers.json` config file** (default path, overridable via `PROVIDERS_CONFIG` env var): a `provider` map in the same shape the operator already uses (per provider: display `name`, `options.baseURL`, optional `options.apiKey`, `models` map). The app reads the file per request; API keys and base URLs are server-side only.
- **New endpoints**: `GET /api/providers` (provider id, display name, model ids, and the default selection — never keys or base URLs), `POST /api/summarize` (displayed text + transcript file name + provider/model ids → summary text, output bounded at 16384 tokens — headroom for thinking models whose reasoning shares that budget), and `GET /api/transcripts/{name}/summary` (load a previously saved summary, 404 when absent).
- **Fetch response gains the derived file name**: `POST /api/transcript` responses include a `name` field (the transcript's persisted `.txt` file name), so a freshly fetched transcript also has a trustworthy file name client-side. Additive, backward-compatible.
- **Summary persistence**: a successful summarization saves the summary as `<transcript name>.summary` (deliberately not `.txt`) in the transcript directory, next to the transcript. The saved-transcript list is unaffected because it only lists `.txt` files.
- **New error codes** in the existing taxonomy: `NOT_CONFIGURED` (503, no usable providers), `INVALID_PROVIDER` (400, unknown provider/model id or structurally invalid name), `PROVIDER_ERROR` (502, backend unreachable/failed/timed out), `INPUT_TOO_LONG` (400, transcript text over the input cap).
- **Structured logging**: `summary_completed` / `summary_failed` events (provider, model, outcome/reason, duration, char counts) plus `summary_save_failed` / `config_load_failed` error events for failed saves and malformed config — never transcript or summary content, config file contents, or keys — with dedicated humanized formatters in the log panel.
- **Deployment**: `docker-compose.yml` mounts the config file into the container; `PROVIDERS_CONFIG` and a summary-call timeout override (`SUMMARY_TIMEOUT`) via env vars, following the existing `TRANSCRIPT_DIR` pattern (app-read env vars use the singular spelling; compose maps them host-side).
- **No new Python dependencies**: providers speak the OpenAI-compatible HTTP protocol at `{baseURL}/chat/completions`, called with the already-declared `requests` dependency from a worker thread.

## Capabilities

### New Capabilities

- `transcript-summarization`: provider configuration file and its per-request reading; the secret-free provider listing endpoint; the summarize endpoint with provider/model id validation and OpenAI-compatible chat-completions invocation; summary file persistence alongside the transcript and its read endpoint; the UI (provider picker, Summarize button with loading state, summary panel, copy-summary, clear-on-new-transcript); and the feature's error codes and their display.

### Modified Capabilities

- `transcript-retrieval`: the successful-fetch response metadata gains the derived transcript file name (`name`), so the client can reference the just-fetched transcript by its persisted file name.
- `structured-logging`: new requirements — each summarization is logged as a `summary_completed` (info) or `summary_failed` (error) event carrying provider, model, outcome or machine-readable failure reason, duration, and char counts; failed summary saves and malformed config loads are logged as `summary_save_failed` / `config_load_failed` error events. No log carries transcript/summary content, config file contents, or credentials.
- `log-viewer`: the set of known event types with dedicated humanized formatters gains `summary_completed`, `summary_failed`, `summary_save_failed`, and `config_load_failed`.

## Impact

- **Code**: new `app/providers.py` (config reading/validation, FastAPI-free, testable against `tmp_path`) and `app/summarize.py` (provider invocation and summary file save/read, FastAPI-free, testable with a mocked HTTP layer), following the `app/library.py` / `app/persist.py` split. New error classes in `app/errors.py`. New routes and UI markup/behavior in `app/main.py`, `app/static/index.html`, `app/static/app.js`, `app/static/style.css`. E2E tests stub the provider call seam, matching the existing stubbed-fetch-chain harness pattern.
- **API**: three new endpoints; `POST /api/transcript` response gains one additive field. No existing endpoint's contract changes.
- **Dependencies**: none added (`requests` is already a direct dependency).
- **Deployment**: a keyless `providers.json.example` in the repo root (the real `providers.json` is git-ignored, host-mounted in compose); two new optional env vars (`PROVIDERS_CONFIG`, `SUMMARY_TIMEOUT`).
- **Data**: new `.summary` files in the transcript directory; existing transcripts, the saved list, and downloads are unaffected.
