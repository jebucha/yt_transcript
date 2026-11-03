"""Transcript library: read-side helpers (list/read) and their endpoints.

Test Requirement IDs:
  T-TRANSCRIPT-LIBRARY-001..015
"""

import asyncio
import os
import threading
import time
from datetime import datetime, timezone

from starlette.testclient import TestClient

from app import chain as chain_mod
from app.chain import FetchResult
from app.library import (
    is_structurally_invalid_name,
    list_transcripts,
    read_transcript,
)
from app.main import create_app
from app.persist import derive_file_name

# Fixed epoch base for mtimes pinned with os.utime (design Test Strategy).
BASE_MTIME = 1_730_000_000


def _write(directory, name, content, mtime):
    """Write a file and pin its mtime exactly (no clock-granularity flakes)."""
    path = directory / name
    path.write_text(content, encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


# --- 1. list_transcripts ------------------------------------------------------


def test_list_returns_name_size_and_modified(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-001"""
    mtime = BASE_MTIME + 100
    _write(tmp_path, "the_end_of_llms_ncm.txt", "Hello there.\n", mtime)
    _write(tmp_path, "another_video.txt", "Other text\n", BASE_MTIME + 200)
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))

    entries = list_transcripts()

    by_name = {entry["name"]: entry for entry in entries}
    assert set(by_name) == {"the_end_of_llms_ncm.txt", "another_video.txt"}
    first = by_name["the_end_of_llms_ncm.txt"]
    assert set(first) == {"name", "size", "modified"}
    assert first["size"] == len("Hello there.\n".encode("utf-8"))
    assert datetime.fromisoformat(first["modified"]) == datetime.fromtimestamp(
        mtime, tz=timezone.utc
    )
    second = by_name["another_video.txt"]
    assert second["size"] == len("Other text\n".encode("utf-8"))
    assert second["modified"].endswith("Z")


def test_list_sorted_most_recent_first(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-002"""
    _write(tmp_path, "older.txt", "old\n", BASE_MTIME)
    _write(tmp_path, "newer.txt", "new\n", BASE_MTIME + 1000)
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))

    names = [entry["name"] for entry in list_transcripts()]

    assert names == ["newer.txt", "older.txt"]


def test_list_excludes_non_txt_files(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-003"""
    _write(tmp_path, "keep.txt", "a\n", BASE_MTIME)
    _write(tmp_path, "notes.md", "b\n", BASE_MTIME)
    _write(tmp_path, "archive.txt.bak", "c\n", BASE_MTIME)
    (tmp_path / "subdir.txt").mkdir()  # a directory wearing a .txt name
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))

    names = [entry["name"] for entry in list_transcripts()]

    assert names == ["keep.txt"]


def test_list_empty_directory_returns_empty_array(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-004"""
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))

    assert list_transcripts() == []


def test_missing_directory_returns_empty_array(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-005"""
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("TRANSCRIPT_DIR", str(missing))

    assert list_transcripts() == []
    assert not missing.exists()  # the read side never creates the directory


def test_non_directory_path_returns_empty_array(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-006"""
    not_dir = tmp_path / "a-file"
    not_dir.write_text("x", encoding="utf-8")
    monkeypatch.setenv("TRANSCRIPT_DIR", str(not_dir))

    assert list_transcripts() == []


# --- 2. read_transcript -------------------------------------------------------


def test_read_returns_file_content(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-007"""
    _write(tmp_path, "the_end_of_llms_ncm.txt", "Hello there.\n", BASE_MTIME)
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))

    ok, text = read_transcript("the_end_of_llms_ncm.txt")

    assert ok is True
    assert text == "Hello there.\n"


def test_read_unicode_file_name(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-009"""
    name = "café_bär_über_alles.txt"
    _write(tmp_path, name, "Über alles.\n", BASE_MTIME)
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))

    ok, text = read_transcript(name)

    assert ok is True
    assert text == "Über alles.\n"


