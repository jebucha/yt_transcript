"""T-STRUCTURED-LOGGING-007 .. 009 (captured log output)"""

import asyncio
import io
import json

from app import log as applog
from app.chain import FetchChain
from app.errors import UpstreamFailureError

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
VIDEO_ID = "dQw4w9WgXcQ"


class Stub:
    def __init__(self, result=None, error=None):
        self.calls = 0
        self._result = result
        self._error = error

    def __call__(self, video_id, requested_language):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._result


def run(coro):
    return asyncio.run(coro)


def _attempt_entries(buf) -> list[dict]:
    lines = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    return [e for e in lines if e.get("event") == "fetch_attempt"]


def test_primary_fetch_logged():
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    primary = Stub(result=("hello world", "en", "Title"))
    chain = FetchChain(primary=primary, fallback=Stub())

    run(chain.run(URL))

    entries = _attempt_entries(buf)
    assert len(entries) == 1
    e = entries[0]
    assert e["video_id"] == VIDEO_ID
    assert e["language"] == "en"
    assert e["source"] == "primary"
    assert e["outcome"] == "success"
    assert isinstance(e["duration_ms"], (int, float))
    assert e["chars"] == len("hello world")


def test_fallback_chain_logs_two_entries():
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    primary = Stub(error=UpstreamFailureError("primary blocked"))
    fallback = Stub(result=("fallback text", "de", "Title"))
    chain = FetchChain(primary=primary, fallback=fallback)

    result = run(chain.run(URL))

    assert result.source == "fallback"
    entries = _attempt_entries(buf)
    assert len(entries) == 2
    failed, succeeded = entries
    assert failed["source"] == "primary"
    assert failed["outcome"] == "failure"
    assert failed["reason"] == "UPSTREAM_FAILURE"
    assert failed["video_id"] == VIDEO_ID
    assert "chars" not in failed
    assert succeeded["source"] == "fallback"
    assert succeeded["outcome"] == "success"
    assert succeeded["chars"] == len("fallback text")


def test_no_headers_or_credentials_in_logs():
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    primary = Stub(error=UpstreamFailureError(
        "blocked: Authorization: Bearer secret-token-xyz, Cookie: session=abc123"))
    fallback = Stub(result=("ok text", "en", "Title"))
    chain = FetchChain(primary=primary, fallback=fallback)

    run(chain.run(URL))

    out = buf.getvalue()
    assert "secret-token-xyz" not in out
    assert "session=abc123" not in out
    assert "Authorization" not in out
    assert "Cookie" not in out
    # the recorded failure reason is the taxonomy code, not raw upstream text
    entries = _attempt_entries(buf)
    assert entries[0]["reason"] == "UPSTREAM_FAILURE"
