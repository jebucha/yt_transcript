"""YouTube video reference parsing/normalization.

Accepts (per spec):
- standard watch URL:  https://www.youtube.com/watch?v=<id> (and m./subdomain variants)
- short link:          https://youtu.be/<id>
- bare video ID:       11 characters of [A-Za-z0-9_-]

Anything else raises InvalidUrlError. No network access is performed here.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from app.errors import InvalidUrlError

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

_YOUTUBE_HOSTS = ("youtube.com", "youtube-nocookie.com")


def parse_video_ref(ref: str) -> str:
    """Return the 11-character video ID, or raise InvalidUrlError."""
    ref = (ref or "").strip()
    if not ref:
        raise InvalidUrlError()

    # Bare video ID (no scheme, no slash)
    if VIDEO_ID_RE.match(ref):
        return ref

    try:
        parsed = urlparse(ref)
        hostname = (parsed.hostname or "").lower()
    except ValueError:
        raise InvalidUrlError() from None

    if any(hostname == host or hostname.endswith("." + host) for host in _YOUTUBE_HOSTS):
        # youtube.com, www.youtube.com, m.youtube.com, ...
        if parsed.path == "/watch":
            query = parse_qs(parsed.query)
            video_id = (query.get("v") or [""])[0]
            if VIDEO_ID_RE.match(video_id):
                return video_id
        raise InvalidUrlError()

    if hostname == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/", 1)[0]
        if VIDEO_ID_RE.match(video_id):
            return video_id

    raise InvalidUrlError()
