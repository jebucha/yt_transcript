# Proposal

## Why

Persisted transcript files are not self-describing: open one in a text editor and there is no way to tell which video it came from beyond the file name (and the file name collides for identical titles, where last write wins). The original request URL is discarded when the reference is parsed to a video ID, so provenance currently survives only in the structured logs. A header line with the video's URL makes every saved file self-describing and recoverable.

## What Changes

- Persisted transcript files now begin with a header line: the video's watch URL (`https://www.youtube.com/watch?v=<video_id>`) as the first line, followed by the transcript text unchanged and a single trailing newline. The URL is reconstructed from the video ID, which `save_transcript` already receives — no signature or call-site changes.
- The `transcript-persistence` capability's file-content requirement changes from "exactly the transcript text plus a trailing newline" to "URL header line, then the transcript text, then a single trailing newline". The `bytes` field of the `transcript_saved` log event now naturally counts the header line too (same computation: the written content).
- The `transcript-library` capability's read-endpoint requirement is updated where it describes app-written files: the round-trip guarantee ("read text equals the fetched transcript text plus a trailing newline") now includes the URL header line. The read endpoint itself is unchanged — it still returns the file's UTF-8 content byte-for-byte, and hand-written files without a header are served exactly as stored.
- Tests updated accordingly: the content assertions in `tests/test_persistence.py` (including the `bytes` field in the save-logging test) and the fetch→read round-trip test in `tests/test_transcript_library.py`.
- **BREAKING** for consumers of the saved files: the byte content of newly written files differs from files written before this change (one extra leading line). Pre-existing files on disk are not rewritten. The HTTP response body, the API surface, and the web interface are unchanged — the fetched transcript shown in the page is still the clean text.
- The app's minor version is bumped in `pyproject.toml` via `uv version --bump minor` (0.1.0 → 0.2.0) — under 0.x versioning, a breaking change takes a minor bump.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transcript-persistence`: the "Transcript file persistence" requirement's file-content contract gains the leading video-URL header line; its "Successful fetch writes the file" scenario and the writer-level content expectations change accordingly.
- `transcript-library`: the "Single transcript read endpoint" requirement's description of app-written file content and its "Fetched transcript round-trips through the store" scenario change to include the URL header line; the endpoint's byte-for-byte read behavior is unchanged.

## Impact

- `app/persist.py` — `save_transcript` builds the file content as URL header line + transcript + trailing newline before encoding; nothing else in the module changes.
- `tests/test_persistence.py` — existing content/bytes assertions updated to include the header; new writer-level test asserting the header format.
- `tests/test_transcript_library.py` — the fetch→read round-trip test's expected text updated.
- `pyproject.toml` / `uv.lock` — app version 0.1.0 → 0.2.0 via `uv version --bump minor`.
- Unaffected: `app/main.py`, `app/chain.py`, `app/fetchers.py`, `app/library.py` (read path is content-agnostic), `app/static/`, the API response schema, dependencies.
- No data migration: files already on disk keep their old format; only new writes carry the header.
