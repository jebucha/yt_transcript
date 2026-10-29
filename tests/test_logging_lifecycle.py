"""T-STRUCTURED-LOGGING-003 / T-STRUCTURED-LOGGING-004"""

import asyncio
import io
import json

import pytest

from app import log as applog
from app.main import create_app


def _json_lines(buf) -> list[dict]:
    return [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]


def test_startup_event_includes_port(monkeypatch):
    monkeypatch.setenv("PORT", "9123")
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    app = create_app()

    async def drive_lifespan():
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(drive_lifespan())

    entries = [e for e in _json_lines(buf) if e["event"] == "server_started"]
    assert len(entries) == 1
    assert entries[0]["port"] == 9123
    assert entries[0]["level"] == "info"


def test_shutdown_event_logged(monkeypatch):
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    app = create_app()

    async def drive_lifespan():
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(drive_lifespan())

    entries = [e for e in _json_lines(buf) if e["event"] == "server_stopped"]
    assert len(entries) == 1


def test_unhandled_exception_logs_error_event():
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    exc = ValueError("boom")
    # Call the hook the way sys.excepthook would be called.
    try:
        raise exc
    except ValueError:
        import sys

        applog.exception_hook(*sys.exc_info())

    entries = [e for e in _json_lines(buf) if e["event"] == "unhandled_exception"]
    assert len(entries) == 1
    assert entries[0]["level"] == "error"
    assert "ValueError" in entries[0]["exception"]
    assert "boom" in entries[0]["exception"]
