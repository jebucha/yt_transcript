# `app/settings.py` — application settings

## Purpose

Reads and writes the durable application-level UI preference file
(`settings.json` in the transcript directory) — the setting is read on
**every call**, never at startup. Today the file holds one boolean,
`autoSummarize`; the shape may grow fields later, nothing is designed ahead
of need.

## Public surface

- `load_settings() -> Settings` — one settings read.
- `save_settings(auto_summarize: bool) -> bool` — atomic write; returns
  whether it succeeded (never raises).
- `settings_path() -> Path` — resolves `settings.json` under
  `persist.transcript_dir()` at call time.
- `Settings` — frozen dataclass: `auto_summarize` (bool).

## Invariants

- **No FastAPI imports.** The reader and writer are pure over
  `persist.transcript_dir()` so they are testable directly against
  `tmp_path`, and never disagree with the transcript write/read side.
- **Read per call, never cached, never at startup.** Edits on disk take
  effect on the next request without a restart, and the app boots with no
  settings file at all.
- **Safe off-default, never an exception.** A missing file (the normal
  state — no log), an unreadable file, malformed JSON, a non-object top
  level, or a missing/non-boolean `autoSummarize` all return
  `auto_summarize=False` without raising.
- **Malformed files are diagnosable but never echoed.** An unreadable or
  malformed file logs exactly one `settings_load_failed` error event
  carrying the path and the parse/OS error detail — never the file's
  contents.
- **Writes are atomic.** `save_settings` writes a sibling temp file
  (`settings.json.tmp`) and swaps it in with `os.replace`, so a crash
  mid-write can never leave a truncated `settings.json` behind — the
  setting is all-or-nothing. A stranded temp file is removed best-effort.
- **The file is invisible to the transcript library:** the list endpoint
  filters to `.txt`, and the settings endpoints never touch the fetch
  chain or the single-flight semaphore.

## Log events emitted

- `settings_load_failed` (error): `path`, `reason` (`invalid_json`,
  `invalid_structure`, or the OS exception type name), `detail` (the parse
  error — never file contents).
- `settings_save_failed` (error): `path`, `reason` (the OS exception type
  name), `detail`.

## Error codes raised/handled

None raised — a failed load degrades to the off-default; a failed write
returns `False` and the endpoint maps that to `500 WRITE_FAILED` (plain
HTTP, not a taxonomy entry).

## Design decisions

Resolved from `add-auto-summarize`:

- **D2** — settings live in `<TRANSCRIPT_DIR>/settings.json`: the durable,
  host-mounted, already-writable volume, so the toggle survives container
  rebuilds and is shared across browsers; not `localStorage` (per-browser)
  and not `providers.json` (mounted read-only, provider config only).
- **D3** — FastAPI-free module mirroring `providers.py`: per-request
  reads, safe off-default, and a sibling-temp + `os.replace` write (the
  all-or-nothing reading of a settings file rules out a plain overwrite).

## Cross-links

- [`persist.py`](persist.html) — `transcript_dir()`, the path this module shares
- [`library.py`](library.html) — the `.txt`-only listing that ignores `settings.json`
- [`main.py`](main.html) — `GET /api/settings` / `POST /api/settings`
- [`app/static/app.js`](static/app-js.html) — the Auto-summarize toggle that consumes them
