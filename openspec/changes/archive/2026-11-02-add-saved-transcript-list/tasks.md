# Tasks

## 1. Read-side module `app/library.py`

- [x] 1.1 Implement `list_transcripts()` (list the transcript directory: `.txt` regular files only, entries with name/size/ISO-8601-UTC modified, sorted most-recent-first, `[]` on missing/non-directory/unreadable) and its unit tests in `tests/test_transcript_library.py` (mtimes pinned with `os.utime`), and verify `python -m pytest tests/test_transcript_library.py -q -k "list or missing or non_directory or empty"` passes (T-TRANSCRIPT-LIBRARY-001…006)
- [x] 1.2 Implement `read_transcript(name)` with the validation order from design decision 3 (structural reject → `.txt` check → resolve-and-contain → regular-file check), returning `(ok, text)` and the exact file content, plus its unit tests, and verify `python -m pytest tests/test_transcript_library.py -q -k "read"` passes, including the traversal (400) and unknown/non-`.txt` (404) cases (T-TRANSCRIPT-LIBRARY-007, 009, 010, 011, 012, 013)

## 2. API endpoints (`app/main.py`)

- [x] 2.1 Add `GET /api/transcripts` (runs `list_transcripts` via `asyncio.to_thread`, returns `{"transcripts": [...]}`) and its endpoint tests, and verify `python -m pytest tests/test_transcript_library.py -q -k "endpoint_list"` passes with the 200 envelope shape for populated, empty, and missing directories (T-TRANSCRIPT-LIBRARY-001…006 at endpoint level)
- [x] 2.2 Add `GET /api/transcripts/{name}` (runs `read_transcript` via `asyncio.to_thread`; maps structural reject to 400, missing/non-`.txt` to 404, success to `{"name", "text"}`) and its endpoint tests, and verify `python -m pytest tests/test_transcript_library.py -q -k "endpoint_read"` passes (T-TRANSCRIPT-LIBRARY-007, 010…013 at endpoint level, including a percent-encoded Unicode name)
- [x] 2.3 Add the cross-cutting endpoint tests: fetch-then-read round-trip (fetch text + one trailing newline), list and read during an in-flight fetch (delayed chain stub held in a background thread; both the list and the read return 200, no `BUSY`, chain not invoked for either), and read-does-not-modify, and verify `python -m pytest tests/test_transcript_library.py -q -k "roundtrip or in_flight or modify"` passes (T-TRANSCRIPT-LIBRARY-008, 014, 015)

## 3. Web UI (`app/static/`)

- [x] 3.1 Add the Saved transcripts section to `index.html` and its styles to `style.css` (header with count + refresh button, scrollable list, empty state), and verify the e2e tests pass: `python -m pytest tests/e2e/test_ui.py -q -k "saved_list_shows or saved_list_empty_state or saved_list_scrolls"` (T-TRANSCRIPT-LIBRARY-016, 018, 019)
- [x] 3.2 Wire the list data in `app.js` (load on page load, reload after each successful fetch, manual refresh; rows carry the real name in `data-name` with a CSS-prettified label; all fetched strings via `textContent` only), and verify `python -m pytest tests/e2e/test_ui.py -q -k "saved_list_prettified or saved_list_updates or saved_list_manual_refresh or saved_list_does_not_poll"` passes, including asserting the request targets the real file name and that no list request is issued without a fetch or refresh (T-TRANSCRIPT-LIBRARY-017, 020, 026, 027)
- [x] 3.3 Implement click-to-display (row click loads the transcript into the existing `#result` panel, name as title, Copy enabled; 404/network failures show the existing error banner and keep the page usable), and verify `python -m pytest tests/e2e/test_ui.py -q -k "click_saved or saved_transcript_html or click_deleted"` passes, including the seeded transcript containing `<script>` markup rendered as plain text (T-TRANSCRIPT-LIBRARY-021, 022, 023)
- [x] 3.4 Implement the Download button (client-side Blob + transient `<a download>` using the real file name; enabled only when the displayed transcript came from the saved list, disabled for not-yet-saved fetches), and verify `python -m pytest tests/e2e/test_ui.py -q -k "download"` passes with the downloaded bytes equal to the seeded file's content, over both the normal page and the plain-HTTP page fixture (T-TRANSCRIPT-LIBRARY-024, 025)

## 4. Documentation and integration

- [x] 4.1 Update the README (storage section gains a browse/download paragraph; smoke test gains a `GET /api/transcripts` step) and verify the documented curl command runs as written against a running local instance
- [x] 4.2 Run the full suites — `python -m pytest tests/ -q --ignore=tests/e2e` and `python -m pytest tests/e2e/ -q` — and verify both complete with exit code 0 and no skipped tests

## Workflow follow-up

- Validate the change (`openspec validate`) after the project's review requirements are satisfied.
- Archive the change once implementation is verified; archiving folds the `transcript-library` delta into the main specs.
