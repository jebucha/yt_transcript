"""T-TRANSCRIPT-SUMMARIZATION-001 .. 039 (+ T-STRUCTURED-LOGGING-015 .. 019).

Provider config reading (app/providers.py), the summarize backend
(app/summarize.py), and the summarization endpoints (app/main.py),
unit-tested against tmp_path with a mocked HTTP layer.
"""

import io
import json

import pytest
from starlette.testclient import TestClient

from app import chain as chain_mod
from app import log as applog
from app import summarize as summarize_mod
from app.chain import FetchChain, FetchResult
from app.errors import ProviderError
from app.main import create_app
from app.providers import Provider, load_providers


def _write_config(path, payload) -> str:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_providers_read_from_config_file(tmp_path, monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-001"""
    config = {
        "provider": {
            "radai": {
                "name": "Radai Local",
                "options": {"baseURL": "http://localhost:8181/v1"},
                "models": {"qwen3.5-27b": "Qwen 3.5 27B"},
            }
        }
    }
    monkeypatch.setenv("PROVIDERS_CONFIG", _write_config(tmp_path / "providers.json", config))

    result = load_providers()

    assert len(result.providers) == 1
    provider = result.providers[0]
    assert provider.id == "radai"
    assert provider.name == "Radai Local"
    assert provider.base_url == "http://localhost:8181/v1"
    assert provider.api_key is None
    assert provider.models == ("qwen3.5-27b",)
    assert result.default == "radai"


def test_config_path_from_environment(tmp_path, monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-002"""
    # A different directory holds the real file; the working directory has no
    # providers.json of its own.
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "PROVIDERS_CONFIG",
        _write_config(other / "custom-providers.json", {
            "provider": {
                "lmstudio": {
                    "name": "LM Studio",
                    "options": {"baseURL": "http://localhost:1234/v1"},
                    "models": {"llama-3.1-8b": "Llama 3.1 8B"},
                }
            }
        }),
    )

    result = load_providers()

    assert [p.id for p in result.providers] == ["lmstudio"]
    assert result.default == "lmstudio"


