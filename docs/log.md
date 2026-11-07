# `app/log.py` — structured JSON logging setup

## Purpose

Configures structlog so that every log entry is one JSON object on one line
of stdout: `{"timestamp": "<ISO-8601 UTC>", "level": "<level>",
"event": "<name>", ...}`. It also provides the lazy logger accessor and an
optional sys.excepthook that turns unhandled exceptions into an error event.

## Public surface

- `setup_logging(stream=None)` — configures structlog (idempotent by design:
  it simply reconfigures). With no stream, it installs a `TeeStream` in
  front of stdout that mirrors rendered JSON entries into
  `logbus.DEFAULT_BUS` for the in-browser log viewer; an explicitly passed
  stream (tests) is used as-is and never touches the bus.
- `get_logger()` — returns a structlog logger bound to the *current*
  configuration; call it lazily, never at module import time.
- `install_excepthook()` — installs the unhandled-exception hook,
  idempotent.
- `exception_hook(exc_type, exc, tb)` — logs `unhandled_exception` (error,
  with `exc_info`), then keeps the interpreter's default behaviour
  (traceback on stderr, non-zero exit).

## Invariants

- **stdout is the only log output destination.** No file handlers are ever
  installed; the in-memory bus mirror is internal state, not an output
  (that's what keeps the structured-logging spec's "stdout only" rule true).
- **One JSON object per line**, `ensure_ascii=False`, with ISO-8601 UTC
  timestamps under the key `timestamp`.
- **The log level floor is INFO** (`make_filtering_bound_logger`) — nothing
  below INFO is ever emitted.
- **Loggers are created lazily.** `get_logger()` at import time would bind
  to the import-time configuration and defeat tests' reconfiguration; every
  module fetches its logger at call time.
- **The default tee resolves `sys.stdout` at write time** (see `logbus.py`)
  — never a captured or `sys.__stdout__` handle — which is what makes the
  capsys-based test streams work.
- **The excepthook adds, never replaces:** after logging, it delegates to
  `sys.__excepthook__`, and installation is idempotent.

## Log events emitted

None of its own — it is the *plumbing* for every other module's events.
The one event associated with this module is `unhandled_exception` (error),
emitted by the hook when an exception escapes the interpreter.

## Error codes raised/handled

None — this module raises nothing and handles no domain errors.

## Design decisions

Resolved from the archived change design docs:

- `2026-10-29-youtube-transcript` **D8** — structlog (tiny, pure Python)
  configured for one JSON object per line with `timestamp`/`level`/`event`;
  no file handlers; a top-level handler turns unhandled exceptions into an
  error event.
- `2026-11-03-add-log-viewer` **decision 2** — the delivery seam: a tee
  stream in front of stdout (rather than a processor or a logging handler)
  so `log.py`'s public shape is unchanged, explicit test streams still
  bypass the bus, and "stdout is still written" is structurally obvious.

## Cross-links

- [`logbus.py`](logbus.html) — the `TeeStream` target and the SSE source
- [`main.py`](main.html) — where `setup_logging` / `install_excepthook` are invoked
- [`__init__.py`](__init__.html) — the package conventions this module serves
