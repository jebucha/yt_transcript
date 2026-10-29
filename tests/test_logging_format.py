"""T-STRUCTURED-LOGGING-001 / T-STRUCTURED-LOGGING-002"""

import io
import json
from datetime import datetime

from starlette.testclient import TestClient

from app import log as applog
from app.main import create_app


def test_log_line_is_single_json_object():
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    applog.get_logger().info("hello", foo="bar")

    out = buf.getvalue()
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event"] == "hello"
    assert entry["foo"] == "bar"
    assert entry["level"] == "info"
    assert "timestamp" in entry
    # timestamp is ISO-8601
    datetime.fromisoformat(entry["timestamp"])


def test_no_log_files_created(tmp_path, monkeypatch):
    # Run the app from an empty directory; nothing may create log files there.
    monkeypatch.chdir(tmp_path)
    applog.setup_logging()

    client = TestClient(create_app())
    with client:
        client.get("/")
    applog.get_logger().info("post_request_event")

    created = [p.name for p in tmp_path.iterdir()]
    assert created == [], f"logging created files: {created}"