def test_config_edit_takes_effect_without_restart(tmp_path, monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-003"""
    config_file = tmp_path / "providers.json"

    def two_providers():
        return {
            "provider": {
                "alpha": {
                    "name": "Alpha",
                    "options": {"baseURL": "http://localhost:1111/v1"},
                    "models": {"m1": "M1"},
                },
                "beta": {
                    "name": "Beta",
                    "options": {"baseURL": "http://localhost:2222/v1"},
                    "models": {"m2": "M2"},
                },
            }
        }

    monkeypatch.setenv("PROVIDERS_CONFIG", _write_config(config_file, two_providers()))
    assert [p.id for p in load_providers().providers] == ["alpha", "beta"]

    # The provider is removed from the file after the app already served a
    # request; the next read must no longer contain it.
    edited = two_providers()
    del edited["provider"]["beta"]
    _write_config(config_file, edited)

    result = load_providers()
    assert [p.id for p in result.providers] == ["alpha"]
    assert result.default == "alpha"


def test_malformed_config_treated_as_not_configured(tmp_path, monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-004"""
    marker = "SECRET_CONFIG_CONTENT_MARKER_42"
    config_file = tmp_path / "providers.json"
    config_file.write_text(f'{{"provider": {{{marker}}}', encoding="utf-8")
    monkeypatch.setenv("PROVIDERS_CONFIG", str(config_file))

    # No request crashes: the read returns the not-configured result...
    result = load_providers()
    assert result.providers == ()
    assert result.default is None

    # ...and a missing file (the normal state) is not logged as a failure.
    monkeypatch.setenv("PROVIDERS_CONFIG", str(tmp_path / "absent.json"))
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    assert load_providers().providers == ()
    entries = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    assert not [e for e in entries if e.get("event") == "config_load_failed"]


def test_unknown_config_fields_ignored(tmp_path, monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-005"""
    config = {
        "$schema": "https://example.com/schemas/providers.json",
        "default": "radai",
        "provider": {
            "radai": {
                "name": "Radai Local",
                "npm": {"name": "radai-node", "version": "1.2.3"},
                "options": {
                    "baseURL": "http://localhost:8181/v1",
                    "apiKey": "sk-test-key",
                    "maxRetries": 3,
                },
                "models": {"model-a": "Model A", "model-b": "Model B"},
            }
        },
        "someOtherTopLevelField": True,
    }
    monkeypatch.setenv("PROVIDERS_CONFIG", _write_config(tmp_path / "providers.json", config))

    result = load_providers()

    assert len(result.providers) == 1
    provider = result.providers[0]
    assert provider.id == "radai"
    assert provider.name == "Radai Local"
    assert provider.api_key == "sk-test-key"
    assert provider.models == ("model-a", "model-b")
    assert result.default == "radai"


def test_missing_display_name_falls_back_to_id(tmp_path, monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-038"""
    config = {
        "provider": {
            "radai": {
                # no "name" field at all
                "options": {"baseURL": "http://localhost:8181/v1"},
                "models": {"qwen3.5-27b": "Qwen 3.5 27B"},
            },
            "lmstudio": {
                # an empty display name
                "name": "",
                "options": {"baseURL": "http://localhost:1234/v1"},
                "models": {"llama-3.1-8b": "Llama 3.1 8B"},
            },
        }
    }
    monkeypatch.setenv("PROVIDERS_CONFIG", _write_config(tmp_path / "providers.json", config))

    result = load_providers()

    assert [p.id for p in result.providers] == ["radai", "lmstudio"]
    by_id = {p.id: p for p in result.providers}
    # both entries stay usable; the display name falls back to the id
    assert by_id["radai"].name == "radai"
    assert by_id["lmstudio"].name == "lmstudio"


def test_config_load_failure_logged(tmp_path, monkeypatch):
    """T-STRUCTURED-LOGGING-019"""
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    config_file = tmp_path / "providers.json"
    marker = "SECRET_CONFIG_CONTENT_MARKER_77"
    config_file.write_text(f'{{"provider": {{{marker}}}', encoding="utf-8")
    monkeypatch.setenv("PROVIDERS_CONFIG", str(config_file))

    result = load_providers()

    assert result.providers == () and result.default is None
    entries = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    failed = [e for e in entries if e.get("event") == "config_load_failed"]
    assert len(failed) == 1
    event = failed[0]
    assert event["level"] == "error"
    assert event["path"] == str(config_file)
    assert event["reason"]
    assert event["detail"]
    # the parse error detail is present, but never the file's contents
    assert marker not in buf.getvalue()


# --- backend call (app/summarize.py, mocked HTTP layer) ------------------------

def _provider(api_key=None):
    return Provider(
        id="radai", name="Radai Local",
        base_url="http://localhost:8181/v1", api_key=api_key,
        models=("model-a",),
    )


def _fake_response(content, status_code=200):
    class FakeResponse:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            if content is _NOT_JSON:
                raise ValueError("No JSON object could be decoded")
            return content

    return FakeResponse()


_NOT_JSON = object()


def _install_fake_post(monkeypatch, post):
    monkeypatch.setattr(summarize_mod.requests, "post", post)


def _recorded_post(monkeypatch, responder):
    """Install a recording requests.post; responder(call) -> FakeResponse."""
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        call = {
            "url": url, "json": json,
            "headers": dict(headers or {}), "timeout": timeout,
        }
        calls.append(call)
        return responder(call)

    _install_fake_post(monkeypatch, fake_post)
    return calls


def test_summarize_sends_chat_completions_shape(monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-010"""
    monkeypatch.delenv("SUMMARY_TIMEOUT", raising=False)
    transcript = "The transcript text to summarize."
    calls = _recorded_post(
        monkeypatch,
        lambda call: _fake_response(
            {"choices": [{"message": {"content": "The summary."}}]}
        ),
    )

    summary = summarize_mod.summarize_with_provider(
        _provider(), "model-a", transcript
    )

    assert summary == "The summary."
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == "http://localhost:8181/v1/chat/completions"
    assert call["timeout"] == summarize_mod.DEFAULT_SUMMARY_TIMEOUT
    body = call["json"]
    # chat completions form: a message list, not a bare prompt
    assert body["model"] == "model-a"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["messages"][1]["content"] == transcript
    # the output length is bounded
    assert body["max_tokens"] == summarize_mod.MAX_OUTPUT_TOKENS


def test_summary_timeout_from_environment(monkeypatch):
    monkeypatch.setenv("SUMMARY_TIMEOUT", "15")
    calls = _recorded_post(
        monkeypatch,
        lambda call: _fake_response({"choices": [{"message": {"content": "s"}}]}),
    )
    summarize_mod.summarize_with_provider(_provider(), "model-a", "text")
    assert calls[0]["timeout"] == 15.0

    # non-numeric values fall back to the default (same style as PORT)
    monkeypatch.setenv("SUMMARY_TIMEOUT", "not-a-number")
    calls = _recorded_post(
        monkeypatch,
        lambda call: _fake_response({"choices": [{"message": {"content": "s"}}]}),
    )
    summarize_mod.summarize_with_provider(_provider(), "model-a", "text")
    assert calls[0]["timeout"] == summarize_mod.DEFAULT_SUMMARY_TIMEOUT


def test_auth_header_only_when_key_present(monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-011"""
    ok = lambda call: _fake_response({"choices": [{"message": {"content": "s"}}]})

    calls = _recorded_post(monkeypatch, ok)
    summarize_mod.summarize_with_provider(_provider(), "model-a", "text")
    assert "Authorization" not in calls[0]["headers"]

    calls = _recorded_post(monkeypatch, ok)
    summarize_mod.summarize_with_provider(_provider(api_key="sk-test-key-9"), "model-a", "text")
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-test-key-9"


def test_backend_failures_raise_provider_error(monkeypatch):
    """The machine-readable failure reasons (design decision 1)."""
    import requests

    # unreachable
    def raise_unreachable(url, json=None, headers=None, timeout=None):
        raise requests.ConnectionError()
    monkeypatch.setattr(summarize_mod.requests, "post", raise_unreachable)
    with pytest.raises(ProviderError) as excinfo:
        summarize_mod.summarize_with_provider(_provider(), "model-a", "text")
    assert excinfo.value.code == "PROVIDER_ERROR" and excinfo.value.status == 502

    # timeout
    def raise_timeout(url, json=None, headers=None, timeout=None):
        raise requests.Timeout()
    monkeypatch.setattr(summarize_mod.requests, "post", raise_timeout)
    with pytest.raises(ProviderError):
        summarize_mod.summarize_with_provider(_provider(), "model-a", "text")

    # http_error
    _recorded_post(monkeypatch, lambda call: _fake_response(None, status_code=500))
    with pytest.raises(ProviderError):
        summarize_mod.summarize_with_provider(_provider(), "model-a", "text")

    # malformed_response: invalid JSON body, missing content, non-string content
    for body in (_NOT_JSON, {"choices": []}, {"choices": [{"message": {}}]}):
        _recorded_post(monkeypatch, lambda call, body=body: _fake_response(body))
        with pytest.raises(ProviderError):
            summarize_mod.summarize_with_provider(_provider(), "model-a", "text")


def test_empty_content_rejected_as_provider_error(tmp_path, monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-039"""
    # The *real* _call_chat_completions runs against a mocked HTTP layer (the
    # api fixture's dispatch stub would bypass the rejection under test).
    config_file = tmp_path / "providers.json"
    config_file.write_text(json.dumps(PROVIDER_CONFIG), encoding="utf-8")
    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir()
    monkeypatch.setenv("PROVIDERS_CONFIG", str(config_file))
    monkeypatch.setenv("TRANSCRIPT_DIR", str(transcript_dir))
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    client = TestClient(create_app())
    with client:
        # empty and whitespace-only content are both rejected
        for content in ("", " \t\n "):
            _recorded_post(
                monkeypatch,
                lambda call, content=content: _fake_response(
                    {"choices": [{"message": {"content": content}}]}
                ),
            )
            response = client.post("/api/summarize", json=_valid_body())
            assert response.status_code == 502
            assert response.json()["error"]["code"] == "PROVIDER_ERROR"

    # no .summary file was written
    assert list(transcript_dir.iterdir()) == []

    # and the summary_failed event carries the machine-readable reason
    failed = _entries(buf, "summary_failed")
    assert [e["reason"] for e in failed] == ["empty_response"] * 2


# --- summary file persistence --------------------------------------------------

def test_summary_written_alongside_transcript(tmp_path, monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-018"""
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))
    (tmp_path / "the_end_of_llms_ncm.txt").write_text("transcript\n", encoding="utf-8")

    summarize_mod.save_summary("the_end_of_llms_ncm.txt", "A summary of the end.")

    summary_file = tmp_path / "the_end_of_llms_ncm.txt.summary"
    assert summary_file.exists()
    assert summary_file.read_text(encoding="utf-8") == "A summary of the end."


def test_resummarize_overwrites_summary_file(tmp_path, monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-019"""
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))

    summarize_mod.save_summary("video.txt", "First summary.")
    summarize_mod.save_summary("video.txt", "Second summary.")

    assert (tmp_path / "video.txt.summary").read_text(encoding="utf-8") == "Second summary."


def test_unwritable_directory_still_returns_summary(api, monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-020"""
    # Point the transcript directory at a path under an existing file so the
    # write deterministically fails (the directory cannot exist).
    blocker = api["transcript_dir"].parent / "blocker"
    blocker.write_text("I am a file, not a directory", encoding="utf-8")
    monkeypatch.setenv("TRANSCRIPT_DIR", str(blocker / "sub"))

    response = api["client"].post(
        "/api/summarize",
        json=_valid_body(name="the_end_of_llms_ncm.txt"),
    )

    # the response is still 200 with the generated summary...
    assert response.status_code == 200
    assert response.json() == {"summary": "The summary."}
    # ...no file was written, and the failure is reported only through the
    # log (T-STRUCTURED-LOGGING-018 covers the event itself)
    assert not (blocker / "sub").exists()


def _entries(buf, event=None) -> list[dict]:
    lines = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    return lines if event is None else [e for e in lines if e.get("event") == event]


def test_summary_completed_logged(monkeypatch):
    """T-STRUCTURED-LOGGING-015"""
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    _recorded_post(
        monkeypatch,
        lambda call: _fake_response(
            {"choices": [{"message": {"content": "The summary."}}]}
        ),
    )

    summarize_mod.summarize_with_provider(_provider(), "model-a", "abcdef")

    entries = _entries(buf, "summary_completed")
    assert len(entries) == 1
    event = entries[0]
    assert event["level"] == "info"
    assert event["provider"] == "radai"
    assert event["model"] == "model-a"
    assert isinstance(event["duration_ms"], (int, float))
    assert event["chars_in"] == len("abcdef")
    assert event["chars_out"] == len("The summary.")


def test_summary_failed_logged(monkeypatch):
    """T-STRUCTURED-LOGGING-016"""
    import requests

    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    monkeypatch.setattr(
        summarize_mod.requests, "post",
        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError()),
    )

    with pytest.raises(ProviderError):
        summarize_mod.summarize_with_provider(_provider(), "model-a", "text")

    entries = _entries(buf, "summary_failed")
    assert len(entries) == 1
    event = entries[0]
    assert event["level"] == "error"
    assert event["provider"] == "radai"
    assert event["model"] == "model-a"
    assert event["reason"] == "unreachable"
    assert event["detail"] == "ConnectionError"
    assert isinstance(event["duration_ms"], (int, float))


def test_summary_logs_omit_content_and_keys(monkeypatch):
    """T-STRUCTURED-LOGGING-017"""
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    transcript = "TRANSCRIPT_MARKER_XYZ unique transcript body"
    summary = "SUMMARY_MARKER_QRS unique summary body"

    # a successful summarization with a keyed provider...
    _recorded_post(
        monkeypatch,
        lambda call: _fake_response({"choices": [{"message": {"content": summary}}]}),
    )
    summarize_mod.summarize_with_provider(_provider(api_key="sk-KEY_MARKER_42"), "model-a", transcript)

    # ...and a failed one
    import requests
    monkeypatch.setattr(
        summarize_mod.requests, "post",
        lambda *a, **kw: (_ for _ in ()).throw(requests.Timeout()),
    )
    with pytest.raises(ProviderError):
        summarize_mod.summarize_with_provider(_provider(api_key="sk-KEY_MARKER_42"), "model-a", transcript)

    out = buf.getvalue()
    assert "TRANSCRIPT_MARKER_XYZ" not in out
    assert "unique transcript body" not in out
    assert "SUMMARY_MARKER_QRS" not in out
    assert "unique summary body" not in out
    assert "sk-KEY_MARKER_42" not in out


def test_summary_save_failure_logged(tmp_path, monkeypatch):
    """T-STRUCTURED-LOGGING-018"""
    blocker = tmp_path / "blocker"
    blocker.write_text("I am a file, not a directory", encoding="utf-8")
    monkeypatch.setenv("TRANSCRIPT_DIR", str(blocker / "sub"))
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    # the summary itself is still produced (the save is best-effort)
    summarize_mod.save_summary("the_end_of_llms_ncm.txt", "A summary.")

    entries = _entries(buf, "summary_save_failed")
    assert len(entries) == 1
    event = entries[0]
    assert event["level"] == "error"
    assert event["name"] == "the_end_of_llms_ncm.txt"
    assert event["path"] == str(blocker / "sub" / "the_end_of_llms_ncm.txt.summary")
    assert event["reason"]
    assert event["detail"]


def test_read_summary_contained_read(tmp_path, monkeypatch):
    """The contained read (endpoint level is covered in task 3.3)."""
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))
    (tmp_path / "video.txt.summary").write_text("saved summary", encoding="utf-8")

    assert summarize_mod.read_summary("video.txt") == (True, "saved summary")
    # absent summary -> not ok
    assert summarize_mod.read_summary("other.txt") == (False, "")
    # structurally invalid name -> not ok, before any filesystem access
    assert summarize_mod.read_summary("..\\evil") == (False, "")
    assert summarize_mod.read_summary("../evil") == (False, "")


