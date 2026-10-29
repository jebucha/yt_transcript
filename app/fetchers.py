"""Caption-track fetchers.

- ``primary_fetch``:  youtube-transcript-api (manual tracks preferred,
  language fallback English -> first available).
- ``fallback_fetch``: yt-dlp used as a Python library (json3 subtitles,
  no download, no ffmpeg).
- ``fetch_video_title``: lightweight watch-page title lookup used to
  complete the response metadata (yt-dlp provides the title itself).

Both fetchers are synchronous (blocking I/O) and are meant to be run in a
worker thread via ``asyncio.to_thread`` with a hard timeout (see
``app.chain``). They return ``(text, language_code, title)`` and raise
``TranscriptError`` subclasses for every failure.
"""

from __future__ import annotations

import html
import json
import os
import re
import tempfile

import requests
import yt_dlp
import yt_dlp.utils
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    YouTubeTranscriptApiException,
    AgeRestricted,
    InvalidVideoId,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
)

from app.errors import (
    NoCaptionsError,
    UpstreamFailureError,
    VideoUnavailableError,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
ATTEMPT_TIMEOUT = 30.0  # seconds, hard cap per fetch attempt

# --------------------------------------------------------------------------
# Output cleaning
# --------------------------------------------------------------------------

_VTT_HEADER_RE = re.compile(r"^WEBVTT[^\n]*\n", re.M)
_VTT_CUE_TIME_RE = re.compile(r"\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\s*-->[^\n]*\n")
_BRACKET_TS_RE = re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?\]")
_SSML_RE = re.compile(r"</?(?:s|p|br|phoneme|say|sub|subline|prosody|break)(?:\s[^>]*)?>")
_ANY_TAG_RE = re.compile(r"<[^>]{1,200}>")
_UNICODE_SPACE_RE = re.compile(r"[\xa0\u2000-\u200b\u202f\u3000]")


def clean_text(raw: str) -> str:
    """Return plain text: entities decoded, timestamps/VTT/SSML/HTML removed,
    whitespace normalized, one cue per line."""
    s = html.unescape(raw)
    s = _UNICODE_SPACE_RE.sub(" ", s)
    s = s.replace("-->", " ")
    s = _VTT_HEADER_RE.sub("", s)
    s = _VTT_CUE_TIME_RE.sub("", s)
    s = _BRACKET_TS_RE.sub(" ", s)
    s = _SSML_RE.sub(" ", s)
    s = _ANY_TAG_RE.sub(" ", s)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.splitlines()]
    return "\n".join(ln for ln in lines if ln)


# --------------------------------------------------------------------------
# Video title
# --------------------------------------------------------------------------


