"""Fallback fetcher (yt-dlp mocked): json3 payload -> clean transcript text."""

import json

import pytest
import yt_dlp.utils

from app import fetchers
from app.errors import (
    NoCaptionsError,
    UpstreamFailureError,
    VideoUnavailableError,
)

VIDEO_ID = "dQw4w9WgXcQ"

JSON3_PAYLOAD = [
    {"eventIds": [1], "segs": [{"utf8": "Hello "}, {"utf8": "world&nbsp;&amp; friends"}]},
    {"eventIds": [2], "segs": [{"utf8": "Second line"}]},
    {"eventIds": [3], "segs": []},  # empty event must be dropped
]


class FakeYoutubeDL:
    """Stands in for yt_dlp.YoutubeDL. ``behavior(url, opts)`` is supplied by
    the test; it may raise or return an info dict. It writes the json3 files
    to the location implied by opts["outtmpl"], as real yt-dlp would."""

    behavior = None

    def __init__(self, opts):
        self.opts = opts

    def extract_info(self, url, download=False):
        assert url == f"https://www.youtube.com/watch?v={VIDEO_ID}"
        behavior = type(self).behavior
        if behavior is None:
            raise AssertionError("no behavior configured")
        return behavior(url, self.opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


def make_behavior(subs_by_lang, title="Fake Title", error=None):
    def behavior(url, opts):
        if error is not None:
            raise yt_dlp.utils.DownloadError(error)
        base = opts["outtmpl"].replace("%(id)s", VIDEO_ID)
        info = {"title": title, "requested_subtitles": {}}
        for lang, payload in subs_by_lang.items():
            path = base.replace("%(ext)s", f"{lang}.json3")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            info["requested_subtitles"][lang] = {"ext": "json3", "filepath": path}
        return info

    return behavior


@pytest.fixture
def fake_ytdlp(monkeypatch):
    monkeypatch.setattr(fetchers.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    return FakeYoutubeDL


def test_json3_payload_maps_to_clean_text(fake_ytdlp):
    fake_ytdlp.behavior = make_behavior({"en": JSON3_PAYLOAD})

    text, language, title = fetchers.fallback_fetch(VIDEO_ID, "en")

    assert text == "Hello world & friends\nSecond line"
    assert language == "en"
    assert title == "Fake Title"
    # no markup/entities survive (the only "&" is the decoded one)
    assert "&nbsp;" not in text and "<" not in text
    assert text.count("&") == 1


def test_non_english_language_used_when_no_english(fake_ytdlp):
    fake_ytdlp.behavior = make_behavior({"de": JSON3_PAYLOAD})

    text, language, _ = fetchers.fallback_fetch(VIDEO_ID, "en")

    assert language == "de"
    assert text == "Hello world & friends\nSecond line"


def test_auto_generated_preferred_over_manual_for_language(fake_ytdlp):
    # en-orig (auto) is the only English track -> it is used
    fake_ytdlp.behavior = make_behavior({"en-orig": JSON3_PAYLOAD, "de": JSON3_PAYLOAD})

    _text, language, _ = fetchers.fallback_fetch(VIDEO_ID, "en")

    assert language == "en-orig"


def test_no_captions_when_no_subtitles(fake_ytdlp):
    fake_ytdlp.behavior = make_behavior({})

    with pytest.raises(NoCaptionsError):
        fetchers.fallback_fetch(VIDEO_ID, "en")


def test_private_video_maps_to_video_unavailable(fake_ytdlp):
    fake_ytdlp.behavior = make_behavior({}, error="YouTube said: Private video")

    with pytest.raises(VideoUnavailableError):
        fetchers.fallback_fetch(VIDEO_ID, "en")


def test_http_429_maps_to_upstream_failure(fake_ytdlp):
    fake_ytdlp.behavior = make_behavior({}, error="HTTP Error 429: Too Many Requests")

    with pytest.raises(UpstreamFailureError):
        fetchers.fallback_fetch(VIDEO_ID, "en")


def test_unreadable_subtitle_file_maps_to_upstream_failure(fake_ytdlp):
    # yt-dlp fell back to a non-json3 format (VTT text in the .json3 slot).
    def behavior(url, opts):
        base = opts["outtmpl"].replace("%(id)s", VIDEO_ID)
        path = base.replace("%(ext)s", "en.json3")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("WEBVTT\n\n00:00.000 --> 00:01.000\nnot json")
        return {"title": "Fake Title",
                "requested_subtitles": {"en": {"ext": "vtt", "filepath": path}}}

    fake_ytdlp.behavior = behavior

    with pytest.raises(UpstreamFailureError):
        fetchers.fallback_fetch(VIDEO_ID, "en")