# --- API endpoints (TestClient; dispatch stubbed, files on tmp_path) ----------


class RecordingDispatch:
    """Recording stand-in for summarize_mod._call_chat_completions."""

    def __init__(self):
        self.calls = []
        self.summary = "The summary."
        self.failure = None  # None | (reason, detail)

    def reset(self):
        self.calls = []
        self.failure = None

    def set_failure(self, reason, detail):
        self.failure = (reason, detail)

    def __call__(self, base_url, model, messages, api_key, timeout):
        self.calls.append({
            "base_url": base_url, "model": model, "messages": messages,
            "api_key": api_key, "timeout": timeout,
        })
        if self.failure is not None:
            raise summarize_mod.ProviderCallError(*self.failure)
        return self.summary


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
    """TestClient with a tmp provider config, a tmp transcript dir, and the
    chat-completions dispatch replaced by a recording stub."""
    config_file = tmp_path / "providers.json"
    config_file.write_text(json.dumps(PROVIDER_CONFIG), encoding="utf-8")
    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir()
    monkeypatch.setenv("PROVIDERS_CONFIG", str(config_file))
    monkeypatch.setenv("TRANSCRIPT_DIR", str(transcript_dir))
    dispatch = RecordingDispatch()
    monkeypatch.setattr(summarize_mod, "_call_chat_completions", dispatch)
    client = TestClient(create_app())
    with client:
        yield {
            "client": client,
            "config_file": config_file,
            "transcript_dir": transcript_dir,
            "dispatch": dispatch,
        }


