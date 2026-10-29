"""T-TRANSCRIPT-RETRIEVAL-011, 012, 016 (+ timeout behaviour)"""

import asyncio
import time

import pytest

from app.chain import FetchChain
from app.errors import (
    BusyError,
    NoCaptionsError,
    TranscriptError,
    UpstreamFailureError,
)
from app.urls import parse_video_ref

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class Stub:
    def __init__(self, result=None, error=None, sleep=0.0):
        self.calls = 0
        self._result = result
        self._error = error
        self._sleep = sleep

    def __call__(self, video_id, requested_language):
        self.calls += 1
        if self._sleep:
            time.sleep(self._sleep)
        if self._error is not None:
            raise self._error
        return self._result


def run(coro):
    return asyncio.run(coro)


def test_primary_fails_fallback_succeeds():
    primary = Stub(error=UpstreamFailureError())
    fallback = Stub(result=("fallback text", "en", "Title"))
    chain = FetchChain(primary=primary, fallback=fallback)

    result = run(chain.run(URL))

    assert result.source == "fallback"
    assert result.text == "fallback text"
    assert result.video_id == parse_video_ref(URL)
    assert result.title == "Title"
    assert result.language == "en"
    assert primary.calls == 1 and fallback.calls == 1


def test_primary_success_no_fallback():
    primary = Stub(result=("primary text", "en", "Title"))
    fallback = Stub(result=("fallback text", "en", "Title"))
    chain = FetchChain(primary=primary, fallback=fallback)

    result = run(chain.run(URL))

    assert result.source == "primary"
    assert primary.calls == 1 and fallback.calls == 0


def test_non_upstream_failure_does_not_fallback():
    primary = Stub(error=NoCaptionsError())
    fallback = Stub(result=("fallback text", "en", "Title"))
    chain = FetchChain(primary=primary, fallback=fallback)

    with pytest.raises(NoCaptionsError):
        run(chain.run(URL))
    assert primary.calls == 1 and fallback.calls == 0


def test_both_fetchers_fail_upstream_failure():
    primary = Stub(error=UpstreamFailureError("primary blocked"))
    fallback = Stub(error=UpstreamFailureError("fallback blocked"))
    chain = FetchChain(primary=primary, fallback=fallback)

    with pytest.raises(TranscriptError) as excinfo:
        run(chain.run(URL))

    assert excinfo.value.code == "UPSTREAM_FAILURE"
    assert excinfo.value.status == 502
    assert primary.calls == 1 and fallback.calls == 1


def test_concurrent_request_busy():
    primary = Stub(result=("text", "en", "Title"), sleep=0.5)
    fallback = Stub(result=("text", "en", "Title"))
    chain = FetchChain(primary=primary, fallback=fallback)

    async def scenario():
        first = asyncio.create_task(chain.run(URL))
        await asyncio.sleep(0.1)  # first chain is now holding the semaphore
        with pytest.raises(BusyError):
            await chain.run(URL)
        return await first

    result = run(scenario())
    assert result.source == "primary"


def test_attempt_timeout_is_upstream_failure():
    primary = Stub(result=("text", "en", "Title"), sleep=0.3)
    fallback = Stub(result=("fb text", "en", "Title"))
    chain = FetchChain(primary=primary, fallback=fallback, attempt_timeout=0.05)

    result = run(chain.run(URL))
    # primary times out (upstream failure) -> fallback is used
    assert result.source == "fallback"
    assert primary.calls == 1 and fallback.calls == 1
