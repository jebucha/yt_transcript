# Tasks

## 1. Provider overrides store and merge

- [x] 1.1 Add an `added_models: tuple[str, ...] = ()` field to `Provider` in `app/providers.py`, leaving `_parse_provider` populating it empty; verify `uv run python -m pytest tests/test_transcript_summarization.py -q` still passes and providers read from the file have an empty `added_models`.
- [x] 1.2 Implement `app/provider_overrides.py` (FastAPI-free): `overrides_path()`, tolerant `load_overrides()` with `provider_overrides_load_failed` logging, `apply_overrides(config, overrides)` (file order first, appended non-duplicates, provenance in `added_models`), atomic `_write_overrides()` with `provider_overrides_save_failed` logging, a module-level lock, and the model-id validation helpers (`MAX_MODEL_ID_CHARS = 200`, `MAX_ADDED_PER_PROVIDER = 50`); verify `uv run python -m pytest tests/ -q --ignore=tests/e2e` still passes (dedicated tests for the module arrive with 1.3).
- [x] 1.3 Add `tests/test_provider_overrides.py` covering merge order, dedupe, overlay-cannot-add-provider, missing file, malformed file logging, edit-without-restart, and exclusion from the transcript list; verify `uv run python -m pytest tests/test_provider_overrides.py -q` passes with no skips (T-SUMMARIZATION-MODEL-MANAGEMENT-001 .. 007).
- [x] 1.4 Update `docs/providers.md` to document `provider_overrides.json`, merge precedence, and the read-only file contract, and add the `docs/provider_overrides.md` module page per the docs convention; verify the documented file name and merge rules appear in the generated pages after task 6.3.

## 2. Error codes and add/remove endpoints

- [x] 2.1 Add `InvalidModelError` (`INVALID_MODEL`, 400) and `ModelNotRemovableError` (`MODEL_NOT_REMOVABLE`, 400) to `app/errors.py`; verify `uv run python -m pytest tests/test_error_taxonomy.py -q` passes.
- [x] 2.2 Implement `POST /api/providers/{provider_id}/models` and `DELETE /api/providers/{provider_id}/models` (model id in the JSON body) in `app/main.py`, running overlay writes via `asyncio.to_thread`, validating the provider against the file config, returning the effective model list, and mapping the documented error codes; verify `uv run python -m pytest tests/ -q --ignore=tests/e2e` still passes (dedicated endpoint tests arrive with 2.3).
- [x] 2.3 Add add/remove/validation tests to `tests/test_model_management.py` covering persistence, idempotent add, unknown provider, write failure, fetch-chain independence, blank/overlong/control-character ids, the 50-addition cap, invalid body, removal of overlay models, refusal to remove file models, absent model, and add/remove log events; verify `uv run python -m pytest tests/test_model_management.py -q` passes with no skips (T-SUMMARIZATION-MODEL-MANAGEMENT-008 .. 022, 042, 044).
- [x] 2.4 Update the error-model sections in `README.md` and `docs/errors.md` with `INVALID_MODEL` and `MODEL_NOT_REMOVABLE`; verify both files name the codes and their HTTP statuses.

## 3. Model discovery

