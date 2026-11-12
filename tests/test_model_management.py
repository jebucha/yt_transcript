"""T-SUMMARIZATION-MODEL-MANAGEMENT-008 .. 028, 042 .. 045.

The model-management add/remove/discover endpoints (app/main.py), the
provider-overrides store (app/provider_overrides.py), and the discovery
module (app/model_discovery.py), tested through Starlette's TestClient
against the real app with a tmp provider config and a tmp transcript
directory — no network: the discovery HTTP seam
(``model_discovery._get_provider_models``) or the ``requests`` layer is
stubbed below the logging wrapper, so the real ``list_models`` log
emission still runs.
"""

import io
import json
import os
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import requests as requests_lib
from app import chain as chain_mod
from app import log as applog
from app import model_discovery as discovery_mod
from app.chain import FetchChain
from app.main import create_app

PROVIDER_CONFIG = {
    "provider": {
        "alpha": {
            "name": "Alpha Local",
            "options": {"baseURL": "http://127.0.0.1:41411/v1"},
            "models": {"model-a1": "Model A1", "model-a2": "Model A2"},
        },
        "beta": {
            "name": "Beta Remote",
            "options": {"baseURL": "http://127.0.0.1:41412/v1",
                        "apiKey": "sk-endpoint-test-key"},
            "models": {"model-b1": "Model B1"},
        },
    },
    "default": "alpha",
}


@pytest.fixture
def api(tmp_path, monkeypatch):
    """TestClient with a tmp provider config and a tmp transcript dir."""
    config_file = tmp_path / "providers.json"
    config_file.write_text(json.dumps(PROVIDER_CONFIG), encoding="utf-8")
    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir()
    monkeypatch.setenv("PROVIDERS_CONFIG", str(config_file))
    monkeypatch.setenv("TRANSCRIPT_DIR", str(transcript_dir))
    client = TestClient(create_app())
    with client:
        yield {
            "client": client,
            "config_file": config_file,
            "transcript_dir": transcript_dir,
        }


def _entries(buf, event=None) -> list[dict]:
    lines = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    return lines if event is None else [e for e in lines if e.get("event") == event]


def _override_file(api) -> "Path":
    return api["transcript_dir"] / "provider_overrides.json"


def _alpha_models(api) -> list[str]:
    body = api["client"].get("/api/providers").json()
    return next(p for p in body["providers"] if p["id"] == "alpha")["models"]


def _block_transcript_dir(api, monkeypatch):
    """Redirect TRANSCRIPT_DIR to a missing (never created) directory so
    writes deterministically fail, while the original directory stays
    readable for the follow-up assertions."""
    monkeypatch.setenv(
        "TRANSCRIPT_DIR", str(api["transcript_dir"].parent / "gone")
    )


def _restore_transcript_dir(api, monkeypatch):
    monkeypatch.setenv("TRANSCRIPT_DIR", str(api["transcript_dir"]))


@pytest.fixture
def readonly_dir():
    """Yield a function that makes the transcript directory read-only so a
    read of the (pre-existing) overlay succeeds but the write (a sibling
    temp file + ``os.replace``) fails with PermissionError. Restores the
    writable mode afterwards."""
    created = []

    def make_readonly(path):
        original = path.stat().st_mode
        os.chmod(path, 0o555)  # r-x: readable/traversable, not writable
        created.append((path, original))

    yield make_readonly

    for path, original in reversed(created):
        os.chmod(path, original)


# --- T-SUMMARIZATION-MODEL-MANAGEMENT-008 .. 012: add endpoint -----------------


