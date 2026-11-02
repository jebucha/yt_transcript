"""Transcript library: read-side access to persisted transcripts.

Read-only companions to the persistence (write) capability in
``app/persist.py``: listing the transcript directory and reading one file
back. Kept free of FastAPI imports (design.md, decision 1): the helpers are
pure over ``persist.transcript_dir()`` so they never disagree with the write
side, and are testable directly against ``tmp_path``.

The read side is best-effort and side-effect-free (design decisions 4 and 5):
an unusable directory degrades to an empty list, and reads never create,
modify, or delete anything.
"""

from __future__ import annotations

import stat
from datetime import datetime, timezone

from app.persist import transcript_dir

_EXTENSION = ".txt"


def _iso_utc(mtime: float) -> str:
    """Render a file mtime as an ISO 8601 UTC string (design 7)."""
    return (
        datetime.fromtimestamp(mtime, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def list_transcripts() -> list[dict]:
    """List the persisted transcripts in the transcript directory (design 1).

    Returns one entry per ``.txt`` regular file as ``{"name", "size",
    "modified"}`` — size in bytes, ``modified`` an ISO 8601 UTC string —
    sorted by last-modified time, most recent first. A missing directory, a
    non-directory path, or any listing failure degrades to ``[]``: the read
    side never creates the directory and never reports these conditions as
    errors (design 5).
    """
    try:
        base = transcript_dir()
        if not base.is_dir():
            return []
        entries = list(base.iterdir())
    except OSError:
        return []
    items: list[tuple[float, str, int]] = []
    for entry in entries:
        if not entry.name.endswith(_EXTENSION):
            continue
        try:
            st = entry.stat()  # follows symlinks; vanished entries skipped
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode):
            continue
        items.append((st.st_mtime, entry.name, st.st_size))
    items.sort(key=lambda item: item[0], reverse=True)
    return [
        {"name": name, "size": size, "modified": _iso_utc(mtime)}
        for mtime, name, size in items
    ]


def is_structurally_invalid_name(name: str) -> bool:
    """Structural reject for a client-supplied name (design 3, step 1).

    True for an empty name, a name that is ``.`` or ``..``, a name containing
    any path separator (``/`` or ``\\``), or a name containing a ``..`` path
    component — all checked on the raw string, before any filesystem access.
    This is the hard rule for HTTP 400; the read endpoint applies it first so
    a structurally invalid name can never be mapped to a 404.
    """
    if not name or name == ".":
        return True
    for separator in ("/", "\\"):
        parts = name.split(separator)
        if len(parts) != 1 or ".." in parts:
            return True
    return False


def read_transcript(name: str) -> tuple[bool, str]:
    """Read one persisted transcript by file name (design 1 and 3).

    Returns ``(ok, text)`` where ``text`` is the file's exact UTF-8 content.
    ``ok`` is False for a structurally invalid name (endpoint maps it to 400
    via :func:`is_structurally_invalid_name`) and for a missing, non-``.txt``,
    or otherwise unreadable file (404). Validation order: structural reject,
    ``.txt`` check, resolve-and-contain, regular-file check.
    """
    if is_structurally_invalid_name(name):
        return False, ""
    if not name.endswith(_EXTENSION):
        return False, ""
    try:
        base = transcript_dir().resolve()
        target = (base / name).resolve()
        if not target.is_relative_to(base):
            return False, ""
        if not target.is_file():
            return False, ""
        return True, target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False, ""
