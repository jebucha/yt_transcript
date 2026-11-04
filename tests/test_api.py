"""Task 4.1 — POST /api/transcript: success shape and all error pairs."""

import pytest
from starlette.testclient import TestClient

from app import chain as chain_mod
from app.chain import FetchChain, FetchResult
from app.errors import (
    BusyError,
    InvalidUrlError,
    NoCaptionsError,
    UpstreamFailureError,
    VideoUnavailableError,
)
from app.main import create_app


class FakeChain:
    """Stands in for chain_mod.default_chain."""

    def __init__(self):
        self.result = None
        self.error = None
        self.calls = []

    async def run(self, url):
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def client_and_chain(monkeypatch):
    fake = FakeChain()
    monkeypatch.setattr(chain_mod, "default_chain", fake)
    client = TestClient(create_app())
    with client:
        yield client, fake


def _post(client, url):
    return client.post("/api/transcript", json={"url": url})


def test_success_shape(client_and_chain):
    client, fake = client_and_chain
    fake.result = FetchResult(
        text="hello world", video_id="dQw4w9WgXcQ", title="A Title",
        language="en", source="primary",
    )

    response = _post(client, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "text", "video_id", "title", "language", "source", "name",
    }
    assert body["text"] == "hello world"
    assert body["video_id"] == "dQw4w9WgXcQ"
    assert body["title"] == "A Title"
    assert body["language"] == "en"
    assert body["source"] == "primary"
    # the derived persistence name (design decision 5)
    assert body["name"] == "a_title.txt"
    assert fake.calls == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (InvalidUrlError(), 400, "INVALID_URL"),
        (VideoUnavailableError(), 404, "VIDEO_UNAVAILABLE"),
        (NoCaptionsError(), 404, "NO_CAPTIONS"),
        (UpstreamFailureError(), 502, "UPSTREAM_FAILURE"),
        (BusyError(), 503, "BUSY"),
    ],
)
def test_error_shape_end_to_end(client_and_chain, error, status, code):
    client, fake = client_and_chain
    fake.error = error

    response = _post(client, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert response.status_code == status
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]


def test_missing_url_is_invalid_url(monkeypatch):
    # Real chain: empty url must be rejected before any fetcher runs.
    calls = []

    def primary(vid, lang):
        calls.append(vid)
        return ("t", "en", "T")

    monkeypatch.setattr(chain_mod, "default_chain",
                        FetchChain(primary=primary, fallback=primary))
    client = TestClient(create_app())
    with client:
        response = client.post("/api/transcript", json={})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_URL"
    assert calls == []


def test_non_youtube_url_is_invalid_url(monkeypatch):
    calls = []

    def primary(vid, lang):
        calls.append(vid)
        return ("t", "en", "T")

    monkeypatch.setattr(chain_mod, "default_chain",
                        FetchChain(primary=primary, fallback=primary))
    client = TestClient(create_app())
    with client:
        response = _post(client, "https://vimeo.com/123456789")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_URL"
    assert calls == []


def test_custom_error_message_passes_through(client_and_chain):
    client, fake = client_and_chain
    fake.error = UpstreamFailureError("custom upstream message")

    response = _post(client, "https://youtu.be/dQw4w9WgXcQ")

    assert response.status_code == 502
    assert response.json()["error"]["message"] == "custom upstream message"