def fetch_video_title(video_id: str) -> str:
    """Fetch the video title from the watch page.

    Raises UpstreamFailureError when the page cannot be fetched (the caller
    treats that as a transient upstream failure).
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        response = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=ATTEMPT_TIMEOUT,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        raise UpstreamFailureError(
            f"Could not fetch the watch page: {type(exc).__name__}"
        ) from exc
    if response.status_code != 200:
        raise UpstreamFailureError(
            f"Watch page returned HTTP {response.status_code}"
        )
    match = re.search(r"<title>(.*?)</title>", response.text, re.S)
    if not match:
        raise UpstreamFailureError("Watch page contained no <title> tag")
    title = html.unescape(match.group(1)).strip()
    title = re.sub(r"\s*[-|]\s*YouTube\s*$", "", title).strip()
    return title or video_id


# --------------------------------------------------------------------------
# Primary fetcher: youtube-transcript-api
# --------------------------------------------------------------------------


def _map_primary_error(exc: YouTubeTranscriptApiException) -> "TranscriptError":
    """Map library exceptions onto the error taxonomy."""
    if isinstance(exc, (VideoUnavailable, VideoUnplayable, AgeRestricted)):
        return VideoUnavailableError()
    if isinstance(exc, (InvalidVideoId, NoTranscriptFound, TranscriptsDisabled)):
        # Video id well-formed but no video, or no caption tracks at all.
        if isinstance(exc, InvalidVideoId):
            return VideoUnavailableError()
        return NoCaptionsError()
    # IpBlocked, RequestBlocked, PoTokenRequired, CouldNotRetrieveTranscript,
    # YouTubeRequestFailed, ...: transient upstream problems -> fallback.
    return UpstreamFailureError()


def _pick_transcript(transcripts):
    """Prefer manual over auto-generated; English first, then first available."""
    candidates = list(transcripts)
    if not candidates:
        return None

    def is_english(t) -> bool:
        return t.language_code.lower().startswith("en")

    manual_english = [t for t in candidates if not t.is_generated and is_english(t)]
    auto_english = [t for t in candidates if t.is_generated and is_english(t)]
    manual_any = [t for t in candidates if not t.is_generated]
    auto_any = [t for t in candidates if t.is_generated]
    for pool in (manual_english, auto_english, manual_any, auto_any):
        if pool:
            return pool[0]
    return None


def primary_fetch(video_id: str, requested_language: str = "en") -> tuple[str, str, str]:
    """Fetch the transcript via youtube-transcript-api.

    Returns ``(text, language_code, title)``. Raises TranscriptError
    subclasses on failure.
    """
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.headers["Accept-Language"] = "en-US"
    api = YouTubeTranscriptApi(http_client=session)

    try:
        transcripts = api.list(video_id)
        transcript = _pick_transcript(transcripts)
        if transcript is None:
            raise NoCaptionsError()
        fetched = transcript.fetch()
    except NoCaptionsError:
        raise
    except YouTubeTranscriptApiException as exc:
        raise _map_primary_error(exc) from exc

    text = clean_text("\n".join(snippet.text for snippet in fetched.snippets))
    if not text:
        raise NoCaptionsError()
    title = fetch_video_title(video_id)
    return text, fetched.language_code, title


# --------------------------------------------------------------------------
# Fallback fetcher: yt-dlp (Python library)
# --------------------------------------------------------------------------


def _map_ytdlp_error(message: str) -> "TranscriptError":
    lowered = message.lower()
    unavailable_phrases = (
        "private video",
        "video unavailable",
        "not exist",
        "was removed",
        "has been removed",
        "is not available",
        "age-restricted",
        "age restricted",
        "confirm your age",
    )
    if any(phrase in lowered for phrase in unavailable_phrases):
        return VideoUnavailableError()
    if re.search(r"\bage\b", lowered) and "sign in" in lowered:
        return VideoUnavailableError()
    # 403/429/blocked/rate-limited and everything else: transient upstream.
    return UpstreamFailureError()


def _parse_json3(data: list) -> str:
    lines = []
    for event in data:
        segs = event.get("segs") or []
        text = "".join(seg.get("utf8", "") for seg in segs if isinstance(seg, dict))
        lines.append(text)
    return clean_text("\n".join(lines))


def _extract_subtitles(video_id: str, langs: list[str], outdir: str) -> dict:
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": langs,
        "subtitlesformat": "json3",
        "outtmpl": os.path.join(outdir, "%(id)s.%(ext)s"),
        "http_headers": {"User-Agent": USER_AGENT},
        "socket_timeout": ATTEMPT_TIMEOUT,
        "retries": 0,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(watch_url, download=True)


def _pick_subtitle_lang(info: dict, prefer_prefix: str | None) -> str | None:
    requested = info.get("requested_subtitles") or {}
    keys = list(requested.keys())
    if not keys:
        return None
    if prefer_prefix:
        manual = [
            k for k in keys
            if k.startswith(prefer_prefix) and not k.endswith("-orig")
        ]
        generated = [k for k in keys if k.startswith(prefer_prefix)]
        if manual:
            return manual[0]
        if generated:
            return generated[0]
    return keys[0]


def fallback_fetch(video_id: str, requested_language: str = "en") -> tuple[str, str, str]:
    """Fetch the transcript via yt-dlp (json3 subtitles, no download).

    Returns ``(text, language_code, title)``.
    """
    with tempfile.TemporaryDirectory(prefix="yt-transcript-") as outdir:
        try:
            info = _extract_subtitles(
                video_id,
                [f"{requested_language}.*", f"{requested_language}-orig", requested_language],
                outdir,
            )
        except yt_dlp.utils.DownloadError as exc:
            raise _map_ytdlp_error(str(exc)) from exc
        except Exception as exc:  # OSError, network, ...
            raise UpstreamFailureError(f"yt-dlp failed: {type(exc).__name__}") from exc

        title = info.get("title") or video_id
        lang = _pick_subtitle_lang(info, prefer_prefix=requested_language)
        if lang is None:
            # No English track: try every available language.
            try:
                info = _extract_subtitles(video_id, ["all"], outdir)
            except yt_dlp.utils.DownloadError as exc:
                raise _map_ytdlp_error(str(exc)) from exc
            except Exception as exc:
                raise UpstreamFailureError(f"yt-dlp failed: {type(exc).__name__}") from exc
            title = info.get("title") or title
            lang = _pick_subtitle_lang(info, prefer_prefix=None)
            if lang is None:
                raise NoCaptionsError()

        filepath = (info.get("requested_subtitles") or {})[lang].get("filepath")
        if not filepath or not os.path.exists(filepath):
            raise NoCaptionsError()
        try:
            with open(filepath, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            # Unreadable file, or yt-dlp fell back to a non-json3 format:
            # treat as an upstream data problem, not a missing-captions case.
            raise UpstreamFailureError(
                f"yt-dlp returned an unreadable subtitle file: {type(exc).__name__}"
            ) from exc
        if not isinstance(data, list):
            raise UpstreamFailureError(
                "yt-dlp subtitle file did not contain json3 events"
            )
        text = _parse_json3(data)
        if not text:
            raise NoCaptionsError()
        return text, lang, title
