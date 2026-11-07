# `app/library.py` — transcript library (read side)

## Purpose

Read-only companions to the persistence (write) capability in `persist.py`:
list the transcript directory and read one saved transcript back byte-for-
byte. It is the backend for the UI's "Saved transcripts" section and its
Download button.

## Public surface

- `list_transcripts() -> list[dict]` — one entry per `.txt` regular file as
  `{"name", "size", "modified"}` (size in bytes, `modified` an ISO 8601 UTC
  string), sorted most-recent-first.
- `read_transcript(name) -> tuple[bool, str]` — `(ok, text)` where `text`
  is the file's exact UTF-8 content.
- `is_structurally_invalid_name(name) -> bool` — the hard traversal-reject
  rule, exported so every `{name}` endpoint applies it before filesystem
  access.

## Invariants

- **No FastAPI imports.** The helpers are pure over
  `persist.transcript_dir()` so read and write can never disagree on the
  directory, and are testable directly against `tmp_path`.
- **Best-effort and side-effect-free.** A missing directory, a non-directory
  path, or any listing failure degrades to `[]` — the read side never
  creates the directory and never reports these conditions as errors. Reads
  never create, modify, or delete anything.
- **Structural reject is checked on the raw string, before any filesystem
  access.** True for an empty name, `.` or `..`, any `/` or `\` separator,
  or any `..` path component. This is the hard HTTP 400 rule; it guarantees a
  structurally invalid name can never be mapped to a 404.
- **Full validation order in `read_transcript`:** structural reject →
  must end in `.txt` → resolve-and-contain (`Path.resolve()` +
  `is_relative_to` against the resolved directory) → regular-file check.
  Steps 3–4 are belt-and-braces (a symlink planted by the host owner is out
  of the threat model — that owner can already read the directory directly).
- **The write side's name-safety guarantee is *not* relied on.** The read
  side defends itself because its input is client-supplied.
- **Listing stats every file on each call** — no cache; the directory is
  expected to hold dozens of files, and `stat.S_ISREG` filtering plus
  `entry.stat()` (symlink-following, vanished entries skipped) keep it
  accurate.
- **Server-side sorting.** Most-recent-first is done here; the UI never
  re-sorts. Equal mtimes may order arbitrarily (filesystem granularity).

## Log events emitted

None — the read endpoints are quiet, low-frequency operator reads
(deliberate non-goal of the change that introduced them).

## Error codes raised/handled

None raised — it returns `(ok, text)`; the endpoint maps a structural reject
to plain-HTTP 400 `INVALID_NAME` and a miss to 404 `NOT_FOUND` (deliberately
outside the `errors.py` taxonomy).

## Design decisions

Resolved from `2026-11-02-add-saved-transcript-list`:

- **decision 1** — a new FastAPI-free module with pure helpers, reusing
  `persist.transcript_dir()`.
- **decision 3** — traversal defense in two layers: structural reject
  (client input, hard 400) + resolve-and-contain (belt-and-braces).
- **decision 4** — filesystem work via `asyncio.to_thread`; plain-HTTP
  status mapping; the endpoints never touch the single-flight semaphore.
- **decision 5** — an unusable directory degrades to an empty list, never an
  error.
- **decision 7** — the API shape: envelope object for the list
  (`{"transcripts": [...]}`), `modified` as ISO 8601 UTC from the file mtime,
  server-side sorting.

## Cross-links

- [`persist.py`](persist.html) — the write side it reads from
- [`main.py`](main.html) — the `GET /api/transcripts*` endpoints
- [`summarize.py`](summarize.html) — `read_summary` follows the same read-side discipline
- [`static/app-js.html`](static/app-js.html) — the UI list that consumes this API
