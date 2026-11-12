# Design

## Context

See `proposal.md` — Why. Current state that shapes the approach:

- `app/providers.py` reads `providers.json` per request into frozen `Provider` / `ProviderConfig` dataclasses and never writes. The file is mounted read-only in compose and may hold API keys.
- `GET /api/providers` strips `apiKey`/`baseURL`; the picker is read-only and loaded once on page load.
- `POST /api/summarize` re-validates the provider/model pair against the config it just read, which is the SSRF guard: the server only sends to configured base URLs.
- `app/settings.py` already demonstrates the project's writable-JSON pattern (per-request read, sibling temp file + `os.replace`, tolerate missing/malformed as defaults).
- The app has no authentication; settings writes are already trusted to anyone who can reach the port. The new endpoints must not widen what an unauthenticated client can reach beyond operator-configured base URLs.
- E2E tests replace HTTP seams (`app/summarize._call_chat_completions`) so the real logic runs against deterministic stubs.

## Goals / Non-Goals

**Goals:**
- Add/remove model ids for existing providers, persisted across restarts, without touching `providers.json`.
- Discover models live from a configured provider's `/models`, with manual entry as the fallback.
- Keep the secret and SSRF boundaries exactly as they are today.
- Keep all writes atomic and tolerant of a missing/malformed overlay.

**Non-Goals:**
- Defining providers, base URLs, or keys from the UI.
- Changing the OpenAI-compatible request shape or adding other protocols.
- Persisting the last-selected provider/model across reloads.
- Authentication/authorization changes, or multi-process coordination.
- Pruning overlay entries for providers that disappear from `providers.json`.

## Decisions

### D1: A separate writable overlay, not a writable `providers.json` or an extended `settings.json`

`provider_overrides.json` lives in the transcript directory (`transcript_dir()`), shaped `{"<providerId>": ["model-id", ...]}`. Missing → no additions; unreadable (OSError) or malformed → log `provider_overrides_load_failed` and treat as no additions.

- *Rejected: make `providers.json` writable.* It holds secrets, the read-only mount is a deliberate safety property, and rewriting an operator-authored file would clobber formatting/comments and race manual edits.
- *Rejected: extend `settings.json`.* `save_settings()` is a blind overwrite of the whole file; adding model data would force a read-merge-write refactor of an unrelated feature and couple every auto-summarize toggle to provider data.
- Consequence: the transcript directory now holds two app-managed JSON files. The same "don't publish/sync this directory" assumption already applies because it holds `settings.json` and transcripts.
- The transcript listing is unaffected: `list_transcripts()` in `app/library.py` lists only `.txt` files, so the overlay file never appears in `GET /api/transcripts`.

### D2: Effective config = file config plus overlay, with provenance carried on `Provider`

`app/provider_overrides.py` (FastAPI-free) owns the overlay read/write and a pure `apply_overrides(config, overrides) -> ProviderConfig`:

- Provider set comes **only** from `ProviderConfig.providers`; overlay keys for unknown providers are ignored (and left on disk).
- `models` = file models in order, then overlay ids not already present, preserving first occurrence.
- `Provider` gains `added_models: tuple[str, ...] = ()`, populated with the overlay ids actually used. This lets `GET /api/providers` return `addedModels` without a second endpoint or secrets.
- `main.py` composes `apply_overrides(load_providers(), load_overrides())` in both `GET /api/providers` and `POST /api/summarize`. Keep `load_providers()` file-only so its existing tests and contract are untouched.

*Rejected: fold merging into `providers.py`.* It would turn a pure reader into a reader/writer and couple it to the transcript directory; an explicit composition in the endpoints keeps both modules single-purpose.

### D3: Add/remove are read-modify-write under a process lock, with atomic replace

