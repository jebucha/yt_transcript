"""Transcript persistence: title-to-file-name derivation and best-effort writer.

Kept free of FastAPI imports (design.md, decision 2): the derivation is a
pure function and the writer is testable directly against ``tmp_path``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from app.log import get_logger

# ext4's hard file-name limit, which is the deployment target (design 3).
_MAX_NAME_BYTES = 255
_EXTENSION = ".txt"

# Default transcript directory (design 6); overridable via TRANSCRIPT_DIR.
_DEFAULT_DIR = "/transcripts"


def _sanitize_title(title: str) -> str:
    """Lowercase and collapse every run of one or more characters that are not
    a Unicode letter or digit (punctuation, whitespace, symbols, and
    underscores) into a single ``_``, then trim the edges. Unicode letters and
    digits are preserved, not transliterated, so the result has no path
    separator."""
    lowered = title.lower()
    # \w keeps Unicode letters, digits and underscores; collapse everything
    # else (punctuation / whitespace / symbols) into a single underscore.
    base = re.sub(r"[^\w]+", "_", lowered)
    # Underscores are separators too; collapse their runs as well.
    base = re.sub(r"_+", "_", base)
    return base.strip("_")


def _truncate_to_bytes(text: str, max_bytes: int) -> str:
    """Return the longest whole-character prefix of ``text`` that encodes to
    at most ``max_bytes`` bytes of UTF-8 (never mid-codepoint)."""
    out: list[str] = []
    size = 0
    for ch in text:
        b = len(ch.encode("utf-8"))
        if size + b > max_bytes:
            break
        out.append(ch)
        size += b
    return "".join(out)


def derive_file_name(title: str, video_id: str) -> str:
    """Derive a path-safe ``.txt`` file name from a video title (design 3).

    A title that sanitizes to the empty string falls back to the video ID; a
    name whose total size (with ``.txt``) exceeds 255 bytes is truncated on a
    character boundary with ``_<video_id>`` appended so the result still fits.
    """
    base = _sanitize_title(title)
    if not base:
        base = video_id
    if len((base + _EXTENSION).encode("utf-8")) > _MAX_NAME_BYTES:
        suffix = "_" + video_id + _EXTENSION
        budget = _MAX_NAME_BYTES - len(suffix.encode("utf-8"))
        base = _truncate_to_bytes(base, budget) + "_" + video_id
    return base + _EXTENSION


def transcript_dir() -> Path:
    """Resolve the transcript directory at call time (design 6).

    Reads ``TRANSCRIPT_DIR`` with the default ``/transcripts`` — the same
    read-at-call-time pattern as ``_listen_port`` in ``app/main.py``. The
    directory is never created here; a missing directory is a write failure
    handled per the best-effort write behavior.
    """
    return Path(os.environ.get("TRANSCRIPT_DIR", _DEFAULT_DIR))


def save_transcript(text: str, title: str, video_id: str) -> str | None:
    """Best-effort write of a transcript to a plain-text file (design 4).

    Writes ``text`` plus a single trailing newline as UTF-8 to
    ``<transcript_dir>/<derived name>`` with a plain overwrite. Never raises to
    the caller: on success it logs ``transcript_saved`` and returns the written
    path; on any write error it logs ``transcript_save_failed`` and returns
    ``None``.
    """
    content = text + "\n"
    data = content.encode("utf-8")
    logger = get_logger()
    try:
        path = transcript_dir() / derive_file_name(title, video_id)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as exc:
        logger.error(
            "transcript_save_failed",
            video_id=video_id,
            reason=type(exc).__name__,
        )
        return None
    logger.info(
        "transcript_saved",
        video_id=video_id,
        path=str(path),
        bytes=len(data),
    )
    return str(path)
