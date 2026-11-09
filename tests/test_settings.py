"""T-APP-SETTINGS-001 .. 009 (+ module-level tests for app/settings.py).

Settings persistence (app/settings.py) tested directly against tmp_path, and
the /api/settings endpoints (app/main.py) through TestClient. The transcript
directory is redirected per test via TRANSCRIPT_DIR.
"""

import io
import json
import threading

import pytest
from starlette.testclient import TestClient

from app import chain as chain_mod
from app import log as applog
from app.chain import FetchChain
from app.main import create_app
from app.settings import load_settings, save_settings, settings_path


# --- module-level: load defaults, per-request re-read, atomic write ---------


def test_module_load_missing_file_defaults_off(tmp_path, monkeypatch):
    """A missing settings file is the normal off-default, unlogged, and no
    file is created."""
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path / "absent"))
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    assert load_settings().auto_summarize is False

    assert not (tmp_path / "absent").exists()
    entries = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    assert not [e for e in entries if e.get("event") == "settings_load_failed"]


def test_module_load_stored_flag(tmp_path, monkeypatch):
    """A stored boolean is returned verbatim (both values)."""
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))
    settings_path().write_text(json.dumps({"autoSummarize": True}),
                               encoding="utf-8")
    assert load_settings().auto_summarize is True

    settings_path().write_text(json.dumps({"autoSummarize": False}),
                               encoding="utf-8")
    assert load_settings().auto_summarize is False


def test_module_load_unusable_defaults_off(tmp_path, monkeypatch):
    """Malformed JSON, a non-object top level, and a non-boolean flag all
    yield off; the malformed cases log once without echoing file contents."""
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))
    marker = "SECRET_SETTINGS_CONTENT_MARKER_99"

    # malformed JSON -> off + one settings_load_failed event, no contents
    settings_path().write_text(f'{{"autoSummarize": {marker}}}',
                               encoding="utf-8")
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    assert load_settings().auto_summarize is False
    entries = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    failures = [e for e in entries if e.get("event") == "settings_load_failed"]
    assert len(failures) == 1
    assert failures[0]["reason"] == "invalid_json"
    assert marker not in buf.getvalue()

    # non-object top level -> off + one event
    settings_path().write_text("[true]", encoding="utf-8")
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    assert load_settings().auto_summarize is False
    events = [e for e in
              (json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip())
              if e.get("event") == "settings_load_failed"]
    assert len(events) == 1

    # non-boolean flag -> off, no crash
    settings_path().write_text(json.dumps({"autoSummarize": "yes"}),
                               encoding="utf-8")
    assert load_settings().auto_summarize is False


def test_module_rereads_per_call(tmp_path, monkeypatch):
    """The file is read on every call: an on-disk edit takes effect on the
    next load without any restart."""
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))
    settings_path().write_text(json.dumps({"autoSummarize": False}),
                               encoding="utf-8")
    assert load_settings().auto_summarize is False

    settings_path().write_text(json.dumps({"autoSummarize": True}),
                               encoding="utf-8")
    assert load_settings().auto_summarize is True


def test_module_save_atomic_roundtrip(tmp_path, monkeypatch):
    """save_settings writes valid JSON through a sibling temp file and
    reports success; no temp file is left behind."""
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))

    assert save_settings(True) is True
    assert json.loads(settings_path().read_text(encoding="utf-8")) == {
        "autoSummarize": True
    }
    # only the settings file exists: the temp file was renamed away
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]

    # overwrite keeps the file valid and readable
    assert save_settings(False) is True
    assert load_settings().auto_summarize is False


def test_module_save_failure_returns_false(tmp_path, monkeypatch):
    """An unwritable target (missing directory) returns False without
    raising and logs settings_save_failed once."""
    missing = tmp_path / "does-not-exist"  # the app never creates it
    monkeypatch.setenv("TRANSCRIPT_DIR", str(missing))
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    assert save_settings(True) is False

    entries = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    failures = [e for e in entries if e.get("event") == "settings_save_failed"]
    assert len(failures) == 1
    assert failures[0]["path"] == str(missing / "settings.json")


# --- endpoint fixture ---------------------------------------------------------


@pytest.fixture
def api(tmp_path, monkeypatch):
    """TestClient with a tmp transcript dir (no provider config needed: the
    settings endpoints are provider-free)."""
    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir()
    monkeypatch.setenv("TRANSCRIPT_DIR", str(transcript_dir))
    client = TestClient(create_app())
    with client:
        yield {"client": client, "transcript_dir": transcript_dir}


def _settings_file(api):
    return api["transcript_dir"] / "settings.json"


# --- T-APP-SETTINGS-001 .. 004: GET /api/settings -----------------------------


def test_settings_read_returns_stored_flag(api):
    """T-APP-SETTINGS-001"""
    _settings_file(api).write_text(json.dumps({"autoSummarize": True}),
                                   encoding="utf-8")

    response = api["client"].get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {"autoSummarize": True}


def test_settings_read_missing_file_defaults_off(api):
    """T-APP-SETTINGS-002"""
    response = api["client"].get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {"autoSummarize": False}
    # the read never creates the file
    assert not _settings_file(api).exists()


