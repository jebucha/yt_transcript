"""T-TRANSCRIPT-RETRIEVAL-001 .. 005"""

import pytest

from app.chain import FetchChain
from app.errors import InvalidUrlError
from app.urls import parse_video_ref

VIDEO_ID = "dQw4w9WgXcQ"


def test_standard_watch_url():
    assert parse_video_ref(f"https://www.youtube.com/watch?v={VIDEO_ID}") == VIDEO_ID
    # host variants
    assert parse_video_ref(f"https://m.youtube.com/watch?v={VIDEO_ID}") == VIDEO_ID


def test_short_link():
    assert parse_video_ref(f"https://youtu.be/{VIDEO_ID}") == VIDEO_ID


def test_bare_video_id():
    assert parse_video_ref(VIDEO_ID) == VIDEO_ID


def test_non_youtube_url_rejected_without_fetch():
    # Parsing itself must not touch the network (it is pure), and a chain
    # driven with this input must never invoke a fetcher.
    with pytest.raises(InvalidUrlError):
        parse_video_ref("https://vimeo.com/123456789")

    primary = _stub_primary()
    fallback = _stub_primary()
    chain = FetchChain(primary=primary, fallback=fallback)
    with pytest.raises(InvalidUrlError):
        asyncio_run(chain.run("https://vimeo.com/123456789"))
    assert primary.calls == 0 and fallback.calls == 0


def test_empty_or_malformed_input_rejected():
    for bad in ("", "   ", "not-a-url", "https://example.com/watch?v=xyz",
                f"https://youtu.be/too-short", "https://vimeo.com/watch?v=" + VIDEO_ID):
        with pytest.raises(InvalidUrlError):
            parse_video_ref(bad)


# --- helpers ---------------------------------------------------------------

def _stub_primary():
    class Stub:
        def __init__(self):
            self.calls = 0

        def __call__(self, video_id, requested_language):
            self.calls += 1
            return ("text", "en", "title")

    return Stub()


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
