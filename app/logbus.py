"""In-memory log bus: bounded ring buffer with subscriber fan-out.

Backs the in-browser log viewer: ``TeeStream`` (installed as the default
logging stream by ``app.log.setup_logging``) publishes every rendered JSON
log entry to the module-level ``DEFAULT_BUS``, and SSE clients of
``GET /api/logs`` subscribe to it for live delivery plus a bounded history
replay.

The bus is internal state only — it is never a log output destination and it
never writes to a file. All thread-safety lives here: log calls arrive from
worker threads and the event loop, so every mutation is guarded by one lock
and entry order in the buffer matches log-call order.
"""

from __future__ import annotations

import json
import sys
import threading
from collections import deque
from queue import Full, Queue
from typing import Any

# Replay cap for recent history (spec: at most 200 entries).
BUFFER_SIZE = 200

# Per-subscriber fan-out bound; a full queue drops the entry instead of
# blocking the logging path.
SUBSCRIBER_QUEUE_SIZE = 256


class LogBus:
    """Thread-safe bounded ring buffer with drop-on-full subscriber fan-out.

    ``publish`` is serialized by a single lock, so entries published from
    multiple threads appear in the buffer in log-call order.
    """

    def __init__(self, maxlen: int = BUFFER_SIZE) -> None:
        self._buffer: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._subscribers: set[Queue[dict[str, Any]]] = set()

    def publish(self, entry: dict[str, Any]) -> None:
        """Append ``entry`` to the ring buffer and fan it out to subscribers.

        Never blocks: a subscriber whose queue is full drops the entry, so a
        slow or dead consumer can never stall the logging path.
        """
        with self._lock:
            self._buffer.append(entry)
            for q in self._subscribers:
                try:
                    q.put_nowait(entry)
                except Full:
                    pass

    def snapshot(self) -> list[dict[str, Any]]:
        """Return a copy of the current buffer, oldest to newest."""
        with self._lock:
            return list(self._buffer)

    def subscribe(self) -> Queue[dict[str, Any]]:
        """Register a new subscriber and return its private queue."""
        q: Queue[dict[str, Any]] = Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: Queue[dict[str, Any]]) -> None:
        """Remove a subscriber (idempotent)."""
        with self._lock:
            self._subscribers.discard(q)


class TeeStream:
    """A stream in front of stdout for the logging factory.

    Every written line is forwarded to the *current* ``sys.stdout`` — resolved
    lazily at write time, never a captured or ``sys.__stdout__`` handle — and
    lines that are rendered JSON entries are additionally published to the
    bus so the log viewer can replay and stream them.
    """

    def __init__(self, bus: LogBus) -> None:
        self._bus = bus

    def flush(self) -> None:
        # structlog's PrintLogger prints with flush=True.
        stdout = sys.stdout
        if stdout is not None:
            stdout.flush()

    def write(self, line: str) -> int:
        stdout = sys.stdout
        written = stdout.write(line) if stdout is not None else len(line)
        stripped = line.strip()
        if stripped:
            try:
                entry = json.loads(stripped)
            except ValueError:
                entry = None
            if isinstance(entry, dict):
                self._bus.publish(entry)
        return written


# The single bus the default tee publishes to and the /api/logs endpoint
# streams from.
DEFAULT_BUS = LogBus()