Both endpoints run in worker threads via `asyncio.to_thread`. `provider_overrides.py` guards read-modify-write with a module-level `threading.Lock`, writes a sibling temp file, then `os.replace` (same pattern as `save_settings`). A successful add emits `provider_model_added` (info: provider, model) and a successful removal emits `provider_model_removed` (info: provider, model); neither event carries secrets. A write failure logs `provider_overrides_save_failed`, cleans up the temp file, and returns `WRITE_FAILED` with no partial state.

- The app runs a single uvicorn process (no `--workers`), so a process-local lock is sufficient; multi-process deployment would need an OS file lock (documented, not implemented).
- Only overlay ids are removable. If the id is in the effective list but not in the overlay, it came from the file → `MODEL_NOT_REMOVABLE`. If it is in neither → `NOT_FOUND`.

### D4: `DELETE` carries the model id in the body

Model ids routinely contain `/` (Hugging Face style, e.g. `meta-llama/Llama-3`). A `{model}` path segment would either fail routing or depend on `%2F` decoding that Starlette does not do consistently. Both add and remove therefore use `POST`/`DELETE /api/providers/{provider_id}/models` with `{"model": "..."}` in the body. Provider ids stay in the path; they are operator-chosen config keys and are expected URL-safe, matching how the summarize endpoint already treats them as opaque handles.

### D5: Validation and bounds live in `provider_overrides.py`

- Trim; must be non-empty; at most 200 characters; free of control characters; at most 50 overlay additions per provider.
- A non-object body or missing `model` → 400 `INVALID_BODY`; a bad id or cap overflow → 400 `INVALID_MODEL`.
- Adding an id already in the effective list is an idempotent 200 (file-provided ids are simply left alone).
- New errors in `app/errors.py`: `InvalidModelError` (`INVALID_MODEL`, 400) and `ModelNotRemovableError` (`MODEL_NOT_REMOVABLE`, 400). Reuse `InvalidProviderError`, `ProviderError`, and the existing `WRITE_FAILED` response shape.

### D6: Discovery is a separate module with its own bounded executor and seam

`app/model_discovery.py` (FastAPI-free) exposes `list_models(provider, timeout=None) -> list[str]` and a module-level `_get_provider_models(url, api_key, timeout)` seam (mirroring `_call_chat_completions` so e2e can stub it below the logging wrapper).

- `requests.get(base_url.rstrip("/") + "/models")`, bearer header only when `apiKey` is configured, timeout from `MODEL_DISCOVERY_TIMEOUT` (default 15 s), same failure taxonomy as summarization (`unreachable`, `timeout`, `http_error`, `malformed_response`).
- Parse `data` as a list; keep only dict entries whose `id` is a non-empty string; dedupe preserving order; cap at 200 ids.
- Failures raise a narrow `ModelDiscoveryError` and log `provider_models_refresh_failed` with provider, reason, and a safe detail (type name for transport errors — never the URL). Success logs `provider_models_refreshed` (provider, count, duration_ms).
- Discovery runs on a dedicated `ThreadPoolExecutor(max_workers=2)` rather than the summarize pool: a 120 s summarize must not block a fast `/models` call, and a hanging discovery must not starve summarization.
- The endpoint resolves the provider against the file config first; the overlay never changes which base URL is contacted.

*Rejected: auto-add every discovered model.* Discovery is advisory; the operator explicitly adds, so an unexpected backend does not silently expand the picker.

### D7: The UI gets an always-visible section with a per-provider panel

`index.html` gains a `#model-management` section outside `#result`, between the error banner and the result section, with a heading, an empty state, and a container that `app.js` fills per provider. Each provider row shows display name, effective model count, and a Manage button. The panel contains:

- manual id input + Add (form submit),
- a "Refresh from backend" button that renders discovered ids with Add buttons (already-present ids disabled),
- the provider's `addedModels` with Remove buttons; file models are listed without a Remove action.