def _valid_body(name="video.txt", text="The transcript text.",
                provider="alpha", model="model-a1"):
    return {"text": text, "name": name, "provider": provider, "model": model}


# --- T-TRANSCRIPT-SUMMARIZATION-006 .. 008: GET /api/providers -----------------


def test_providers_endpoint_omits_secrets(api):
    """T-TRANSCRIPT-SUMMARIZATION-006"""
    response = api["client"].get("/api/providers")

    assert response.status_code == 200
    body = response.json()
    alpha = next(p for p in body["providers"] if p["id"] == "alpha")
    assert set(alpha.keys()) == {"id", "name", "models"}
    assert alpha["name"] == "Alpha Local"
    assert alpha["models"] == ["model-a1", "model-a2"]
    # neither the API key nor the base URL appears anywhere in the body
    assert "sk-endpoint-test-key" not in response.text
    assert "41411" not in response.text and "41412" not in response.text


def test_providers_endpoint_default_selection(api):
    """T-TRANSCRIPT-SUMMARIZATION-007"""
    # an explicit default key wins
    assert api["client"].get("/api/providers").json()["default"] == "alpha"

    # without it, the first provider in file order is the default
    config = json.loads(api["config_file"].read_text(encoding="utf-8"))
    del config["default"]
    api["config_file"].write_text(json.dumps(config), encoding="utf-8")
    assert api["client"].get("/api/providers").json()["default"] == "alpha"

    # an explicit default naming another provider wins for that provider
    config["default"] = "beta"
    api["config_file"].write_text(json.dumps(config), encoding="utf-8")
    assert api["client"].get("/api/providers").json()["default"] == "beta"


