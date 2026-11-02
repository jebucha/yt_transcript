# Design

## Context

The write side is complete: `app/persist.py` provides the pure `derive_file_name`, the call-time `transcript_dir()` helper (reading `TRANSCRIPT_DIR`, default `/transcripts`), and the best-effort `save_transcript`; `app/main.py` awaits it after every successful fetch. Nothing on the read side exists — no endpoint lists or reads the files, and the UI (`app/static/`) only renders the just-fetched transcript. Requirements live in the `transcript-library` delta; this document covers how.

Constraints inherited from the existing specs: no build step, no framework, no CDN in the UI; all fetched content into the DOM via `textContent` only; the single-flight fetch semaphore governs the YouTube fetch chain and nothing else; the app never creates the transcript directory.

## Goals / Non-Goals

**Goals:**
- Close the loop: list saved transcripts, read one back byte-for-byte, display it in the existing panel, and download it.
- Keep the read side a thin, FastAPI-free, unit-testable module over the same `transcript_dir()` the write side uses.
- Make client-supplied names traversal-safe by construction, independently of the write side's name-safety guarantee.
- Stay best-effort and side-effect-free: an unusable directory is an empty list, never an error; reads never touch the fetch chain or the semaphore.

**Non-Goals:**
- Deleting, renaming, or otherwise mutating saved transcripts from the app.
- Storing metadata (original title, video ID, fetch time) — the on-disk contract stays one plain `.txt` per transcript, no sidecars.
- Pagination, search, or filters on the list.
- Automatic polling or cross-tab sync of the list.
- Structured log events for the read endpoints (they are quiet, low-frequency operator reads).

## Decisions

### 1. New module `app/library.py`, pure helpers, no FastAPI imports
- `list_transcripts() -> list[dict]` — lists the transcript directory, returns entries `{name, size, modified}` (ISO 8601 UTC `modified`), sorted most-recent-first, `.txt` regular files only. Returns `[]` for a missing, non-directory, or unreadable path.
- `read_transcript(name: str) -> tuple[bool, str]` — validates the name, reads the file, returns `(ok, text)` where `ok` is False for a structurally invalid name (rejected, HTTP 400) or a missing/non-`.txt` file (HTTP 404). `text` is the file's exact UTF-8 content.
- Reuses `persist.transcript_dir()` so read and write can never disagree on the directory.
- Alternative: put the helpers in `app/persist.py` — rejected: that module is spec'd as the *persistence* (write) capability; a separate module keeps the capability boundary clean and gives `tests/test_transcript_library.py` its own natural home, mirroring `tests/test_persistence.py`.
- Alternative: read the files straight in `main.py` endpoint bodies — rejected: the traversal validation and the empty-dir degradation are the richest test surface of the change and deserve pure-function tests without an app instance.

### 2. One endpoint serves display and download
`GET /api/transcripts/{name}` returns JSON `{name, text}`. The UI renders `text` into the existing panel *and* wraps the same response in a `Blob` for the download button. One wire format, one cache of state, no `Content-Disposition` branching on the server.
- Alternative: a second "raw file" endpoint with `Content-Disposition: attachment` — rejected: it duplicates the read path, forces two client code paths for the same data, and the client-side Blob download works identically over plain HTTP and HTTPS with no server involvement.

### 3. Traversal defense: structural reject + resolve-and-contain
Validation in `read_transcript`, in order:
1. Reject if the name is empty, equals `.` or `..`, contains `/` or `\`, or contains a `..` path component (checked on the raw string) → 400.
2. Reject if it does not end in `.txt` → 404 (not an error in structure; the store simply has no such transcript).
3. Resolve `transcript_dir() / name` and require the resolved path to be inside the resolved transcript directory (`Path.resolve()` + `is_relative_to`) → otherwise 404.
4. Require the resolved path to be a regular file → 404 otherwise.

Step 1 is the hard rule (client input); steps 3–4 are belt-and-braces (symlinks planted by the host owner are out of the threat model — that owner already has direct read access to the directory). The write side's "derived names never contain a separator" guarantee is *not* relied on: the read side defends itself because its input is client-supplied.

### 4. Threading and status codes
Both endpoints run their (small, blocking) filesystem work via `asyncio.to_thread`, matching the codebase's rule that no blocking I/O happens on the event loop (`save_transcript` does the same). Status mapping: structurally invalid name → 400; unknown/missing/non-`.txt` → 404; anything else 200. No new error-code entry in the `errors.py` taxonomy — these are plain HTTP statuses, not `TranscriptError`s, and the UI treats them with the existing generic error banner rather than a fetch-specific message.
- The endpoints do not touch the single-flight semaphore: a read during an in-flight fetch is a normal 200, and no read can ever produce `BUSY`.

### 5. Unusable directory degrades to an empty list
`list_transcripts` catches any listing failure (`NotADirectoryError`, `PermissionError`, missing dir, and friends) and returns `[]`. The UI then shows its empty state. This mirrors the write side's philosophy (a missing directory is an operator-config condition, not an application error) and is what makes the "app runs, persistence silently degraded" state visible in the UI instead of broken.
- Alternative: 503 with a message — rejected: it turns a normal operating condition into a red error state, and the read side has no log-channel obligation like the write side's `transcript_save_failed`.

### 6. UI: one section, reusing the result panel
- New section below `#result` in `index.html`: header ("Saved transcripts" + count + refresh button) over a `<ul>` with `max-height` (~40vh) and `overflow-y: auto`, matching the existing `.transcript-panel` treatment. Each row: a clickable name (a `<button>` styled as a list item — keyboard-accessible, no custom `<a>` semantics needed) and a right-aligned date.
- Row label: the real file name with a cosmetic prettify — replace `_` with spaces, strip the trailing `.txt` extension, and apply CSS `text-transform: capitalize`. The real name is kept in a `data-name` attribute and is what any request uses; the display string is never sent to the server.
- Click a row → `fetch('/api/transcripts/' + encodeURIComponent(name))` → render into the *existing* `#result` section: text into the panel, name as the title, language line hidden, Copy enabled (it already operates on `currentTranscript`). The row's real name also populates the Download button's target; for a freshly fetched (not-yet-clicked) transcript the Download button is disabled — the fetch response carries no derived file name, so the UI has no trustworthy name to use as the download target (the file itself is normally already saved by then: the fetch endpoint persists before responding).
- Error path (404 after a row was deleted, network failure) reuses the existing `#error-banner` with the generic message; the page stays usable.
- Refresh: list loads on page load, reloads after each successful fetch, and via the refresh button. No polling.
- All fetched strings (name, text) enter the DOM exclusively via `textContent` / `innerText` — the web-interface spec's no-HTML rule, same discipline as `renderResult`.
- Download: `new Blob([text], {type: "text/plain"})` + object URL + a transient `<a download="<real name>">` click. No HTTPS dependency, no server headers.
- Alternative: a sidebar/two-column layout — rejected: the page is a single 760px column by design; a second column adds layout complexity for a low-frequency operator feature. A modal — rejected: it is a third state to manage when the existing panel already renders transcripts identically.