- [x] 3.1 Implement `app/model_discovery.py` (FastAPI-free) with `list_models(provider, timeout=None)`, the replaceable `_get_provider_models` seam, `MODEL_DISCOVERY_TIMEOUT` resolution, OpenAI-compatible `data[].id` parsing with dedupe/cap, the failure taxonomy, and the `provider_models_refreshed` / `provider_models_refresh_failed` events; verify `uv run python -m pytest tests/ -q --ignore=tests/e2e` still passes (dedicated discovery tests arrive with 3.3).
- [x] 3.2 Add `GET /api/providers/{provider_id}/available-models` in `app/main.py`, resolving the provider against the file config and running discovery on a dedicated bounded executor; verify `uv run python -m pytest tests/ -q --ignore=tests/e2e` still passes (the discovery endpoint tests arrive with 3.3).
- [x] 3.3 Extend `tests/test_model_management.py` with discovery tests covering id parsing, auth-header presence/absence, unknown provider, backend failure → 502, secret-free response, fetch-chain independence, discovery-failure logging, and the no-secrets log assertion; verify `uv run python -m pytest tests/test_model_management.py -q` passes with no skips (T-SUMMARIZATION-MODEL-MANAGEMENT-023 .. 028, 043, 045).
- [x] 3.4 Add `docs/model_discovery.md` (and its cross-links from `docs/providers.md` / `docs/summarize.md`) describing the `/models` call, timeout, failure reasons, and the manual fallback, and register both new module pages in the `PAGES` list in `docs/generate.py` (`app/model_discovery.py` → `model_discovery.md` → `model_discovery.html`, and `app/provider_overrides.py` → `provider_overrides.md` → `provider_overrides.html` from task 1.4); verify `uv run python docs/generate.py` renders both pages (not skipped), with content re-checked in task 6.3.

## 4. Listing and summarize integration

- [x] 4.1 Update `GET /api/providers` to return `addedModels` and update `POST /api/summarize` to validate against the merged config; verify `uv run python -m pytest tests/test_transcript_summarization.py -q` passes.
- [x] 4.2 Add tests to `tests/test_transcript_summarization.py` for added models appearing after file models, `addedModels` provenance, and an added model being accepted by summarize; verify those new tests pass with no skips (T-TRANSCRIPT-SUMMARIZATION-056 .. 058).
- [x] 4.3 Update the README "Summarization" section to explain adding/removing models in the UI, the overlay file, and the unchanged secret/SSRF boundary; verify the section names the overlay and the trust assumption.

## 5. Model-management interface

- [x] 5.1 Add the always-visible `#model-management` section (heading, provider list container, empty state) to `app/static/index.html` outside `#result`, plus its styles in `app/static/style.css`; verify the page loads with the section visible and the empty state shown when no providers are configured.
- [x] 5.2 Implement `app/static/app.js` rendering and actions: per-provider rows with counts, manage panel (manual add, discovery with Add buttons, added-model Remove buttons, no Remove for file models), provider-list reload with preferred selection, picker refresh, error-banner messages for `INVALID_MODEL` / `MODEL_NOT_REMOVABLE` / `NOT_FOUND` / discovery failure, and log-viewer formatters for the new events; verify all inserted content uses `textContent` and the manual flows work against a local server.
- [x] 5.3 Add `tests/e2e/test_model_management.py` with the section visibility, provider/count listing, empty state, manual add, discovered add, removal, file-model immutability, markup-as-text, picker refresh/selection, and error-message scenarios; verify `uv run python -m pytest tests/e2e/test_model_management.py -q` passes with no skips (T-SUMMARIZATION-MODEL-MANAGEMENT-029 .. 041).

## 6. Integration and release checks

- [x] 6.1 Run the full non-e2e suite and verify it passes: `uv run python -m pytest tests/ -q --ignore=tests/e2e`.
- [x] 6.2 Run the full e2e suite and verify it passes: `uv run python -m pytest tests/e2e/ -q`.
- [x] 6.3 Regenerate the documentation site with `uv run python docs/generate.py` and verify the updated provider, discovery, error, and static pages are present.
- [x] 6.4 Bump the app version with `uv run uv version --bump minor` (user-visible change) and verify `pyproject.toml` and `uv.lock` reflect the new version.
- [x] 6.5 Manually smoke-test: add a model manually, discover and add one from a configured backend, remove an added model, confirm the picker updates, and confirm `provider_overrides.json` exists in the transcript directory.

## Workflow follow-up

- Run `/opsx-validate` in a fresh session with a model that did not write the code, then resolve any findings.
- Archive the change after validation and the version bump are complete.
