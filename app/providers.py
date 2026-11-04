"""Summarization provider configuration: per-request config-file reading.

Kept free of FastAPI imports (design.md, decision 2): the reader is pure over
the config file path so it is testable directly against ``tmp_path``.

The config is read on every call, never at startup (design decision 3):
edits take effect on the next request, and a missing or malformed file means
"not configured" (an empty result), never an exception.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from app.log import get_logger

# Default config path: providers.json in the working directory; overridable
# via PROVIDERS_CONFIG (app-read env vars use the singular spelling; compose
# maps them host-side, as with TRANSCRIPT_DIR).
_DEFAULT_CONFIG = "providers.json"


@dataclass(frozen=True)
class Provider:
    """One usable provider entry from the config file."""

    id: str
    name: str  # display name (falls back to the id)
    base_url: str
    api_key: str | None
    models: tuple[str, ...]  # model ids in file order


@dataclass(frozen=True)
class ProviderConfig:
    """The result of one config read: usable providers plus the default id."""

    providers: tuple[Provider, ...]
    default: str | None


def config_path() -> Path:
    """Resolve the config file path at call time (design decision 3)."""
    return Path(os.environ.get("PROVIDERS_CONFIG", _DEFAULT_CONFIG))


def _parse_provider(provider_id: str, value: object) -> Provider | None:
    """Validate one provider entry; ``None`` when it is not usable.

    A provider is usable when it carries a non-empty string
    ``options.baseURL`` and a non-empty ``models`` map (its keys are the
    model ids, in file order). Unknown fields are ignored, and a missing or
    empty display name falls back to the provider id.
    """
    if not isinstance(value, dict):
        return None
    options = value.get("options")
    if not isinstance(options, dict):
        return None
    base_url = options.get("baseURL")
    if not isinstance(base_url, str) or not base_url:
        return None
    api_key = options.get("apiKey")
    if not isinstance(api_key, str):
        api_key = None
    models = value.get("models")
    if not isinstance(models, dict) or not models:
        return None
    name = value.get("name")
    if not isinstance(name, str) or not name:
        name = provider_id
    return Provider(
        id=provider_id,
        name=name,
        base_url=base_url,
        api_key=api_key,
        models=tuple(models.keys()),
    )


def _log_config_failed(path: str, reason: str, detail: str) -> None:
    # The parse error only — never the file's contents (design decision 13).
    get_logger().error(
        "config_load_failed", path=path, reason=reason, detail=detail
    )


def load_providers() -> ProviderConfig:
    """Read, parse, and validate the provider config file (per call).

    A missing file is the normal "not configured" state (no log); an
    unreadable file, malformed JSON, a malformed structure, or a file with no
    usable provider all return the empty result without raising, and a
    malformed config additionally logs one ``config_load_failed`` error event
    carrying the path and the parse error detail.
    """
    path = config_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ProviderConfig((), None)
    except OSError as exc:
        _log_config_failed(str(path), type(exc).__name__, str(exc))
        return ProviderConfig((), None)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        _log_config_failed(str(path), "invalid_json", str(exc))
        return ProviderConfig((), None)
    if not isinstance(data, dict):
        _log_config_failed(str(path), "invalid_structure",
                           "top-level JSON value is not an object")
        return ProviderConfig((), None)
    provider_map = data.get("provider")
    if provider_map is not None and not isinstance(provider_map, dict):
        _log_config_failed(str(path), "invalid_structure",
                           "the \"provider\" entry is not an object")
        return ProviderConfig((), None)
    providers = tuple(
        parsed
        for parsed in (
            _parse_provider(provider_id, value)
            for provider_id, value in (provider_map or {}).items()
        )
        if parsed is not None
    )
    default = data.get("default")
    if not isinstance(default, str) or default not in {p.id for p in providers}:
        default = providers[0].id if providers else None
    return ProviderConfig(providers, default)
