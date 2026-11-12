# Proposal

## Why

Today the set of selectable models is fixed by `providers.json`, which is mounted read-only and edited by the operator. On the local lab network models are added, swapped, and retired frequently, so every change means editing a file over SSH and reloading the page. The picker should be able to grow with the backends without touching the operator-owned config.

## What Changes

- Introduce a writable provider-overrides store (`provider_overrides.json` in the transcript directory) holding model ids added through the UI. The file config stays operator-owned and read-only; overrides never define providers, base URLs, or keys.
- The effective provider list becomes `providers.json` providers/models followed by non-duplicate overlay models. `GET /api/providers` and `POST /api/summarize` both use the merged list, so an added model is immediately selectable and usable.
- Add `POST /api/providers/{id}/models` for manual model-id entry and `DELETE /api/providers/{id}/models` (model id in the JSON body) to remove only overlay-added models; file-provided models are immutable from the UI.
- Add `GET /api/providers/{id}/available-models` to discover models live from an existing provider's OpenAI-compatible `GET {baseURL}/models`, with bounded timeout and secret-free error reporting.
- Add a new always-visible **Summarization models** section (provider list with model counts and a per-provider manage panel) for manual add, discovery, and removal.
- Add the `INVALID_MODEL` and `MODEL_NOT_REMOVABLE` error codes and bounded validation (trimmed non-empty printable id, length cap, per-provider addition cap). Add structured log events for model add/remove and discovery failure, with log-viewer formatters.
- No breaking changes: a missing overrides file means the previous behavior exactly, and every existing endpoint keeps its response shape apart from the merged model lists and the new `addedModels` field on `GET /api/providers`.

## Capabilities

### New Capabilities

- `summarization-model-management`: the writable overrides store, the add/remove/discover endpoints, merge precedence, validation and bounds, the UI model-management section, and its logging/error behavior.

### Modified Capabilities

- `transcript-summarization`: the provider configuration read and the secret-free provider listing now include overlay-added models, and the summarize endpoint validates provider/model ids against the merged list.

## Impact

- New `app/provider_overrides.py` (FastAPI-free read/atomic-write of `provider_overrides.json`, plus the `apply_overrides` merge helper) and `app/model_discovery.py` (FastAPI-free live model discovery).
- `app/main.py` — three new endpoints, and existing summarize validation moves to the merged config.
- `app/errors.py` — `INVALID_MODEL` and `MODEL_NOT_REMOVABLE`.
- `app/static/index.html`, `app/static/app.js`, `app/static/style.css` — the new section and panel; all inserted text via `textContent`.
- Tests: new unit tests for overrides/merge/validation/discovery parsing, new e2e tests for add, discover, remove, and picker refresh.
- Docs (`docs/providers.md`, `docs/summarize.md`, README summarization section) and generated docs.
- User-visible change: bump the minor version (`uv version --bump minor`) before archiving.