def test_providers_endpoint_not_configured_empty(api):
    """T-TRANSCRIPT-SUMMARIZATION-008"""
    api["config_file"].unlink()  # no usable provider configuration exists

    response = api["client"].get("/api/providers")

    assert response.status_code == 200
    assert response.json() == {"default": None, "providers": []}


# --- T-TRANSCRIPT-SUMMARIZATION-009, 012 .. 017: POST /api/summarize ----------


def test_summarize_success_returns_summary(api):
    """T-TRANSCRIPT-SUMMARIZATION-009"""
    response = api["client"].post("/api/summarize", json=_valid_body())

    assert response.status_code == 200
    assert response.json() == {"summary": "The summary."}
    assert len(api["dispatch"].calls) == 1


def test_unknown_provider_or_model_rejected(api):
    """T-TRANSCRIPT-SUMMARIZATION-012"""
    # a provider id that is not in the current configuration...
    response = api["client"].post(
        "/api/summarize", json=_valid_body(provider="ghost")
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PROVIDER"

    # ...and a model id not listed for a known provider
    response = api["client"].post(
        "/api/summarize", json=_valid_body(model="model-zz")
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PROVIDER"

    # no backend request was made
    assert api["dispatch"].calls == []


def test_invalid_name_rejected(api):
    """T-TRANSCRIPT-SUMMARIZATION-013"""
    for bad_name in ("../evil.txt", "..\\evil.txt", "a/b.txt", ""):
        response = api["client"].post(
            "/api/summarize", json=_valid_body(name=bad_name)
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_NAME"

    # no file was read or written, no backend request was made
    assert list(api["transcript_dir"].iterdir()) == []
    assert api["dispatch"].calls == []


def test_overlong_text_rejected(api):
    """T-TRANSCRIPT-SUMMARIZATION-014"""
    # over the cap: rejected without a backend call...
    response = api["client"].post(
        "/api/summarize", json=_valid_body(text="x" * (summarize_mod.MAX_INPUT_CHARS + 1))
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INPUT_TOO_LONG"
    assert api["dispatch"].calls == []

    # exactly at the cap: not rejected
    response = api["client"].post(
        "/api/summarize", json=_valid_body(text="x" * summarize_mod.MAX_INPUT_CHARS)
    )
    assert response.status_code == 200
    assert len(api["dispatch"].calls) == 1


def test_not_configured_returns_503(api):
    """T-TRANSCRIPT-SUMMARIZATION-015"""
    api["config_file"].unlink()  # no usable provider configuration exists

    response = api["client"].post("/api/summarize", json=_valid_body())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "NOT_CONFIGURED"
    assert api["dispatch"].calls == []


def test_backend_failure_returns_502(api):
    """T-TRANSCRIPT-SUMMARIZATION-016"""
    api["dispatch"].set_failure("unreachable", "ConnectionError")

    response = api["client"].post("/api/summarize", json=_valid_body())

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "PROVIDER_ERROR"
    # a message suggesting a retry
    assert "try again" in error["message"].lower()


def test_summarize_during_in_flight_fetch_succeeds(api, monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-017"""
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
        response = api["client"].post("/api/summarize", json=_valid_body())
        assert response.status_code == 200
        assert response.json() == {"summary": "The summary."}
        # the summarize did not invoke the fetch chain
        assert fetch_calls == ["dQw4w9WgXcQ"]
    finally:
        release_fetch.set()
        thread.join(timeout=15)


# --- T-TRANSCRIPT-SUMMARIZATION-021, 022 .. 024, 037: summary read endpoint ---


def test_summary_files_excluded_from_list(api):
    """T-TRANSCRIPT-SUMMARIZATION-021"""
    (api["transcript_dir"] / "video.txt").write_text("transcript\n", encoding="utf-8")
    (api["transcript_dir"] / "video.txt.summary").write_text("a summary\n", encoding="utf-8")

    response = api["client"].get("/api/transcripts")

    assert response.status_code == 200
    assert [t["name"] for t in response.json()["transcripts"]] == ["video.txt"]


def test_summary_read_returns_content(api):
    """T-TRANSCRIPT-SUMMARIZATION-022"""
    (api["transcript_dir"] / "the_end_of_llms_ncm.txt").write_text(
        "transcript\n", encoding="utf-8"
    )
    (api["transcript_dir"] / "the_end_of_llms_ncm.txt.summary").write_text(
        "The saved summary.", encoding="utf-8"
    )

    response = api["client"].get("/api/transcripts/the_end_of_llms_ncm.txt/summary")

    assert response.status_code == 200
    assert response.json() == {
        "name": "the_end_of_llms_ncm.txt",
        "summary": "The saved summary.",
    }


def test_summary_read_absent_returns_404(api):
    """T-TRANSCRIPT-SUMMARIZATION-023"""
    (api["transcript_dir"] / "the_end_of_llms_ncm.txt").write_text(
        "transcript\n", encoding="utf-8"
    )

    response = api["client"].get("/api/transcripts/the_end_of_llms_ncm.txt/summary")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_summary_read_traversal_rejected(api, tmp_path):
    """T-TRANSCRIPT-SUMMARIZATION-024"""
    # A file that a successful traversal would read, outside the transcript
    # directory; its content must never reach the response.
    outside = tmp_path / "evil.txt.summary"
    outside.write_text("OUTSIDE_SUMMARY_MARKER", encoding="utf-8")

    # backslash path component (routed as a single path segment)
    response = api["client"].get("/api/transcripts/..%5Cevil.txt/summary")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_NAME"
    assert "OUTSIDE_SUMMARY_MARKER" not in response.text


def test_summary_read_has_no_side_effects(api, monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-037"""
    import threading

    # A fetch in flight holding the single-flight semaphore...
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

    before = sorted(p.name for p in api["transcript_dir"].iterdir())
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
        response = api["client"].get("/api/transcripts/gone_video.txt/summary")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
        # no file or directory was created...
        after = sorted(p.name for p in api["transcript_dir"].iterdir())
        assert before == after
        assert not (api["transcript_dir"] / "gone_video.txt.summary").exists()
        # ...and the request did not invoke the fetch chain
        assert fetch_calls == ["dQw4w9WgXcQ"]
    finally:
        release_fetch.set()
        thread.join(timeout=15)
