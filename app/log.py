"""Structured JSON logging setup (structlog).

Every log entry is one JSON object on one line of stdout:
``{"timestamp": "<ISO-8601 UTC>", "level": "<level>", "event": "<name>", ...}``.
stdout is the only log output; no file handlers are ever installed.
"""

from __future__ import annotations

import logging
import sys
from typing import IO, Optional

import structlog

from app import logbus


def setup_logging(stream: Optional[IO[str]] = None) -> None:
    """Configure structlog to emit one JSON object per line.

    ``stream`` defaults to a ``TeeStream`` that forwards every line to
    ``sys.stdout`` (resolved at write time, which keeps the configuration
    test-friendly) and mirrors rendered JSON entries into
    ``logbus.DEFAULT_BUS`` for the log viewer. An explicitly passed stream is
    used as-is and never touches the bus.
    """
    if stream is None:
        stream = logbus.TeeStream(logbus.DEFAULT_BUS)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=False,
    )


def get_logger():
    """Return a structlog logger bound to the current configuration.

    Called lazily (never at module import time) so tests can reconfigure
    structlog and have new output appear on the configured stream.
    """
    return structlog.get_logger()


def exception_hook(exc_type, exc, tb) -> None:
    """sys.excepthook: log unhandled exceptions as an error event, then keep
    the interpreter's default behaviour (traceback on stderr, non-zero exit).
    """
    get_logger().error("unhandled_exception", exc_info=(exc_type, exc, tb))
    sys.__excepthook__(exc_type, exc, tb)


_excepthook_installed = False


def install_excepthook() -> None:
    """Install the unhandled-exception hook (idempotent)."""
    global _excepthook_installed
    if not _excepthook_installed:
        sys.excepthook = exception_hook
        _excepthook_installed = True