def test_add_model_persists_and_lists(api):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-008"""
    response = api["client"].post(
        "/api/providers/alpha/models", json={"model": "model-a3"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "alpha"
    assert body["model"] == "model-a3"
    assert body["models"] == ["model-a1", "model-a2", "model-a3"]
    # the overrides file persists the id ...
    assert json.loads(_override_file(api).read_text(encoding="utf-8")) == {
        "alpha": ["model-a3"]
    }
    # ...and a subsequent provider listing includes it after the file models
    assert _alpha_models(api) == ["model-a1", "model-a2", "model-a3"]


def test_add_existing_model_is_idempotent(api):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-009"""
    # an overlay id already in the effective list: 200, exactly once
    api["client"].post("/api/providers/alpha/models", json={"model": "model-c"})
    response = api["client"].post(
        "/api/providers/alpha/models", json={"model": "model-c"}
    )
    assert response.status_code == 200
    assert response.json()["models"] == ["model-a1", "model-a2", "model-c"]
    assert _alpha_models(api) == ["model-a1", "model-a2", "model-c"]

    # a config-file id: 200, left alone — no write, no duplication
    response = api["client"].post(
        "/api/providers/alpha/models", json={"model": "model-a1"}
    )
    assert response.status_code == 200
    assert response.json()["models"] == ["model-a1", "model-a2", "model-c"]
    persisted = json.loads(_override_file(api).read_text(encoding="utf-8"))
    assert persisted == {"alpha": ["model-c"]}


