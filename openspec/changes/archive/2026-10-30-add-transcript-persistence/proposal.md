# Proposal

## Why

Fetched transcripts currently exist only on the page until the user copies them; nothing survives the browser tab. Operators want a durable, machine-readable record of every fetched transcript on disk (for archiving or downstream processing). A bind-mounted directory is the natural store for this stateless single-container app — no database, no new service.

## What Changes

- On every successful transcript fetch, the app writes the plain transcript text to a configurable directory (env `TRANSCRIPT_DIR`, default `/transcripts`) as a plain-text `.txt` file, in addition to returning it in the response as it does today.
- File name is derived from the video title: lowercased, all punctuation removed, word gaps replaced with underscores, leading/trailing underscores trimmed. Example: `The End of LLMs? (NCM)` -> `the_end_of_llms_ncm.txt`. Titles that sanitize to the empty string fall back to the video ID; names truncated to fit the 255-byte file-name limit get the video ID appended.
- Persistence is best-effort: a failed write (missing directory, permissions, disk full) is logged with an error event but never changes the HTTP response — the transcript is still returned and displayed.
- Re-fetching a video whose title maps to an existing file name overwrites that file (the stored copy is always the latest fetch).
- New structured log events: `transcript_saved` (success, with video ID, file path, byte count) and `transcript_save_failed` (error, with video ID and failure reason).
- `docker-compose.yml` mounts `${TRANSCRIPTS_DIR:-/home/john/transcripts}:/transcripts`; the `Dockerfile` sets the default `TRANSCRIPT_DIR` environment variable.
- README updated: the "zero state" description is adjusted, and a host-directory permissions note is added for the bind mount (the container runs as an unprivileged user).

No breaking changes: the API response shape, the web interface, and the error taxonomy are unchanged.

## Capabilities

### New Capabilities
- `transcript-persistence`: persistence of successfully fetched transcripts to a plain-text file on disk — when a file is written, how the file name is derived from the title, file content and encoding, overwrite semantics, and the best-effort failure behavior that keeps the HTTP response unaffected.

### Modified Capabilities
- `structured-logging`: adds a persistence-operation logging requirement — the app SHALL log `transcript_saved` and `transcript_save_failed` events with the video ID, file path (on success), byte count (on success), and failure reason (on failure).

## Impact

- `app/main.py` — write step in the transcript endpoint after a successful fetch.
- New `app/persist.py` (working name) — pure title-to-file-name derivation plus the file writer, kept free of FastAPI imports so both are unit-testable.
- `Dockerfile` — `TRANSCRIPT_DIR` environment variable default.
- `docker-compose.yml` — `volumes` entry for the host transcript directory.
- `README.md` — state description, mount configuration, host permissions note.
- Tests — unit tests for the file-name derivation rules; API-level tests for the write path, overwrite, and best-effort failure using a temporary directory.
- Unaffected: `app/chain.py`, `app/fetchers.py`, `app/urls.py`, `app/errors.py`, `app/static/` (no frontend change), API response schema, dependencies (`pyproject.toml` gains nothing).
