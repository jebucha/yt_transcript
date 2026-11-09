# Tasks

## 1. Settings backend

- [x] 1.1 Create `app/settings.py` per design D3 (FastAPI-free: `settings_path()` via `persist.transcript_dir()`, per-request `load_settings()` with safe off-default and one `settings_load_failed` log event for unreadable/malformed files without echoing contents, `save_settings()` writing sibling temp file + `os.replace` and returning a success flag) and verify with direct module tests against `tmp_path` covering the load defaults, per-request re-read, and atomic write.
- [x] 1.2 Add `GET /api/settings` to `app/main.py` as a thin wrapper over `load_settings` via `asyncio.to_thread` (no semaphore, no fetch chain) and verify the API tests T-APP-SETTINGS-001–004 in `tests/test_settings.py` pass (`uv run python -m pytest tests/test_settings.py -q`).
- [x] 1.3 Add `POST /api/settings` per design D3 (body validated first: non-object / missing / non-boolean `autoSummarize` → 400 `INVALID_BODY` with no filesystem access; write failure → 500 `WRITE_FAILED` + `settings_save_failed` log; success → 200 echo) and verify the API tests T-APP-SETTINGS-005–007 pass.
- [x] 1.4 Verify settings-file isolation: implement and pass T-APP-SETTINGS-008 (`settings.json` excluded from `GET /api/transcripts`) and T-APP-SETTINGS-009 (settings endpoints proceed during an in-flight fetch and never invoke the fetch chain; stub pattern from `test_summarize_during_in_flight_fetch_succeeds`).

## 2. Settings UI control

- [x] 2.1 Add the "Auto-summarize" checkbox and a hidden subdued note element next to the provider picker in `app/static/index.html`, with muted-note styling in `app/static/style.css`, and verify both elements are present and hidden/disabled per markup in the Playwright harness.
- [x] 2.2 In `app/static/app.js`, load `GET /api/settings` on page load (mirror `loadProviders`), reflect `autoSummarize` in the checkbox, POST changes optimistically and revert the checkbox on 500/network failure (design D6), disable the checkbox when no providers are configured and while `summarizing`, and wire it into `updateSummarizeEnabled`; verify e2e tests T-TRANSCRIPT-SUMMARIZATION-043–045 pass (`uv run python -m pytest tests/e2e/test_auto_summarize.py -q`).

## 3. Auto-fire and skip-and-show

- [x] 3.1 Extract a shared `defaultSelection()` from `renderProviderPicker`'s default pre-selection (design D4) and refactor `doSummarize` to take an `auto` flag reusing the same busy state (button, picker, and checkbox disabled + spinner), `summarizing` guard, and `displayToken` staleness rule; verify the existing `tests/e2e/test_summarization.py` suite still passes unchanged.
- [x] 3.2 Hook the auto path into the fetch-success flow only (`renderResult`, not `displaySavedTranscript`): when the checkbox is on, first attempt the existing saved-summary read for the derived name (reuse `loadSavedSummary`) — show it on success and skip (no summarize call), else auto-fire `doSummarize(true)` with the default target; verify e2e tests T-TRANSCRIPT-SUMMARIZATION-046–051 pass.

## 4. Subdued failure handling

- [x] 4.1 Route every auto-summarize failure shape (`PROVIDER_ERROR`, `NOT_CONFIGURED`, `INVALID_PROVIDER`, `INPUT_TOO_LONG`, network error, empty-`summary` 200) to the subdued note via `textContent` — never `showError`, panel stays hidden, manual Summarize remains enabled — leaving the manual banner path untouched, and note the accepted consecutive-fetch drop (design D7) in a code comment; verify e2e tests T-TRANSCRIPT-SUMMARIZATION-052–054 pass.

## 5. Integration and docs

- [x] 5.1 Run the full non-e2e suite (`uv run python -m pytest tests/ -q --ignore=tests/e2e`) and the e2e suite (`uv run python -m pytest tests/e2e/ -q`) and verify both are green with no skipped tests.
- [x] 5.2 Document the `/api/settings` endpoints and the auto-summarize toggle in `docs/` following the existing page conventions (see `docs/providers.md`), and verify the pages render with working links via `docs/index.md`.

## Workflow follow-up

- Validate in a fresh session with `/opsx-validate` (a model that did not write the code).
- Bump the minor version with `uv version --bump minor` (user-visible change) before archiving.
- Archive the change with `/opsx-archive` once validation passes.