def test_read_unknown_name_returns_404(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-010 (404 mapping at the endpoint level)"""
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))

    assert read_transcript("does_not_exist.txt") == (False, "")


def _forbid_transcript_dir(monkeypatch):
    """Prove the structural reject happens before any filesystem access: a
    structurally invalid name must never reach ``transcript_dir()`` (the only
    path from the read side to a file)."""
    import app.library as library

    def _forbidden():
        raise AssertionError(
            "structurally invalid name must be rejected before any directory access"
        )

    monkeypatch.setattr(library, "transcript_dir", _forbidden)


def test_read_name_with_path_separator_returns_400(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-011"""
    base = tmp_path / "root"
    (base / "transcripts").mkdir(parents=True)
    outside = base / "outside.txt"
    outside.write_text("secret\n", encoding="utf-8")
    monkeypatch.setenv("TRANSCRIPT_DIR", str(base / "transcripts"))
    _forbid_transcript_dir(monkeypatch)

    ok, text = read_transcript("../outside.txt")

    assert (ok, text) == (False, "")
    assert is_structurally_invalid_name("../outside.txt") is True
    # No file outside the transcript directory is read.
    assert outside.read_text(encoding="utf-8") == "secret\n"


def test_read_dotdot_name_returns_400(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-012"""
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))
    _forbid_transcript_dir(monkeypatch)

    for name in ("..", "sub/..", "..\\win", "."):
        assert read_transcript(name) == (False, "")
        assert is_structurally_invalid_name(name) is True


def test_read_non_txt_name_returns_404(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-013"""
    _write(tmp_path, "notes.md", "notes\n", BASE_MTIME)
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))

    assert read_transcript("notes.md") == (False, "")
    # A structurally plain non-.txt name is a miss, not a 400.
    assert is_structurally_invalid_name("notes.md") is False


# --- 3. Endpoint integration --------------------------------------------------


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))
    return TestClient(create_app())