def test_settings_read_unusable_file_defaults_off(api):
    """T-APP-SETTINGS-003"""
    marker = "SECRET_SETTINGS_CONTENT_MARKER_99"
    _settings_file(api).write_text(f'{{"autoSummarize": {marker}}}',
                                   encoding="utf-8")
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    response = api["client"].get("/api/settings")  # no crash

    assert response.status_code == 200
    assert response.json() == {"autoSummarize": False}
    # the failure is visible in the log...
    entries = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    assert [e for e in entries if e.get("event") == "settings_load_failed"]
    # ...and the file contents never appear in the response
    assert marker not in response.text

    # a non-boolean flag is the same safe off-default
    _settings_file(api).write_text(json.dumps({"autoSummarize": "true"}),
                                   encoding="utf-8")
    response = api["client"].get("/api/settings")
    assert response.status_code == 200
    assert response.json() == {"autoSummarize": False}


def test_settings_edit_takes_effect_without_restart(api):
    """T-APP-SETTINGS-004"""
    assert api["client"].get("/api/settings").json()["autoSummarize"] is False

    _settings_file(api).write_text(json.dumps({"autoSummarize": True}),
                                   encoding="utf-8")

    assert api["client"].get("/api/settings").json()["autoSummarize"] is True


# --- T-APP-SETTINGS-005 .. 007: POST /api/settings ----------------------------


def test_settings_write_persists_and_echoes(api):
    """T-APP-SETTINGS-005"""
    response = api["client"].post("/api/settings",
                                  json={"autoSummarize": True})

    assert response.status_code == 200
    assert response.json() == {"autoSummarize": True}
    assert json.loads(_settings_file(api).read_text(encoding="utf-8")) == {
        "autoSummarize": True
    }
    assert api["client"].get("/api/settings").json() == {"autoSummarize": True}


def test_settings_write_invalid_body_rejected(api):
    """T-APP-SETTINGS-006"""
    _settings_file(api).write_text(json.dumps({"autoSummarize": True}),
                                   encoding="utf-8")

    for bad_body in ([1, 2], "true", 42, None, {},
                     {"autoSummarize": "true"}, {"autoSummarize": 1},
                     {"other": True}):
        response = api["client"].post("/api/settings", json=bad_body)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_BODY"

    # a non-JSON body is rejected the same way
    response = api["client"].post(
        "/api/settings", content="not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_BODY"

    # the settings file is unchanged by every rejection
    assert json.loads(_settings_file(api).read_text(encoding="utf-8")) == {
        "autoSummarize": True
    }
    # ...and a rejection against a missing file never creates it
    _settings_file(api).unlink()
    response = api["client"].post("/api/settings", json={"autoSummarize": "x"})
    assert response.status_code == 400
    assert not _settings_file(api).exists()


def test_settings_write_unwritable_directory_fails(api, monkeypatch):
    """T-APP-SETTINGS-007"""
    assert api["client"].post("/api/settings",
                              json={"autoSummarize": True}).status_code == 200

    # Redirect to a missing (never created) directory: writes now fail...
    monkeypatch.setenv("TRANSCRIPT_DIR",
                       str(api["transcript_dir"].parent / "gone"))
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    response = api["client"].post("/api/settings",
                                  json={"autoSummarize": False})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "WRITE_FAILED"
    entries = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    assert [e for e in entries if e.get("event") == "settings_save_failed"]

    # ...and the previously stored value is still readable
    monkeypatch.setenv("TRANSCRIPT_DIR", str(api["transcript_dir"]))
    assert api["client"].get("/api/settings").json() == {"autoSummarize": True}


# --- T-APP-SETTINGS-008 .. 009: isolation and independence --------------------


def test_settings_file_excluded_from_transcript_list(api):
    """T-APP-SETTINGS-008"""
    (api["transcript_dir"] / "a_video.txt").write_text("body\n",
                                                      encoding="utf-8")
    assert api["client"].post("/api/settings",
                              json={"autoSummarize": True}).status_code == 200

    listing = api["client"].get("/api/transcripts").json()["transcripts"]

    names = [entry["name"] for entry in listing]
    assert names == ["a_video.txt"]
    assert "settings.json" not in names


def test_settings_during_in_flight_fetch_succeeds(api, monkeypatch):
    """T-APP-SETTINGS-009"""
    # A real chain whose fetcher blocks until released: it holds the
    # single-flight semaphore for the whole in-flight window (same stub
    # pattern as T-TRANSCRIPT-SUMMARIZATION-017).
    fetch_started = threading.Event()
    release_fetch = threading.Event()
    fetch_calls = []

    def blocking_fetch(video_id, requested_language):
        fetch_calls.append(video_id)
        fetch_started.set()
        release_fetch.wait(timeout=10)
        return ("fetched text", "en", "A Title")

    chain = FetchChain(primary=blocking_fetch, fallback=blocking_fetch)
    monkeypatch.setattr(chain_mod, "default_chain", chain)

    holder = {}

    def fetch_thread():
        holder["response"] = api["client"].post(
            "/api/transcript",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )

    thread = threading.Thread(target=fetch_thread)
    thread.start()
    try:
        assert fetch_started.wait(timeout=10)  # the fetch is in flight
        response = api["client"].get("/api/settings")
        assert response.status_code == 200
        assert response.json() == {"autoSummarize": False}
        response = api["client"].post("/api/settings",
                                      json={"autoSummarize": True})
        assert response.status_code == 200
        assert response.json() == {"autoSummarize": True}
        # the settings requests did not invoke the fetch chain
        assert fetch_calls == ["dQw4w9WgXcQ"]
    finally:
        release_fetch.set()
        thread.join(timeout=15)
