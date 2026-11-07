# `app/logbus.py` — in-memory log bus

## Purpose

Backs the in-browser log viewer: a bounded ring buffer with subscriber
fan-out. `TeeStream` (installed as the default logging stream by
`app.log.setup_logging`) publishes every rendered JSON log entry to the
module-level `DEFAULT_BUS`, and the SSE clients of `GET /api/logs` subscribe
for live delivery plus a bounded history replay.

## Public surface

- `LogBus` — `publish(entry)`, `snapshot() -> list[dict]` (oldest→newest),
  `subscribe() -> Queue`, `unsubscribe(q)` (idempotent).
- `TeeStream` — a stream in front of stdout for structlog's
  `PrintLoggerFactory`.
- `DEFAULT_BUS` — the single bus the default tee publishes to and
  `/api/logs` streams from.
- Constants: `BUFFER_SIZE` (200 — the replay cap), `SUBSCRIBER_QUEUE_SIZE`
  (256 — the per-subscriber fan-out bound).

## Invariants

- **Internal state only.** The bus is never a log output destination and
  never writes to a file — the structured-logging spec's "stdout is the only
  log output" holds with or without subscribers.
- **All thread-safety lives here.** Log calls arrive from worker threads and
  the event loop; every mutation is guarded by one lock, and entry order in
  the buffer matches log-call order because `publish` is serialized.
- **`publish` never blocks.** A subscriber whose queue is full drops the
  entry — a slow or dead consumer can never stall the logging path.
- **`TeeStream` resolves the *current* `sys.stdout` at write time** — never
  a captured or `sys.__stdout__` handle — so test streams (capsys) keep
  working. Only lines that parse as a JSON *dict* are published; everything
  else passes through to stdout unmodified.
- **Bounded memory, both ends.** The ring buffer is a `deque(maxlen=200)`;
  the client panel mirrors the 200-line cap.

## Log events emitted

None — it *carries* every other module's events. It does not log.

## Error codes raised/handled

None — it raises nothing; `Full` queues are swallowed by design.

## Design decisions

Resolved from `2026-11-03-add-log-viewer`:

- **decision 1** — the transport is server-sent events (one-way, instant,
  dependency-free) rather than polling or WebSocket.
- **decision 2** — the delivery seam: a tee stream in front of stdout
  (alternatives — a structlog processor or a logging handler — were
  rejected; the stream seam is where the app already plugs in test streams).
- **decision 3** — thread-safe fan-out: one lock, per-subscriber
  `queue.Queue`, drop-on-full, unsubscribe on generator exit.
- **decision 4** — replay on connect: subscribe *before* snapshotting so an
  entry logged between the two is not lost on the first connect.

## Cross-links

- [`log.py`](log.html) — installs the `TeeStream` as the default stream
- [`main.py`](main.html) — the `GET /api/logs` endpoint that streams `DEFAULT_BUS`
- [`static/app-js.html`](static/app-js.html) — the in-browser panel that consumes the stream
