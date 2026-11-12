"""T-SUMMARIZATION-MODEL-MANAGEMENT-001 .. 007.

The provider-overrides store (app/provider_overrides.py), unit-tested
against tmp_path: no FastAPI, no network. The merge is verified the way the
endpoints compose it: apply_overrides(load_providers(), load_overrides()).
"""

import io
import json

import pytest

from app import log as applog
from app import provider_overrides as overrides_mod
from app.library import list_transcripts
from app.providers import load_providers


def _write_config(path, payload) -> str:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


RADAI_CONFIG = {
    "provider": {
        "radai": {
            "name": "Radai Local",
            "options": {"baseURL": "http://localhost:8181/v1"},
            "models": {"model-a": "Model A", "model-b": "Model B"},
        }
    }
}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A tmp provider config plus a tmp (empty) transcript directory."""
    config_file = tmp_path / "providers.json"
    monkeypatch.setenv("PROVIDERS_CONFIG", _write_config(config_file, RADAI_CONFIG))
    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir()
    monkeypatch.setenv("TRANSCRIPT_DIR", str(transcript_dir))
    return {"transcript_dir": transcript_dir}


def _effective():
    """The merge exactly as the endpoints compose it."""
    return overrides_mod.apply_overrides(load_providers(),
                                         overrides_mod.load_overrides())


def test_overrides_merge_after_file_models(env):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-001"""
    (env["transcript_dir"] / "provider_overrides.json").write_text(
        json.dumps({"radai": ["model-c"]}), encoding="utf-8"
    )

    config = _effective()

    radai = config.providers[0]
    assert radai.models == ("model-a", "model-b", "model-c")
    assert radai.added_models == ("model-c",)


def test_override_duplicates_not_repeated(env):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-002"""
    (env["transcript_dir"] / "provider_overrides.json").write_text(
        json.dumps({"radai": ["model-b", "model-c", "model-c"]}), encoding="utf-8"
    )

    radai = _effective().providers[0]

    assert radai.models == ("model-a", "model-b", "model-c")
    # the file-provided duplicate is not repeated nor provenance-marked
    assert radai.added_models == ("model-c",)


def test_overlay_cannot_add_provider(env):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-003"""
    (env["transcript_dir"] / "provider_overrides.json").write_text(
        json.dumps({"radai": ["model-c"], "ghost": ["model-x"]}),
        encoding="utf-8",
    )

    config = _effective()

    assert [p.id for p in config.providers] == ["radai"]
    assert config.providers[0].models == ("model-a", "model-b", "model-c")


def test_missing_overrides_means_file_only(env):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-004"""
    buf = io.StringIO()
    applog.setup_logging(stream=buf)

    config = _effective()

    radai = config.providers[0]
    assert radai.models == ("model-a", "model-b")
    assert radai.added_models == ()
    # the missing file is the normal state: no failure is logged
    assert not [
        e for e in (json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip())
        if e.get("event") == "provider_overrides_load_failed"
    ]


def test_malformed_overrides_degrades(env):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-005"""
    overrides_file = env["transcript_dir"] / "provider_overrides.json"
    marker = "SECRET_OVERRIDE_CONTENT_MARKER_77"

    # invalid JSON ...
    overrides_file.write_text(f'{{"radai": [{marker}]', encoding="utf-8")
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    config = _effective()
    assert config.providers[0].models == ("model-a", "model-b")
    entries = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    failed = [e for e in entries if e.get("event") == "provider_overrides_load_failed"]
    assert len(failed) == 1
    event = failed[0]
    assert event["level"] == "error"
    assert event["path"] == str(overrides_file)
    assert event["reason"]
    assert event["detail"]
    # the parse error detail is present, but never the file's contents
    assert marker not in buf.getvalue()

    # ...and a non-object top level
    overrides_file.write_text("[]", encoding="utf-8")
    buf = io.StringIO()
    applog.setup_logging(stream=buf)
    config = _effective()
    assert config.providers[0].models == ("model-a", "model-b")
    entries = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    failed = [e for e in entries if e.get("event") == "provider_overrides_load_failed"]
    assert len(failed) == 1
    assert failed[0]["reason"] == "invalid_structure"


def test_overrides_edit_takes_effect_without_restart(env):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-006"""
    # the app has already served a provider list read ...
    assert _effective().providers[0].models == ("model-a", "model-b")

    # ...and the overlay file appears after that read; the next read must
    # include the added model with no restart.
    (env["transcript_dir"] / "provider_overrides.json").write_text(
        json.dumps({"radai": ["model-c"]}), encoding="utf-8"
    )
    assert _effective().providers[0].models == ("model-a", "model-b", "model-c")

    # and an edit on disk is picked up the same way
    (env["transcript_dir"] / "provider_overrides.json").write_text(
        json.dumps({"radai": ["model-c", "model-d"]}), encoding="utf-8"
    )
    assert _effective().providers[0].models == ("model-a", "model-b", "model-c", "model-d")


def test_overrides_file_excluded_from_list(env):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-007"""
    transcript_dir = env["transcript_dir"]
    (transcript_dir / "provider_overrides.json").write_text(
        json.dumps({"radai": ["model-c"]}), encoding="utf-8"
    )
    (transcript_dir / "video.txt").write_text("transcript\n", encoding="utf-8")

    names = [t["name"] for t in list_transcripts()]

    assert "provider_overrides.json" not in names
    assert names == ["video.txt"]