Rendering is build-with-`createElement`/`textContent` only (no `innerHTML`), per the project rule. `error-banner` is reused for failures, with new `ERROR_MESSAGES` entries for `INVALID_MODEL`, `MODEL_NOT_REMOVABLE`, `NOT_FOUND`, and a discovery-specific `PROVIDER_ERROR` override so a failed refresh does not read as a failed summary. The log-viewer's `LOG_FORMATTERS` in `app.js` gains one-line humanized formatters for the new events (`provider_model_added`, `provider_model_removed`, `provider_models_refreshed`, `provider_models_refresh_failed`, `provider_overrides_load_failed`, `provider_overrides_save_failed`).

### D8: Picker refresh and session selection

`loadProviders()` gains an optional preferred `{provider, model}`. After a successful add it reloads and selects the new pair; after a successful removal it reloads the provider list and re-renders the section, falling back to `defaultOptionIndex()` if the removal dropped the current selection. No last-selection persistence — after a reload the existing default rule (`default` provider's first model) still applies.

### D9: Trust model unchanged, explicitly

The new write endpoints are as unauthenticated as `POST /api/settings`. They cannot introduce a base URL, so the SSRF surface stays "operator-configured URLs". They can only cause the server to address an operator-approved backend with a different model string, bounded by the caps in D5. README/docs state this trust assumption rather than implying the UI is an admin surface.

## Test Strategy

- Unit tests (pytest, `tmp_path`, no FastAPI, no network): `tests/test_provider_overrides.py` covers overlay read/merge/validation (tasks 1.2–1.3); `tests/test_model_management.py` covers add/remove/discovery logic (tasks 2.2–2.3, 3.1–3.3), with the discovery HTTP seam `_get_provider_models` stubbed, mirroring the existing `_call_chat_completions` pattern.
- Endpoint tests through Starlette's TestClient against the real app: status codes and error codes, rejection precedence, and no fetch-chain interaction (tasks 2.2–2.3, 3.2, 4.1–4.2).
- E2E (Playwright, headless Chromium, in-process uvicorn with the fetch chain and summarize seam stubbed): `tests/e2e/test_model_management.py` (task 5.3).
- Every spec scenario carries a Test Requirement block (id/file/command/pass); the blocks' `python -m pytest …` commands are executed through `uv run` from the repo root. E2E prerequisite: `uv run python -m playwright install chromium`. Pass criterion for every block: exit code 0, no skipped tests. The integration gate is the full non-e2e and e2e suites passing with no skips (tasks 6.1–6.2).

## Risks / Trade-offs

- [Unauthenticated LAN client can add model ids] → Bounded id length, 50 per provider, no secrets/base URLs added; same trust level as existing settings writes; documented. Not treated as a vulnerability in this personal-tool threat model.
- [Lost update between concurrent adds] → Module lock around read-modify-write plus atomic replace; single-process server today. Multi-process would need a file lock (documented as a non-goal).
- [Discovery endpoint absent or non-standard] → Manual entry always works; discovery failures show a distinct message and never alter existing models.
- [Provider `/models` is slow or hangs] → Dedicated 15 s timeout and dedicated executor, so other endpoints and summaries stay responsive.
- [Overlay drifts after a provider is removed from `providers.json`] → Orphan entries are ignored and retained; re-adding the provider restores them. No destructive prune.
- [Model ids containing `/` break routing] → DELETE takes the id in the body (D4).
- [Header section crowds the page] → The section is below the fetch form, outside the result toolbar, so it does not interact with the recently fixed result-header layout.
- [Behavior change to `POST /api/summarize` validation] → The merged config is the single source for both listing and validation; dedicated tests cover added-model acceptance and unchanged `INVALID_PROVIDER` behavior.

## Migration Plan

No data migration. Deploy the new image; `provider_overrides.json` is created on the first successful add inside the already-mounted transcript directory. An older image ignores the file, so rollback is simply redeploying the previous image (and optionally deleting the overlay). `providers.json` and its mount are unchanged.
