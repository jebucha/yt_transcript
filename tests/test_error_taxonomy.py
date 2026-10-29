"""T-TRANSCRIPT-RETRIEVAL-013 .. 015 (+ remaining taxonomy entries)."""

import asyncio

import pytest

from app.chain import FetchChain
from app.errors import (
    BusyError,
    InvalidUrlError,
    NoCaptionsError,
    TranscriptError,
    UpstreamFailureError,
    VideoUnavailableError,
)

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


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


def _expect_error(chain, url, expected_code, expected_status, message_fragment):
    with pytest.raises(TranscriptError) as excinfo:
        run(chain.run(url))
    err = excinfo.value
    assert err.code == expected_code
    assert err.status == expected_status
    assert message_fragment.lower() in err.message.lower()


def test_private_video_video_unavailable():
    primary = Stub(error=VideoUnavailableError())
    fallback = Stub(result=("text", "en", "Title"))
    chain = FetchChain(primary=primary, fallback=fallback)

    _expect_error(chain, URL, "VIDEO_UNAVAILABLE", 404, "unavailable")
    # a definitive unavailability must not trigger the fallback
    assert primary.calls == 1 and fallback.calls == 0


def test_no_captions():
    primary = Stub(error=NoCaptionsError())
    fallback = Stub(result=("text", "en", "Title"))
    chain = FetchChain(primary=primary, fallback=fallback)

    _expect_error(chain, URL, "NO_CAPTIONS", 404, "no captions")
    assert primary.calls == 1 and fallback.calls == 0


def test_transient_upstream_outage():
    primary = Stub(error=UpstreamFailureError())
    fallback = Stub(error=UpstreamFailureError())
    chain = FetchChain(primary=primary, fallback=fallback)

    _expect_error(chain, URL, "UPSTREAM_FAILURE", 502, "try again later")
    assert primary.calls == 1 and fallback.calls == 1


def test_invalid_url_entry():
    chain = FetchChain(primary=Stub(), fallback=Stub())
    _expect_error(chain, "https://vimeo.com/123456789", "INVALID_URL", 400,
                  "valid YouTube")
    _expect_error(chain, "", "INVALID_URL", 400, "valid YouTube")


def test_busy_entry():
    chain = FetchChain(primary=Stub(), fallback=Stub())

    async def scenario():
        # Hold the single-flight semaphore to simulate an in-flight chain.
        await chain._semaphore.acquire()
        try:
            with pytest.raises(BusyError) as excinfo:
                await chain.run(URL)
        finally:
            chain._semaphore.release()
        return excinfo

    excinfo = run(scenario())
    assert excinfo.value.code == "BUSY"
    assert excinfo.value.status == 503
    assert "busy" in excinfo.value.message.lower()
