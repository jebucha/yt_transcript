"""Transcript persistence: file-name derivation, best-effort writer, save
logging, and endpoint integration.

Test Requirement IDs:
  T-TRANSCRIPT-PERSISTENCE-001..011, T-STRUCTURED-LOGGING-010/011/014
"""

import io
import json

from starlette.testclient import TestClient

from app import chain as chain_mod
from app import log as applog
from app.chain import FetchResult
from app.errors import NoCaptionsError
from app.main import create_app
from app.persist import derive_file_name, save_transcript


# --- 1. File name derivation (pure function) --------------------------------

def test_filename_typical_title():
    """T-TRANSCRIPT-PERSISTENCE-003"""
    name = derive_file_name("The End of LLMs? (NCM)", "dQw4w9WgXcQ")
    assert name == "the_end_of_llms_ncm.txt"


def test_filename_punctuation_only_title_falls_back_to_video_id():
    """T-TRANSCRIPT-PERSISTENCE-004"""
    name = derive_file_name("???", "dQw4w9WgXcQ")
    assert name == "dQw4w9WgXcQ.txt"


def test_filename_slash_in_title_stays_in_directory():
    """T-TRANSCRIPT-PERSISTENCE-005"""
    name = derive_file_name("Foo/Bar: The Story", "dQw4w9WgXcQ")
    assert name == "foo_bar_the_story.txt"
    assert "/" not in name
    assert "\\" not in name


def test_filename_unicode_title_preserved():
    """T-TRANSCRIPT-PERSISTENCE-006"""
    name = derive_file_name("Café & Bär: Über alles", "dQw4w9WgXcQ")
    assert name == "café_bär_über_alles.txt"


def test_filename_overlong_title_truncated_with_video_id():
    """T-TRANSCRIPT-PERSISTENCE-007"""
    video_id = "dQw4w9WgXcQ"
    title = "a" * 300  # sanitizes to 300 alnum chars -> over 255 bytes with .txt

    name = derive_file_name(title, video_id)

    # Fits within the 255-byte file-name limit.
    assert len(name.encode("utf-8")) <= 255
    # Truncated and disambiguated with the video ID suffix.
    assert name.endswith("_" + video_id + ".txt")
    # The title was actually truncated, not the full 300-char name.
    assert name != title + ".txt"


# --- 2. Best-effort writer and save logging ---------------------------------

def test_directory_from_environment_variable(tmp_path, monkeypatch):
    """T-TRANSCRIPT-PERSISTENCE-010"""
    target = tmp_path / "transcripts"
    target.mkdir()
    monkeypatch.setenv("TRANSCRIPT_DIR", str(target))

    path = save_transcript("hello world", "A Title", "dQw4w9WgXcQ")

    assert path == str(target / "a_title.txt")
    assert (target / "a_title.txt").read_text(encoding="utf-8") == "hello world\n"


def test_unwritable_directory_still_returns_transcript(tmp_path, monkeypatch):
    """T-TRANSCRIPT-PERSISTENCE-009 (writer-level best-effort contract).

    A missing/unwritable directory must not raise: the write is best-effort so
    the caller can still return the transcript. The endpoint-level 200
    assertion for this scenario is covered by the endpoint integration tests.
    """
    missing = tmp_path / "does-not-exist"  # app never creates the directory
    monkeypatch.setenv("TRANSCRIPT_DIR", str(missing))

    path = save_transcript("hello", "A Title", "dQw4w9WgXcQ")

    assert path is None
    assert not (missing / "a_title.txt").exists()


def test_successful_save_logged(tmp_path, monkeypatch):
    """T-STRUCTURED-LOGGING-010"""
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    target = tmp_path / "transcripts"
    target.mkdir()
    monkeypatch.setenv("TRANSCRIPT_DIR", str(target))

    save_transcript("hello", "A Title", "dQw4w9WgXcQ")

    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event"] == "transcript_saved"
    assert entry["level"] == "info"
    assert entry["video_id"] == "dQw4w9WgXcQ"
    assert entry["path"] == str(target / "a_title.txt")
    assert entry["bytes"] == len("hello\n".encode("utf-8"))


def test_failed_save_logged(tmp_path, monkeypatch):
    """T-STRUCTURED-LOGGING-011"""
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("TRANSCRIPT_DIR", str(missing))

    save_transcript("hello", "A Title", "dQw4w9WgXcQ")

    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event"] == "transcript_save_failed"
    assert entry["level"] == "error"
    assert entry["video_id"] == "dQw4w9WgXcQ"
    # Machine-readable failure reason = the exception type name.
    assert entry["reason"] == "FileNotFoundError"


