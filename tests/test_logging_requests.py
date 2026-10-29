"""T-STRUCTURED-LOGGING-005 / T-STRUCTURED-LOGGING-006"""

import io
import json

from starlette.testclient import TestClient

from app import log as applog
from app.main import create_app


def _request_entries(buf) -> list[dict]:
    lines = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    return [e for e in lines if e.get("event") == "http_request"]


def test_successful_request_logged(capsys):
    applog.setup_logging()  # resolves sys.stdout at logger-creation time (captured)

    client = TestClient(create_app())
    with client:
        response = client.get("/")

    assert response.status_code == 200
    entries = _request_entries(io.StringIO(capsys.readouterr().out))
    matches = [
        e
        for e in entries
        if e["method"] == "GET" and e["path"] == "/" and e["status"] == 200
    ]
    assert len(matches) == 1
    assert isinstance(matches[0]["duration_ms"], (int, float))


def test_error_request_logged(capsys):
    applog.setup_logging()

    client = TestClient(create_app())
    with client:
        response = client.get("/does-not-exist")

    assert response.status_code == 404
    out = capsys.readouterr().out
    entries = _request_entries(io.StringIO(out))
    matches = [
        e
        for e in entries
        if e["method"] == "GET"
        and e["path"] == "/does-not-exist"
        and e["status"] == 404
    ]
    assert len(matches) == 1
    assert isinstance(matches[0]["duration_ms"], (int, float))
    # no raw request headers in any log line
    assert "X-Secret" not in out


def test_request_log_contains_no_raw_headers(capsys):
    applog.setup_logging()

    client = TestClient(create_app())
    with client:
        client.get(
            "/",
            headers={
                "X-Secret-Header": "super-secret-value",
                "Authorization": "Bearer token-abc-123",
            },
        )

    out = capsys.readouterr().out
    assert "super-secret-value" not in out
    assert "token-abc-123" not in out
