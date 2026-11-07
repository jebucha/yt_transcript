# `app/persist.py` — transcript persistence (write side)

## Purpose

Two jobs: derive a path-safe `.txt` file name from a video title (a pure
function) and write a successfully fetched transcript to a plain-text file
(best-effort). This is the sole write path for transcripts; the read side
lives in `library.py`.

## Public surface

- `derive_file_name(title, video_id) -> str` — pure, no I/O; the full file
  name including `.txt`.
- `save_transcript(text, title, video_id) -> str | None` — best-effort
  writer; returns the written path, `None` on any failure.
- `transcript_dir() -> Path` — resolves `TRANSCRIPT_DIR` (default
  `/transcripts`) **at call time**.
- File format: the video's watch URL
  (`https://www.youtube.com/watch?v=<video_id>`) as the first line, then the
  transcript text, then a single trailing newline — UTF-8.

## Invariants

- **No FastAPI imports.** The derivation is pure and the writer is testable
  directly against `tmp_path`; the module must stay importable without an
  app instance.
- **Never raises to the caller.** Any write error (missing directory,
  permissions, disk full, encoding) is logged as `transcript_save_failed`
  and swallowed — persistence is a side effect of a successful fetch, and a
  failed save must never break the response.
- **Never creates the transcript directory.** A missing directory is an
  operator-config condition that degrades to the logged failure; the app
  creating it would be a permissions trap on the bind mount.
- **Name derivation rules, in order:** lowercase; replace every run of
  non-letter/non-digit characters (punctuation, whitespace, symbols —
  including `/`, so the output is inherently path-safe) with a single `_`;
  trim `_` edges; empty → the video ID; over 255 bytes with `.txt` → truncate
  on a character boundary (never mid-codepoint) and append `_<video_id>` so
  the result still fits. The video-ID suffix appears **only when
  truncation happens**. 255 bytes is ext4's hard limit — the deployment
  target.
- **Plain overwrite, no atomic replace.** A re-fetch of the same video
  rewrites identical bytes; the single-flight semaphore makes concurrent
  writes of the same file a non-issue.
- **Watch URL header, reconstructed from the video ID** — not the URL the
  user pasted — so the same video always writes the same bytes no matter
  which URL variant triggered the fetch.
- The directory is resolved *outside* the try block so the failure handler
  can always reference the intended path.

## Log events emitted

- `transcript_saved` (info): `video_id`, `path`, `bytes` (the encoded
  content, header line included).
- `transcript_save_failed` (error): `video_id`, `reason` (exception type
  name), `path`, `detail` (the OS error string).

## Error codes raised/handled

None raised. Catches broad `Exception` on the write — by design.

## Design decisions

Resolved from the archived change design docs:

- `2026-10-30-add-transcript-persistence` **decision 2** (new module, pure
  derivation + writer, no FastAPI), **decision 3** (the name derivation
  algorithm above), **decision 4** (best-effort write with structured
  logging, never re-raised), **decision 5** (worker-thread write, plain
  overwrite), **decision 6** (`TRANSCRIPT_DIR` read at call time, default
  `/transcripts`, directory deliberately not created).
- `2026-11-03-add-video-url-header` **decision 1** (header is the watch URL
  reconstructed from the video ID), **decision 2** (bare URL, first line, no
  label, no blank separator), **decision 3** (content assembled before
  encoding so the `bytes` log field counts the header).

## Cross-links

- [`library.py`](library.html) — the read side over the same directory
- [`main.py`](main.html) — the endpoint that calls `save_transcript`
- [`summarize.py`](summarize.html) — the alongside `.summary` writer
- [`__init__.py`](__init__.html) — the no-FastAPI-imports package convention
