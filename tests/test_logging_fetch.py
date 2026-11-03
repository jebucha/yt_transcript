"""T-STRUCTURED-LOGGING-007 .. 009, 012 .. 013 (captured log output)"""

import asyncio
import io
import json
import time

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
    # The real fetchers raise with safe, app-constructed messages (never raw
    # upstream text, headers, or credentials); the stub matches that
    # convention. The chain logs the message verbatim as ``detail``
    # (T-STRUCTURED-LOGGING-013), so the sensitive-data guarantee rests on
    # the fetchers' messages being clean.
    primary = Stub(error=UpstreamFailureError("Watch page returned HTTP 429"))
    fallback = Stub(result=("ok text", "en", "Title"))
    chain = FetchChain(primary=primary, fallback=fallback)

    run(chain.run(URL))

    out = buf.getvalue()
    # no raw HTTP request headers or credentials in any log line
    assert "Authorization" not in out
    assert "Cookie" not in out
    assert "Bearer" not in out
    # the recorded failure reason is the taxonomy code, not raw upstream text
    entries = _attempt_entries(buf)
    assert entries[0]["reason"] == "UPSTREAM_FAILURE"


def test_timeout_failure_includes_detail():
    """T-STRUCTURED-LOGGING-012"""

    def slow_fetch(video_id, requested_language):
        time.sleep(1.2)  # outlasts the attempt timeout
        return ("text", "en", "Title")

    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    chain = FetchChain(
        primary=slow_fetch,
        fallback=Stub(result=("fallback text", "en", "Title")),
        attempt_timeout=1.0,
    )

    result = run(chain.run(URL))
    assert result.source == "fallback"

    failed = [e for e in _attempt_entries(buf) if e["outcome"] == "failure"]
    assert len(failed) == 1
    e = failed[0]
    assert e["source"] == "primary"
    assert e["reason"] == "UPSTREAM_FAILURE"
    # the cause detail carries the timeout message, duration included
    assert e["detail"] == "primary fetch timed out after 1s"


def test_fetcher_failure_includes_detail():
    """T-STRUCTURED-LOGGING-013"""
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    primary = Stub(error=UpstreamFailureError("connection to upstream timed out"))
    fallback = Stub(result=("fallback text", "en", "Title"))
    chain = FetchChain(primary=primary, fallback=fallback)

    result = run(chain.run(URL))
    assert result.source == "fallback"

    failed = [e for e in _attempt_entries(buf) if e["outcome"] == "failure"]
    assert len(failed) == 1
    e = failed[0]
    assert e["source"] == "primary"
    assert e["reason"] == "UPSTREAM_FAILURE"
    assert e["detail"] == "connection to upstream timed out"