### 7. API shape
- `GET /api/transcripts` → `200 {"transcripts": [{"name", "size", "modified"}, ...]}` (envelope object, not a bare array, so fields can be added later without a breaking change).
- `GET /api/transcripts/{name}` → `200 {"name", "text"}` | `400` | `404`.
- `modified` is the file mtime as an ISO 8601 UTC string; the UI renders it as a local date. Sorting is done server-side, so the UI never re-sorts.

### 8. Deployment and documentation
No Dockerfile, compose, or dependency changes: the endpoints read the same bind-mounted directory the write side already uses, and no new image capability is needed. README gains a short paragraph in the storage section (list/browse/download saved transcripts from the UI) and a smoke-test step for `GET /api/transcripts`.

## Test Strategy

- **Unit** — `tests/test_transcript_library.py` exercises `list_transcripts` / `read_transcript` directly against `tmp_path` with `TRANSCRIPT_DIR` pointed there via `monkeypatch` (same pattern as `test_persistence.py`): listing fields, mtime ordering (mtimes set explicitly with `os.utime` to avoid clock-granularity flakes), `.txt` filtering, empty/missing/non-directory degradation, traversal rejects, 404 cases, exact-content reads.
- **API-level** — same file, through `TestClient(create_app())` with the `FakeChain` + `monkeypatch.setattr(chain_mod, "default_chain", ...)` pattern: endpoint JSON shapes, status codes, the round-trip (fetch persists → read returns fetch text + trailing newline), and the in-flight-fetch case (a chain stub with a delay held in a background thread while both a list and a read are asserted to complete without `BUSY` and without invoking the chain again).
- **E2E** — `tests/e2e/test_ui.py` extends the existing `server`/`page` fixtures: the server points `TRANSCRIPT_DIR` at a temp directory pre-seeded with files; new tests cover list rendering, prettified labels with real-name requests, empty state, scrolling, post-fetch refresh, click-to-display, `textContent` discipline (a seeded transcript containing `<script>` markup), the deleted-file error path, and the download (a Playwright `download` event whose saved content equals the seeded file; the plain-HTTP flavor reuses the existing `http_page` fixture).
- **Run** — `python -m pytest tests/ -q --ignore=tests/e2e` and `python -m pytest tests/e2e/ -q`; each spec scenario maps to a named test via its Test Requirement block.

## Risks / Trade-offs

- [Two rapid saves land with the same mtime (filesystem granularity), making "most recent first" ambiguous among them] → accepted: order among equal mtimes is stable-but-unspecified; the UI shows a date, so ties are invisible in practice. Tests pin mtimes explicitly with `os.utime`.
- [A file is deleted between listing and clicking] → expected race; the read returns 404 and the UI shows the generic error banner (spec'd scenario T-…-023).
- [A very large saved transcript is sent as JSON in one response] → transcripts are KB to low MB; one JSON body is fine and avoids streaming complexity.
- [Prettified labels are lossy and can look like the title (they are not)] → accepted per the agreed trade-off; the on-disk contract stays pure and the row's tooltip/title attribute carries the real file name.
- [List endpoint stats every file on each call] → directory is expected to hold dozens of files, not millions; `os.stat` per entry is negligible, and no caching layer is worth adding.
- [`text-transform: capitalize` lowercases acronym-like words (e.g. "LLMs" → "Llms")] → cosmetic only; the real name is always what is requested and downloaded.

## Migration Plan

Purely additive: two GET endpoints, one UI section, one module. No data migration, no compose/image change, no behavior change to the fetch flow. Deploy as usual (`docker compose up -d --build`); existing saved files are listed immediately with no conversion. Rollback: revert the commit and re-deploy — files on the host are untouched either way.

## Open Questions

None — the scope, API shape, and UI placement were settled during exploration.
