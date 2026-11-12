"""Model discovery: live read of a provider's OpenAI-compatible ``/models``.

Kept free of FastAPI imports (mirroring ``app/summarize.py``): the call is a
plain synchronous function meant to be run in a worker thread, and is
testable directly against ``tmp_path``/monkeypatched ``requests``.

The HTTP dispatch lives in the module-level :func:`_get_provider_models`
(design D6): tests replace that function with a recording stub while
:func:`list_models` keeps running for real, so its
``provider_models_refreshed`` / ``provider_models_refresh_failed`` log
emission still happens while the backend response is controlled
deterministically.
"""

from __future__ import annotations

import os
import time

import requests

from app.errors import ProviderError
from app.log import get_logger
from app.providers import Provider

# Backend-call timeout in seconds (connect + read), sized for a local
# /models endpoint (design D6); overridable via MODEL_DISCOVERY_TIMEOUT,
# non-numeric values fall back to the default (same style as SUMMARY_TIMEOUT).
DEFAULT_DISCOVERY_TIMEOUT = 15.0

# Cap on the number of discovered ids returned (design D6): a misbehaving
# backend must not be able to flood the picker.
MAX_DISCOVERED_MODELS = 200


class ModelDiscoveryError(Exception):
    """A failed models-endpoint call, with a machine-readable reason.

    ``reason`` is one of ``unreachable``, ``timeout``, ``http_error``,
    ``malformed_response`` (the same taxonomy as the summarization call);
    ``detail`` is a safe, app-constructed message (no base URLs, keys, or
    response contents).
    """

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def discovery_timeout() -> float:
    """Resolve the discovery-call timeout at call time (design D6)."""
    raw = os.environ.get("MODEL_DISCOVERY_TIMEOUT")
    try:
        return float(raw) if raw is not None else DEFAULT_DISCOVERY_TIMEOUT
    except ValueError:
        return DEFAULT_DISCOVERY_TIMEOUT


def _get_provider_models(
    base_url: str, api_key: str | None, timeout: float
) -> dict:
    """GET ``{baseURL}/models`` and return the parsed JSON body.

    Per-call ``requests.get`` (no shared session: thread-safe without
    locking). The bearer token is attached only when the provider defines
    an ``apiKey``. Raises :class:`ModelDiscoveryError` with a
    machine-readable reason on every failure.
    """
    url = base_url.rstrip("/") + "/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
    except requests.Timeout as exc:
        raise ModelDiscoveryError(
            "timeout",
            f"models endpoint did not respond within {timeout:.0f}s",
        ) from exc
    except requests.RequestException as exc:
        # Type name only: str() of requests exceptions embeds the base URL,
        # which must stay out of the logs (design D6).
        raise ModelDiscoveryError("unreachable", type(exc).__name__) from exc
    if response.status_code // 100 != 2:
        raise ModelDiscoveryError(
            "http_error", f"models endpoint returned HTTP {response.status_code}"
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise ModelDiscoveryError(
            "malformed_response", "models response is not valid JSON"
        ) from exc
    if not isinstance(data, dict):
        raise ModelDiscoveryError(
            "malformed_response", "models response is not a JSON object"
        )
    return data


def _parse_model_ids(data: dict) -> list[str] | None:
    """Extract the model ids from a ``/models`` body (design D6).

    Returns a list of id strings — only dict entries of the ``data`` array
    with a non-empty string ``id`` are kept, duplicates removed preserving
    first occurrence, capped at :data:`MAX_DISCOVERED_MODELS` — or ``None``
    when the body is not the expected shape (``data`` missing or not a
    list), which the caller treats as ``malformed_response``.
    """
    entries = data.get("data")
    if not isinstance(entries, list):
        return None
    ids: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id")
        if isinstance(model_id, str) and model_id and model_id not in seen:
            seen.add(model_id)
            ids.append(model_id)
        if len(ids) >= MAX_DISCOVERED_MODELS:
            break
    return ids


def list_models(provider: Provider, timeout: float | None = None) -> list[str]:
    """Fetch the provider's model ids and return them as a list of strings.

    Emits exactly one structured event per call:
    ``provider_models_refreshed`` (info: ``provider``, ``count``,
    ``duration_ms``) or ``provider_models_refresh_failed`` (error:
    ``provider``, ``reason``, ``detail``, ``duration_ms``) — never a base
    URL, an API key, or response contents (design D6). Raises
    :class:`ProviderError` (HTTP 502 ``PROVIDER_ERROR``) when the models
    endpoint fails in any way.
    """
    logger = get_logger()
    start = time.monotonic()

    def _fail(reason: str, detail: str) -> ProviderError:
        logger.error(
            "provider_models_refresh_failed",
            provider=provider.id,
            reason=reason,
            detail=detail,
            duration_ms=round((time.monotonic() - start) * 1000.0, 2),
        )
        return ProviderError(
            f"Model discovery failed ({reason}). Please try again."
        )

    try:
        data = _get_provider_models(
            provider.base_url, provider.api_key,
            discovery_timeout() if timeout is None else timeout,
        )
    except ModelDiscoveryError as exc:
        raise _fail(exc.reason, exc.detail) from exc
    ids = _parse_model_ids(data)
    if ids is None:
        raise _fail(
            "malformed_response", "models response missing a \"data\" list"
        )
    logger.info(
        "provider_models_refreshed",
        provider=provider.id,
        count=len(ids),
        duration_ms=round((time.monotonic() - start) * 1000.0, 2),
    )
    return ids