def test_failed_save_includes_path_and_detail(tmp_path, monkeypatch):
    """T-STRUCTURED-LOGGING-014"""
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("TRANSCRIPT_DIR", str(missing))

    save_transcript("hello", "A Title", "dQw4w9WgXcQ")

    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event"] == "transcript_save_failed"
    assert entry["video_id"] == "dQw4w9WgXcQ"
    assert entry["reason"] == "FileNotFoundError"
    # the attempted target path and the OS error string are both carried
    expected_path = str(missing / "a_title.txt")
    assert entry["path"] == expected_path
    assert expected_path in entry["detail"]
    assert "No such file or directory" in entry["detail"]


# --- 3. Endpoint integration -----------------------------------------------

class FakeChain:
    """Stands in for chain_mod.default_chain; returns queued results in order.

    Mirrors the project's existing chain-mocking pattern (tests/test_api.py).
    """

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
    return FetchResult(text=text, video_id=video_id, title=title,
                       language="en", source="primary")


def test_successful_fetch_writes_file(tmp_path, monkeypatch):
    """T-TRANSCRIPT-PERSISTENCE-001"""
    target = tmp_path / "transcripts"
    target.mkdir()
    monkeypatch.setenv("TRANSCRIPT_DIR", str(target))
    monkeypatch.setattr(
        chain_mod, "default_chain",
        FakeChain(results=[_result("hello world", "dQw4w9WgXcQ",
                                   "The End of LLMs? (NCM)")]),
    )
    client = TestClient(create_app())
    with client:
        response = client.post(
            "/api/transcript",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )

    assert response.status_code == 200
    fpath = target / "the_end_of_llms_ncm.txt"
    assert fpath.exists()
    assert fpath.read_text(encoding="utf-8") == response.json()["text"] + "\n"


def test_failed_fetch_writes_no_file(tmp_path, monkeypatch):
    """T-TRANSCRIPT-PERSISTENCE-002"""
    target = tmp_path / "transcripts"
    target.mkdir()
    monkeypatch.setenv("TRANSCRIPT_DIR", str(target))
    monkeypatch.setattr(
        chain_mod, "default_chain", FakeChain(error=NoCaptionsError())
    )
    client = TestClient(create_app())
    with client:
        response = client.post(
            "/api/transcript",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )

    assert response.status_code == 404
    assert list(target.iterdir()) == []


def test_refetch_overwrites_existing_file(tmp_path, monkeypatch):
    """T-TRANSCRIPT-PERSISTENCE-008"""
    target = tmp_path / "transcripts"
    target.mkdir()
    monkeypatch.setenv("TRANSCRIPT_DIR", str(target))
    monkeypatch.setattr(
        chain_mod, "default_chain",
        FakeChain(results=[
            _result("first fetch", "dQw4w9WgXcQ", "A Title"),
            _result("second fetch", "dQw4w9WgXcQ", "A Title"),
        ]),
    )
    client = TestClient(create_app())
    with client:
        client.post("/api/transcript",
                    json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
        client.post("/api/transcript",
                    json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})

    fpath = target / "a_title.txt"
    assert fpath.read_text(encoding="utf-8") == "second fetch\n"


def test_distinct_videos_same_title_last_write_wins(tmp_path, monkeypatch):
    """T-TRANSCRIPT-PERSISTENCE-011"""
    target = tmp_path / "transcripts"
    target.mkdir()
    monkeypatch.setenv("TRANSCRIPT_DIR", str(target))
    monkeypatch.setattr(
        chain_mod, "default_chain",
        FakeChain(results=[
            _result("transcript A", "aaaaaaaaaaa", "Same Title"),
            _result("transcript B", "bbbbbbbbbbb", "Same Title"),
        ]),
    )
    client = TestClient(create_app())
    with client:
        client.post("/api/transcript",
                    json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"})
        client.post("/api/transcript",
                    json={"url": "https://www.youtube.com/watch?v=bbbbbbbbbbb"})

    # Both titles derive the same file name; the most recent write wins.
    fpath = target / "same_title.txt"
    assert fpath.read_text(encoding="utf-8") == "transcript B\n"


def test_unwritable_directory_still_returns_200(tmp_path, monkeypatch):
    """T-TRANSCRIPT-PERSISTENCE-009 (endpoint-level): an unwritable transcript
    directory does not fail the request; the transcript is still returned and
    no file is written."""
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("TRANSCRIPT_DIR", str(missing))
    monkeypatch.setattr(
        chain_mod, "default_chain",
        FakeChain(results=[_result("hello", "dQw4w9WgXcQ", "A Title")]),
    )
    client = TestClient(create_app())
    with client:
        response = client.post(
            "/api/transcript",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )

    assert response.status_code == 200
    assert response.json()["text"] == "hello"
    assert not (missing / "a_title.txt").exists()