def test_add_unknown_provider_rejected(api):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-010"""
    response = api["client"].post(
        "/api/providers/ghost/models", json={"model": "model-x"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PROVIDER"
    assert not _override_file(api).exists()


def test_add_write_failure_no_partial_state(api, monkeypatch):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-011"""
    _block_transcript_dir(api, monkeypatch)
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    response = api["client"].post(
        "/api/providers/alpha/models", json={"model": "model-a3"}
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "WRITE_FAILED"
    # the failure is logged ...
    failed = _entries(buf, "provider_overrides_save_failed")
    assert len(failed) == 1
    assert failed[0]["path"]
    assert failed[0]["reason"]
    # ...no partial state was left, and the effective model list is
    # unchanged once the directory is readable again
    _restore_transcript_dir(api, monkeypatch)
    assert not _override_file(api).exists()
    assert _alpha_models(api) == ["model-a1", "model-a2"]


def test_add_during_in_flight_fetch_succeeds(api, monkeypatch):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-012"""
    import threading

    # A real chain whose fetcher blocks until released: it holds the
    # single-flight semaphore for the whole in-flight window.
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

    def fetch_thread():
        api["client"].post(
            "/api/transcript",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )

    thread = threading.Thread(target=fetch_thread)
    thread.start()
    try:
        assert fetch_started.wait(timeout=10)  # the fetch is in flight
        response = api["client"].post(
            "/api/providers/alpha/models", json={"model": "model-a3"}
        )
        assert response.status_code == 200
        assert response.json()["models"] == ["model-a1", "model-a2", "model-a3"]
        # the add did not invoke the fetch chain or touch its limit
        assert fetch_calls == ["dQw4w9WgXcQ"]
    finally:
        release_fetch.set()
        thread.join(timeout=15)


# --- T-SUMMARIZATION-MODEL-MANAGEMENT-013 .. 017: validation and bounds --------


def test_add_blank_model_rejected(api):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-013"""
    for blank in ("", "   \t\n  "):
        response = api["client"].post(
            "/api/providers/alpha/models", json={"model": blank}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_MODEL"
    # nothing is written
    assert not _override_file(api).exists()


def test_add_overlong_model_rejected(api):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-014"""
    response = api["client"].post(
        "/api/providers/alpha/models", json={"model": "x" * 201}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_MODEL"
    assert not _override_file(api).exists()

    # exactly at the cap: accepted
    response = api["client"].post(
        "/api/providers/alpha/models", json={"model": "y" * 200}
    )
    assert response.status_code == 200


def test_add_control_char_model_rejected(api):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-015"""
    for model_id in ("model\x01a", "model\x1fa", "model\x7fa", "model\x9fa"):
        response = api["client"].post(
            "/api/providers/alpha/models", json={"model": model_id}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_MODEL"
    assert not _override_file(api).exists()


def test_add_per_provider_cap_enforced(api):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-016"""
    overrides_file = _override_file(api)
    existing = [f"bulk-{i:02d}" for i in range(50)]
    overrides_file.write_text(json.dumps({"alpha": existing}), encoding="utf-8")

    response = api["client"].post(
        "/api/providers/alpha/models", json={"model": "model-a3"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_MODEL"
    # nothing is written: the cap-sized list is untouched
    assert json.loads(overrides_file.read_text(encoding="utf-8")) == {
        "alpha": existing
    }

    # an already-present id stays an idempotent success at the cap
    response = api["client"].post(
        "/api/providers/alpha/models", json={"model": existing[0]}
    )
    assert response.status_code == 200


def test_add_invalid_body_rejected(api):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-017"""
    # a non-object body, a missing "model" field, and a non-string model
    for body in ([1, 2, 3], {"other": "x"}, {"model": 42}, "just a string"):
        response = api["client"].post(
            "/api/providers/alpha/models", json=body
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_BODY"

    # and an unparseable body
    response = api["client"].post(
        "/api/providers/alpha/models",
        content=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_BODY"

    # nothing is written
    assert not _override_file(api).exists()


# --- T-SUMMARIZATION-MODEL-MANAGEMENT-018 .. 022: remove endpoint --------------


def test_remove_added_model(api):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-018"""
    api["client"].post("/api/providers/alpha/models", json={"model": "model-c"})

    response = api["client"].request("DELETE",
        "/api/providers/alpha/models", json={"model": "model-c"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "alpha"
    assert body["model"] == "model-c"
    assert body["models"] == ["model-a1", "model-a2"]
    # the overrides file no longer contains it ...
    persisted = json.loads(_override_file(api).read_text(encoding="utf-8"))
    assert "model-c" not in persisted.get("alpha", [])
    # ...and the provider listing no longer offers it
    assert _alpha_models(api) == ["model-a1", "model-a2"]


def test_remove_file_model_rejected(api):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-019"""
    response = api["client"].request("DELETE",
        "/api/providers/alpha/models", json={"model": "model-a1"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MODEL_NOT_REMOVABLE"
    # the model remains in the effective list, and no overlay was created
    assert _alpha_models(api) == ["model-a1", "model-a2"]
    assert not _override_file(api).exists()


def test_remove_absent_model_404(api):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-020"""
    response = api["client"].request("DELETE",
        "/api/providers/alpha/models", json={"model": "model-zz"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert not _override_file(api).exists()


def test_remove_unknown_provider_rejected(api):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-021"""
    response = api["client"].request("DELETE",
        "/api/providers/ghost/models", json={"model": "model-x"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PROVIDER"
    assert not _override_file(api).exists()


def test_remove_write_failure_no_partial_state(api, readonly_dir):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-022"""
    api["client"].post("/api/providers/alpha/models", json={"model": "model-c"})
    # The overlay must be *readable* (so the model is found) but the
    # directory *unwritable* (so the atomic write fails).
    readonly_dir(api["transcript_dir"])
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    response = api["client"].request("DELETE",
        "/api/providers/alpha/models", json={"model": "model-c"}
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "WRITE_FAILED"
    failed = _entries(buf, "provider_overrides_save_failed")
    assert len(failed) == 1
    # the model remains listed: the on-disk overlay is untouched
    assert "model-c" in json.loads(
        _override_file(api).read_text(encoding="utf-8")
    ).get("alpha", [])
    assert _alpha_models(api) == ["model-a1", "model-a2", "model-c"]


# --- T-SUMMARIZATION-MODEL-MANAGEMENT-042, 044: logging -------------------------


def test_add_and_remove_are_logged(api):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-042"""
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    assert (
        api["client"].post(
            "/api/providers/alpha/models", json={"model": "model-c"}
        ).status_code
        == 200
    )
    assert (
        api["client"].request("DELETE",
            "/api/providers/alpha/models", json={"model": "model-c"}
        ).status_code
        == 200
    )

    added = _entries(buf, "provider_model_added")
    assert len(added) == 1
    assert added[0]["level"] == "info"
    assert added[0]["provider"] == "alpha"
    assert added[0]["model"] == "model-c"

    removed = _entries(buf, "provider_model_removed")
    assert len(removed) == 1
    assert removed[0]["level"] == "info"
    assert removed[0]["provider"] == "alpha"
    assert removed[0]["model"] == "model-c"


def test_overlay_failures_logged(api, monkeypatch):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-044"""
    # A malformed overlay file: exactly one load-failure event carrying the
    # path and the parse detail — never the file's contents.
    marker = "SECRET_OVERRIDE_CONTENT_MARKER_99"
    overrides_file = _override_file(api)
    overrides_file.write_text(f'{{"alpha": [{marker}]', encoding="utf-8")
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    assert api["client"].get("/api/providers").status_code == 200
    load_failed = _entries(buf, "provider_overrides_load_failed")
    assert len(load_failed) == 1
    event = load_failed[0]
    assert event["level"] == "error"
    assert event["path"] == str(overrides_file)
    assert event["reason"]
    assert event["detail"]
    assert marker not in buf.getvalue()

    # An unwritable directory: the save failure is logged the same way.
    _block_transcript_dir(api, monkeypatch)
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    response = api["client"].post(
        "/api/providers/alpha/models", json={"model": "model-a3"}
    )
    assert response.status_code == 500
    save_failed = _entries(buf, "provider_overrides_save_failed")
    assert len(save_failed) == 1
    event = save_failed[0]
    assert event["level"] == "error"
    assert event["path"]
    assert event["reason"]
    assert event["detail"]


# --- T-SUMMARIZATION-MODEL-MANAGEMENT-023 .. 028, 043, 045: discovery ---------


class _FakeGetResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        if self._body is _NOT_JSON:
            raise ValueError("No JSON object could be decoded")
        return self._body


_NOT_JSON = object()


def _recorded_get(monkeypatch, responder):
    """Install a recording ``requests.get``; ``responder(call) -> response``."""
    calls = []

    def fake_get(url, headers=None, timeout=None):
        call = {"url": url, "headers": dict(headers or {}), "timeout": timeout}
        calls.append(call)
        return responder(call)

    monkeypatch.setattr(discovery_mod.requests, "get", fake_get)
    return calls


def _stub_discovery(monkeypatch, data):
    """Stub the HTTP seam to return a fixed ``/models`` body."""
    def stub(base_url, api_key, timeout):
        return data

    monkeypatch.setattr(discovery_mod, "_get_provider_models", stub)


def test_discover_models_returns_ids(api, monkeypatch):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-023"""
    # ids kept in order, duplicates removed, non-strings / non-dicts /
    # non-string-ids ignored.
    _stub_discovery(monkeypatch, {
        "data": [
            {"id": "m1"},
            {"id": "m2"},
            {"id": "m1"},  # duplicate
            "not-a-dict",
            {"id": 42},  # non-string id
            {"id": ""},  # empty id
            {"name": "no id field"},
            {"id": "m3"},
        ]
    })

    response = api["client"].get("/api/providers/alpha/available-models")

    assert response.status_code == 200
    assert response.json() == {"models": ["m1", "m2", "m3"]}


def test_discover_auth_header_only_when_key_present(api, monkeypatch):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-024"""
    ok = lambda call: _FakeGetResponse({"data": []})

    # a keyless provider's request carries no authorization header ...
    calls = _recorded_get(monkeypatch, ok)
    response = api["client"].get("/api/providers/alpha/available-models")
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["url"] == "http://127.0.0.1:41411/v1/models"
    assert calls[0]["timeout"] == discovery_mod.DEFAULT_DISCOVERY_TIMEOUT
    assert "Authorization" not in calls[0]["headers"]

    # ...while a keyed provider's request carries that key as a bearer token
    calls = _recorded_get(monkeypatch, ok)
    response = api["client"].get("/api/providers/beta/available-models")
    assert response.status_code == 200
    assert calls[0]["url"] == "http://127.0.0.1:41412/v1/models"
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-endpoint-test-key"


def test_discover_unknown_provider_rejected(api, monkeypatch):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-025"""
    calls = _recorded_get(monkeypatch, lambda call: _FakeGetResponse({"data": []}))

    response = api["client"].get("/api/providers/ghost/available-models")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PROVIDER"
    # no backend request was made
    assert calls == []


def test_discover_backend_failure_returns_502(api, monkeypatch):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-026"""
    def raise_exc(exc):
        def _get(url, headers=None, timeout=None):
            raise exc
        return _get

    # unreachable / timeout
    for exc, reason in (
        (requests_lib.ConnectionError(), "unreachable"),
        (requests_lib.Timeout(), "timeout"),
    ):
        _recorded_get(monkeypatch, raise_exc(exc))
        response = api["client"].get("/api/providers/alpha/available-models")
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "PROVIDER_ERROR"

    # non-2xx status
    _recorded_get(
        monkeypatch, lambda call: _FakeGetResponse(None, status_code=500)
    )
    response = api["client"].get("/api/providers/alpha/available-models")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "PROVIDER_ERROR"

    # malformed body (invalid JSON)
    _recorded_get(monkeypatch, lambda call: _FakeGetResponse(_NOT_JSON))
    response = api["client"].get("/api/providers/alpha/available-models")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "PROVIDER_ERROR"


def test_discover_response_omits_secrets(api, monkeypatch):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-027"""
    _stub_discovery(monkeypatch, {"data": [{"id": "model-b1"}]})

    response = api["client"].get("/api/providers/beta/available-models")

    assert response.status_code == 200
    assert response.json() == {"models": ["model-b1"]}
    # neither the API key nor the base URL appears anywhere in the body
    assert "sk-endpoint-test-key" not in response.text
    assert "41412" not in response.text


def test_discover_during_in_flight_fetch_succeeds(api, monkeypatch):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-028"""
    import threading

    # A real chain whose fetcher blocks until released: it holds the
    # single-flight semaphore for the whole in-flight window.
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
    _stub_discovery(monkeypatch, {"data": [{"id": "m1"}]})

    def fetch_thread():
        api["client"].post(
            "/api/transcript",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )

    thread = threading.Thread(target=fetch_thread)
    thread.start()
    try:
        assert fetch_started.wait(timeout=10)  # the fetch is in flight
        response = api["client"].get("/api/providers/alpha/available-models")
        assert response.status_code == 200
        assert response.json() == {"models": ["m1"]}
        # discovery did not invoke the fetch chain or touch its limit
        assert fetch_calls == ["dQw4w9WgXcQ"]
    finally:
        release_fetch.set()
        thread.join(timeout=15)


def test_discovery_failure_logged(api, monkeypatch):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-043"""
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    _recorded_get(
        monkeypatch,
        lambda *a, **kw: (_ for _ in ()).throw(requests_lib.ConnectionError()),
    )
    response = api["client"].get("/api/providers/alpha/available-models")

    assert response.status_code == 502
    failed = _entries(buf, "provider_models_refresh_failed")
    assert len(failed) == 1
    event = failed[0]
    assert event["level"] == "error"
    # machine-readable reason + a safe detail (type name, never the URL)
    assert event["provider"] == "alpha"
    assert event["reason"] == "unreachable"
    assert event["detail"] == "ConnectionError"
    assert "41411" not in event["detail"]


def test_logs_carry_no_secrets(api, monkeypatch):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-045"""
    # A keyed provider is used for add, remove, and a successful discovery.
    _stub_discovery(monkeypatch, {"data": [{"id": "model-b1"}]})
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    assert (
        api["client"].post(
            "/api/providers/beta/models", json={"model": "model-b2"}
        ).status_code
        == 200
    )
    assert api["client"].get("/api/providers/beta/available-models").status_code == 200
    assert (
        api["client"].request(
            "DELETE", "/api/providers/beta/models", json={"model": "model-b2"}
        ).status_code
        == 200
    )

    out = buf.getvalue()
    # no emitted log event carries the API key or the base URL
    assert "sk-endpoint-test-key" not in out
    assert "41412" not in out
