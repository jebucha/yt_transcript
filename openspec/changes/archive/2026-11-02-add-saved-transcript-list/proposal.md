# Proposal

## Why

Transcript persistence is write-only: every successful fetch is saved to a `.txt` file in the transcript directory, but nothing in the app can read them back. An operator who saved transcripts over time has to open the bind-mounted host directory to find them. The loop should be closeable from the UI: see what is saved, read it, and take a copy.

## What Changes

- Two new read-only API endpoints over the existing transcript directory:
  - `GET /api/transcripts` — list of persisted transcripts (file name, size, last-modified time), most recent first.
  - `GET /api/transcripts/{name}` — the text of one persisted transcript.
- Path-traversal defense on the read side: the client-supplied name must be a plain `.txt` file name that resolves inside the transcript directory.
- A new "Saved transcripts" section in the web UI: a scrollable, most-recent-first list of saved transcript names (prettified for display only). Clicking a name renders the transcript into the existing result panel, where Copy keeps working; a new Download button saves the transcript as a `.txt` file on the user's machine.
- The list loads on page load, reloads after a successful fetch, and has a manual refresh affordance. No polling.
- Missing or unreadable transcript directory is a normal condition: the list endpoint returns an empty list, and the UI shows an empty state — mirroring the best-effort philosophy of the write side.
- No changes to the on-disk contract: still one plain-text `.txt` file per transcript, no metadata sidecars. No changes to fetch behavior, error taxonomy, or the single-flight semaphore (read endpoints are unaffected by it).

## Capabilities

### New Capabilities

- `transcript-library`: read access to persisted transcripts — the list and single-transcript endpoints with traversal-safe name handling, empty-directory behavior, and the web UI section that displays and downloads saved transcripts.

### Modified Capabilities

None. `transcript-persistence` (write side), `transcript-retrieval`, `web-interface` (the pre-existing fetch/display/copy flows are untouched), and `structured-logging` keep their existing requirements.

## Impact

- `app/main.py`: two new read-only API routes.
- `app/persist.py` (or a small read-side module next to it): listing and single-file read helpers, kept FastAPI-free and testable against `tmp_path`, reusing `transcript_dir()`.
- `app/static/index.html`, `app/static/app.js`, `app/static/style.css`: the Saved transcripts section, click-to-display, Download button, refresh behavior (vanilla JS, no framework, `textContent` only for fetched content).
- Tests: new API/unit tests for the read endpoints (tmp transcript directory, traversal cases, missing directory) and e2e tests for the list UI, following the existing `tests/` and `tests/e2e/` layout.
- `README.md`: the storage section gains a browse/download paragraph and the smoke test gains a `GET /api/transcripts` step.
- No new dependencies, no new services, no compose or image changes.
