"""Provider overrides: per-request read and atomic write of
provider_overrides.json, plus the effective-config merge.

Kept free of FastAPI imports (mirroring ``app/providers.py`` and
``app/settings.py``): the reader, the merge, and the writer are pure over
``persist.transcript_dir()`` so they are testable directly against
``tmp_path``.

The file is read on every call, never at startup (design D1/D3): edits on
disk take effect on the next request. A missing file is the normal "no
additions" state (no log); an unreadable or malformed file degrades to no
additions without raising and logs ``provider_overrides_load_failed``.
Writes go to a sibling temp file followed by ``os.replace`` so a crash
mid-write can never leave a truncated file behind.

The overlay only extends the model list of providers defined in the config
file (design D2): it never introduces a provider, a base URL, or an API key,
and entries for unknown provider ids are ignored.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import replace
from pathlib import Path

from app.errors import InvalidModelError, ModelNotRemovableError
from app.log import get_logger
from app.persist import transcript_dir
from app.providers import Provider, ProviderConfig

# Overrides file name inside the transcript directory (design D1): the volume
# is already host-mounted and writable, and the name is invisible to the
# .txt-only transcript listing.
_OVERRIDES_FILE = "provider_overrides.json"

# Model id bounds (design D5): a trimmed id must be 1..200 characters and
# free of control characters; each provider holds at most 50 overlay
# additions.
MAX_MODEL_ID_CHARS = 200
MAX_ADDED_PER_PROVIDER = 50

# C0 controls, DEL, and C1 (design D5).
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")

# Read-modify-write guard (design D3): the app runs a single uvicorn process,
# so a process-local lock is sufficient; a multi-process deployment would
# need an OS file lock (documented non-goal).
_lock = threading.Lock()


class ModelNotFoundError(Exception):
    """The model id is in neither the overlay nor the provider's file models.

    The remove endpoint maps it to 404 ``NOT_FOUND`` — a plain HTTP status,
    deliberately outside the taxonomy (as with ``INVALID_NAME``).
    """


def overrides_path() -> Path:
    """Resolve the overrides file path at call time (design D1)."""
    return transcript_dir() / _OVERRIDES_FILE


def _log_load_failed(path: str, reason: str, detail: str) -> None:
    # The parse/OS error only — never the file's contents (design D3).
    get_logger().error(
        "provider_overrides_load_failed", path=path, reason=reason, detail=detail
    )


def _log_save_failed(path: str, reason: str, detail: str) -> None:
    get_logger().error(
        "provider_overrides_save_failed", path=path, reason=reason, detail=detail
    )


def load_overrides() -> dict[str, list[str]]:
    """Read the overlay file (per call); returns ``{provider_id: [model, ...]}``.

    A missing file is the normal "no additions" state (no log). An unreadable
    file, malformed JSON, or a non-object top level returns ``{}`` without
    raising and logs one ``provider_overrides_load_failed`` error event
    carrying the path and the parse/OS detail — never the file's contents.
    Non-string entries inside a model list are dropped; a provider whose list
    holds no usable id is dropped.
    """
    path = overrides_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        _log_load_failed(str(path), type(exc).__name__, str(exc))
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        _log_load_failed(str(path), "invalid_json", str(exc))
        return {}
    if not isinstance(data, dict):
        _log_load_failed(str(path), "invalid_structure",
                         "top-level JSON value is not an object")
        return {}
    result: dict[str, list[str]] = {}
    for provider_id, models in data.items():
        if not isinstance(models, list):
            continue
        ids = [m for m in models if isinstance(m, str) and m]
        if ids:
            result[str(provider_id)] = ids
    return result


def _merge_provider(provider: Provider, overlay_ids: list[str]) -> Provider:
    """One provider's effective model list: file models in order, then the
    overlay ids not already present (first occurrence kept). The overlay ids
    actually used are carried on ``added_models`` (design D2)."""
    effective = list(provider.models)
    added: list[str] = []
    for model in overlay_ids:
        if model not in effective:
            effective.append(model)
            added.append(model)
    return replace(
        provider, models=tuple(effective), added_models=tuple(added)
    )


def apply_overrides(
    config: ProviderConfig, overrides: dict[str, list[str]]
) -> ProviderConfig:
    """Merge overlay ids into a file config (pure — no I/O).

    The provider set comes **only** from ``config.providers``: overlay keys
    for unknown provider ids are ignored (and left on disk). Each provider's
    effective models are its file models in order, then its overlay ids not
    already present; the overlay ids actually used are carried on
    ``added_models`` in the same order they appear in ``models`` (design D2).
    """
    merged = tuple(
        _merge_provider(provider, overrides.get(provider.id, []))
        for provider in config.providers
    )
    return ProviderConfig(merged, config.default)


def _write_overrides(overrides: dict[str, list[str]]) -> bool:
    """Atomically persist the overlay map; return whether the write
    succeeded.

    Never raises: on any failure it logs ``provider_overrides_save_failed``
    (path + OS error detail) and returns ``False``, removing a stranded temp
    file best-effort.
    """
    path = overrides_path()
    tmp_path = path.with_name(path.name + ".tmp")
    payload = json.dumps(overrides, indent=2)
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_path, path)
    except Exception as exc:
        # Best-effort cleanup of a stranded temp file; the replace itself
        # never leaves one behind.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        _log_save_failed(str(path), type(exc).__name__, str(exc))
        return False
    return True


def is_valid_model_id(model_id: str) -> bool:
    """Whether ``model_id`` is a usable model id (design D5).

    Valid when it is a string that is non-empty after trimming, at most
    ``MAX_MODEL_ID_CHARS`` characters, and free of control characters.
    """
    if not isinstance(model_id, str):
        return False
    trimmed = model_id.strip()
    if not trimmed or len(trimmed) > MAX_MODEL_ID_CHARS:
        return False
    return _CONTROL_CHARS.search(trimmed) is None


def _effective_models(provider: Provider, overlay_ids: list[str]) -> list[str]:
    effective = list(provider.models)
    for model in overlay_ids:
        if model not in effective:
            effective.append(model)
    return effective


def add_model(provider: Provider, model_id: str) -> list[str] | None:
    """Atomically add a validated model id to the overlay for ``provider``.

    ``model_id`` must already be trimmed and pass
    :func:`is_valid_model_id`. Runs the read-modify-write under the module
    lock (design D3). An id already in the effective list is an idempotent
    success — file-provided ids are left alone and no write or log event
    happens. A successful new addition emits ``provider_model_added`` (info:
    ``provider``, ``model``). Returns the effective model list (file models,
    then overlay ids) on success, or ``None`` when the overlay write failed
    (already logged as ``provider_overrides_save_failed``). Raises
    :class:`InvalidModelError` when the per-provider addition cap would be
    exceeded.
    """
    with _lock:
        overrides = load_overrides()
        ids = list(overrides.get(provider.id, []))
        if model_id not in provider.models and model_id not in ids:
            if len(ids) >= MAX_ADDED_PER_PROVIDER:
                raise InvalidModelError(
                    "That provider already has the maximum of "
                    f"{MAX_ADDED_PER_PROVIDER} added models — remove one "
                    "before adding another."
                )
            ids.append(model_id)
            overrides[provider.id] = ids
            if not _write_overrides(overrides):
                return None
            get_logger().info(
                "provider_model_added", provider=provider.id, model=model_id
            )
    return _effective_models(provider, overrides.get(provider.id, []))


def remove_model(provider: Provider, model_id: str) -> list[str] | None:
    """Atomically remove a model id from the overlay for ``provider``.

    ``model_id`` must already be trimmed. A config-file model is never
    removable: raises :class:`ModelNotRemovableError` (400). An id in neither
    the overlay nor the file models raises :class:`ModelNotFoundError` (the
    endpoint maps it to 404 ``NOT_FOUND``). A successful removal emits
    ``provider_model_removed`` (info: ``provider``, ``model``). Returns the
    remaining effective model list on success, or ``None`` when the overlay
    write failed (already logged).
    """
    if model_id in provider.models:
        raise ModelNotRemovableError()
    with _lock:
        overrides = load_overrides()
        ids = list(overrides.get(provider.id, []))
        if model_id not in ids:
            raise ModelNotFoundError(model_id)
        ids.remove(model_id)
        if ids:
            overrides[provider.id] = ids
        else:
            overrides.pop(provider.id, None)
        if not _write_overrides(overrides):
            return None
        get_logger().info(
            "provider_model_removed", provider=provider.id, model=model_id
        )
    return _effective_models(provider, overrides.get(provider.id, []))