def test_endpoint_list_populated(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-001..003 (endpoint level): 200 envelope shape."""
    _write(tmp_path, "the_end_of_llms_ncm.txt", "Hello there.\n", BASE_MTIME)
    _write(tmp_path, "notes.md", "skip me\n", BASE_MTIME + 10)
    client = _client(monkeypatch, tmp_path)
    with client:
        response = client.get("/api/transcripts")

    assert response.status_code == 200
    body = response.json()
    assert list(body) == ["transcripts"]
    [entry] = body["transcripts"]
    assert set(entry) == {"name", "size", "modified"}
    assert entry["name"] == "the_end_of_llms_ncm.txt"
    assert entry["size"] == len("Hello there.\n".encode("utf-8"))
    assert entry["modified"].endswith("Z")


def test_endpoint_list_empty(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-004 (endpoint level)."""
    client = _client(monkeypatch, tmp_path)
    with client:
        response = client.get("/api/transcripts")

    assert response.status_code == 200
    assert response.json() == {"transcripts": []}


def test_endpoint_list_missing(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-005 (endpoint level): missing dir is not created."""
    missing = tmp_path / "does-not-exist"
    client = _client(monkeypatch, missing)
    with client:
        response = client.get("/api/transcripts")

    assert response.status_code == 200
    assert response.json() == {"transcripts": []}
    assert not missing.exists()


def test_endpoint_list_non_directory(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-006 (endpoint level)."""
    not_dir = tmp_path / "a-file"
    not_dir.write_text("x", encoding="utf-8")
    client = _client(monkeypatch, not_dir)
    with client:
        response = client.get("/api/transcripts")

    assert response.status_code == 200
    assert response.json() == {"transcripts": []}


def test_endpoint_read_returns_content(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-007 (endpoint level)."""
    _write(tmp_path, "the_end_of_llms_ncm.txt", "Hello there.\n", BASE_MTIME)
    client = _client(monkeypatch, tmp_path)
    with client:
        response = client.get("/api/transcripts/the_end_of_llms_ncm.txt")

    assert response.status_code == 200
    assert response.json() == {
        "name": "the_end_of_llms_ncm.txt",
        "text": "Hello there.\n",
    }


def test_endpoint_read_unicode_name(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-009 (endpoint level, percent-encoded name)."""
    name = "café_bär_über_alles.txt"
    _write(tmp_path, name, "Über alles.\n", BASE_MTIME)
    client = _client(monkeypatch, tmp_path)
    with client:
        response = client.get(f"/api/transcripts/{name}")

    assert response.status_code == 200
    assert response.json() == {"name": name, "text": "Über alles.\n"}


def test_endpoint_read_unknown_404(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-010 (endpoint level)."""
    client = _client(monkeypatch, tmp_path)
    with client:
        response = client.get("/api/transcripts/does_not_exist.txt")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_endpoint_read_traversal_400(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-011, 012 (endpoint level): separator / dot-dot.

    Names that arrive percent-encoded (the only form in which a `..` or a
    path separator reaches a single path segment) are rejected with 400.
    Literal multi-segment traversal paths never match the single-``{name}``
    route and therefore never reach the handler; forward-slash forms are
    additionally normalized away by the test client.
    """
    client = _client(monkeypatch, tmp_path)
    with client:
        # `%2e%2e` decodes to the dot-dot name `..`.
        response = client.get("/api/transcripts/%2e%2e")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_NAME"
        # `..%5Coutside.txt` decodes to the separator name `..\outside.txt`.
        response = client.get("/api/transcripts/..%5Coutside.txt")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_NAME"


def test_endpoint_read_non_txt_404(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-013 (endpoint level)."""
    _write(tmp_path, "notes.md", "notes\n", BASE_MTIME)
    client = _client(monkeypatch, tmp_path)
    with client:
        response = client.get("/api/transcripts/notes.md")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


class FakeChain:
    """Stands in for chain_mod.default_chain; returns queued results in order
    (mirrors the project's existing chain-mocking pattern)."""

    def __init__(self, results=(), error=None):
        self._results = list(results)
        self.error = error
        self.calls = []

    async def run(self, url):
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        if self._results:
            return self._results.pop(0)
        raise AssertionError("FakeChain: no queued results left")


def _result(text, video_id, title):
    return FetchResult(
        text=text, video_id=video_id, title=title, language="en", source="primary"
    )


def test_read_roundtrips_after_successful_fetch(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-008: fetch persists, then read returns the watch
    URL line, the transcript text, and a trailing newline — byte-for-byte with
    the saved file."""
    text = "This is the transcript of the test video."
    expected = "https://www.youtube.com/watch?v=dQw4w9WgXcQ\n" + text + "\n"
    name = derive_file_name("The End of LLMs? (NCM)", "dQw4w9WgXcQ")
    monkeypatch.setattr(
        chain_mod,
        "default_chain",
        FakeChain(results=[_result(text, "dQw4w9WgXcQ", "The End of LLMs? (NCM)")]),
    )
    client = _client(monkeypatch, tmp_path)
    with client:
        fetch = client.post(
            "/api/transcript",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )
        assert fetch.status_code == 200
        read = client.get(f"/api/transcripts/{name}")

    assert read.status_code == 200
    assert read.json() == {"name": name, "text": expected}
    # The read round-trips byte-for-byte with the saved file.
    assert (tmp_path / name).read_bytes() == expected.encode("utf-8")


class DelayedChain:
    """A chain stub whose single run blocks until released, held in a
    background thread so a fetch is genuinely in flight (design Test
    Strategy). The single-flight semaphore is not involved here: the read
    endpoints must not touch it at all."""

    def __init__(self):
        self.release = threading.Event()
        self.calls = []

    async def run(self, url):
        self.calls.append(url)
        await asyncio.to_thread(self.release.wait, timeout=15)
        return _result("slow fetch text", "dQw4w9WgXcQ", "A Slow Title")


def test_reads_during_in_flight_fetch_succeed(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-014: while a fetch is in flight, both a list and a
    read complete normally (not 503 BUSY) and the fetch chain is not invoked
    for either."""
    _write(tmp_path, "already_saved.txt", "saved content\n", BASE_MTIME)
    chain = DelayedChain()
    monkeypatch.setattr(chain_mod, "default_chain", chain)
    client = _client(monkeypatch, tmp_path)
    with client:
        # Hold the fetch in flight in a background thread.
        fetch_holder = {}

        def _run_fetch():
            fetch_holder["resp"] = client.post(
                "/api/transcript",
                json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            )

        fetch_thread = threading.Thread(target=_run_fetch)
        fetch_thread.start()
        # Wait until the fetch has actually reached the (delayed) chain.
        deadline = time.time() + 15
        while not chain.calls and time.time() < deadline:
            time.sleep(0.01)
        assert chain.calls == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]

        # Both reads complete while the fetch is still in flight.
        list_response = client.get("/api/transcripts")
        read_response = client.get("/api/transcripts/already_saved.txt")

        assert list_response.status_code == 200
        assert [e["name"] for e in list_response.json()["transcripts"]] == [
            "already_saved.txt"
        ]
        assert read_response.status_code == 200
        assert read_response.json() == {
            "name": "already_saved.txt",
            "text": "saved content\n",
        }
        # No read invoked the chain: still exactly one (the in-flight fetch).
        assert chain.calls == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]

        chain.release.set()
        fetch_thread.join(timeout=15)

    assert fetch_thread.is_alive() is False
    assert fetch_holder["resp"].status_code == 200
    # The fetch persisted its own transcript, independent of the reads.
    assert chain.calls == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]


def test_read_does_not_modify_file(tmp_path, monkeypatch):
    """T-TRANSCRIPT-LIBRARY-015: a successful read leaves the file unchanged
    (content, size, and mtime)."""
    path = _write(tmp_path, "the_end_of_llms_ncm.txt", "Hello there.\n", BASE_MTIME)
    client = _client(monkeypatch, tmp_path)
    with client:
        response = client.get("/api/transcripts/the_end_of_llms_ncm.txt")

    assert response.status_code == 200
    st = path.stat()
    assert path.read_bytes() == b"Hello there.\n"
    assert st.st_size == len(b"Hello there.\n")
    # mtime is unchanged (pinned above; a read must not bump it).
    assert st.st_mtime == BASE_MTIME
