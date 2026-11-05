"""T-HTTP-REQUEST-LIMITS-001 .. 003.

Bounds on inbound HTTP traffic (app/main.py): the oversized-body rejection
(413 BODY_TOO_LARGE from the Content-Length middleware) and the uvicorn
connection-concurrency cap in the main() entry point.
"""

import json

import pytest
import uvicorn
from starlette.testclient import TestClient

from app import summarize as summarize_mod
from app.main import MAX_BODY_BYTES, create_app, main


class RecordingDispatch:
    """Recording stand-in for summarize_mod._call_chat_completions."""

    def __init__(self):
        self.calls = []
        self.summary = "The summary."

    def __call__(self, base_url, model, messages, api_key, timeout):
        self.calls.append({
            "base_url": base_url, "model": model, "messages": messages,
            "api_key": api_key, "timeout": timeout,
        })
        return self.summary


PROVIDER_CONFIG = {
    "provider": {
        "alpha": {
            "name": "Alpha Local",
            "options": {"baseURL": "http://127.0.0.1:41411/v1"},
            "models": {"model-a1": "Model A1"},
        },
    },
    "default": "alpha",
}


@pytest.fixture
def api(tmp_path, monkeypatch):
    """TestClient with a tmp provider config, a tmp transcript dir, and the
    chat-completions dispatch replaced by a recording stub."""
    config_file = tmp_path / "providers.json"
    config_file.write_text(json.dumps(PROVIDER_CONFIG), encoding="utf-8")
    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir()
    monkeypatch.setenv("PROVIDERS_CONFIG", str(config_file))
    monkeypatch.setenv("TRANSCRIPT_DIR", str(transcript_dir))
    dispatch = RecordingDispatch()
    monkeypatch.setattr(summarize_mod, "_call_chat_completions", dispatch)
    client = TestClient(create_app())
    with client:
        yield {
            "client": client,
            "transcript_dir": transcript_dir,
            "dispatch": dispatch,
        }


def _valid_body(text="The transcript text."):
    return {
        "text": text,
        "name": "video.txt",
        "provider": "alpha",
        "model": "model-a1",
    }


def test_oversized_body_rejected_with_413(api, monkeypatch):
    """T-HTTP-REQUEST-LIMITS-001"""
    # the production limit is 5 MiB...
    assert MAX_BODY_BYTES == 5 * 1024 * 1024

    # ...patched small for the test, so a 4 KiB body is over the limit
    monkeypatch.setattr("app.main.MAX_BODY_BYTES", 1024)
    body = json.dumps(_valid_body(text="x" * 4096)).encode("utf-8")
    assert len(body) > 1024

    response = api["client"].post(
        "/api/summarize", content=body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "BODY_TOO_LARGE"
    # the body was rejected before any endpoint code ran: no backend call...
    assert api["dispatch"].calls == []
    # ...and no transcript or summary file was written
    assert list(api["transcript_dir"].iterdir()) == []


def test_body_under_limit_processed_normally(api):
    """T-HTTP-REQUEST-LIMITS-002"""
    # a valid small body is handled by the endpoint as usual
    response = api["client"].post("/api/summarize", json=_valid_body())
    assert response.status_code == 200
    assert response.json() == {"summary": "The summary."}
    assert len(api["dispatch"].calls) == 1

    # so is a valid body well under the real 5 MiB limit (a 100,000-char
    # transcript, under 300 KB as JSON)
    response = api["client"].post(
        "/api/summarize", json=_valid_body(text="x" * 100_000)
    )
    assert response.status_code == 200
    assert response.json() == {"summary": "The summary."}
    assert len(api["dispatch"].calls) == 2

    # and a bodyless request is unaffected
    response = api["client"].get("/api/transcripts")
    assert response.status_code == 200
    assert response.json() == {"transcripts": []}


def test_entry_point_sets_connection_limit(monkeypatch):
    """T-HTTP-REQUEST-LIMITS-003"""
    calls = {}

    def fake_run(*args, **kwargs):
        calls.update({"args": args, "kwargs": kwargs})

    # main() imports uvicorn and looks up run on the module at call time
    monkeypatch.setattr(uvicorn, "run", fake_run)

    main()

    assert calls["kwargs"].get("limit_concurrency") == 100
