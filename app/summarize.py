"""Summarization backend: OpenAI-compatible chat-completions call and
summary-file persistence.

Kept free of FastAPI imports (design.md, decision 2): the call is a plain
synchronous function meant to be run in a worker thread via
``asyncio.to_thread``, and the save/read helpers are testable directly
against ``tmp_path``.

The HTTP dispatch lives in the module-level :func:`_call_chat_completions`
(design decision 11): the e2e harness replaces that function with a recording
stub while :func:`summarize_with_provider` keeps running for real, so its
``summary_completed`` / ``summary_failed`` log emission still happens in e2e.
"""

from __future__ import annotations

import os
import time

import requests

from app.errors import ProviderError
from app.library import is_structurally_invalid_name
from app.log import get_logger
from app.persist import transcript_dir
from app.providers import Provider

# Output cap (design decision 10); the model is bounded server-side. Sized at
# 16384: thinking models draw reasoning tokens from the same budget as
# content, so a small cap can be exhausted in reasoning and yield an empty
# summary (design decision 10, "Output cap sizing").
MAX_OUTPUT_TOKENS = 16384

# Input cap in characters (≈25k tokens): above it the request is rejected
# with INPUT_TOO_LONG rather than risking an opaque provider 400 (design 10).
MAX_INPUT_CHARS = 100_000

# Backend-call timeout in seconds (connect + read), default sized for local
# 27B-class models on LAN hardware (design decision 10); overridable via
# SUMMARY_TIMEOUT, non-numeric values fall back to the default (same style as
# the PORT handling in app/main.py).
DEFAULT_SUMMARY_TIMEOUT = 120.0

# Fixed, server-side summarization instruction (design decision 1: the prompt
# is not user-customizable).
SUMMARY_INSTRUCTION = (
    "You are a summarization assistant. Summarize the transcript below: "
    "start with one sentence stating the video's topic, then list the key "
    "points as short lines, and finish with a one-sentence conclusion. "
    "Write in the same language as the transcript. Be factual and concise, "
    "and do not invent content that is not in the transcript."
)

SUMMARY_EXTENSION = ".summary"


class ProviderCallError(Exception):
    """A failed backend call, with a machine-readable reason.

    ``reason`` is one of ``unreachable``, ``timeout``, ``http_error``,
    ``malformed_response``, or ``empty_response``; ``detail`` is a safe,
    app-constructed message (no config file contents, base URLs, or keys).
    """

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def summary_timeout() -> float:
    """Resolve the backend-call timeout at call time (design decision 10)."""
    raw = os.environ.get("SUMMARY_TIMEOUT")
    try:
        return float(raw) if raw is not None else DEFAULT_SUMMARY_TIMEOUT
    except ValueError:
        return DEFAULT_SUMMARY_TIMEOUT


def _call_chat_completions(
    base_url: str,
    model: str,
    messages: list[dict],
    api_key: str | None,
    timeout: float,
) -> str:
    """POST the chat-completions request and return the model's text.

    Per-call ``requests.post`` (no shared session: thread-safe without
    locking, design decision 1). The bearer token is attached only when the
    provider defines an ``apiKey``. Raises :class:`ProviderCallError` with a
    machine-readable reason on every failure.
    """
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.Timeout as exc:
        raise ProviderCallError(
            "timeout",
            f"backend did not respond within {timeout:.0f}s",
        ) from exc
    except requests.RequestException as exc:
        # Type name only: str() of requests exceptions embeds the base URL,
        # which must stay out of the logs (design decision 13).
        raise ProviderCallError("unreachable", type(exc).__name__) from exc
    if response.status_code // 100 != 2:
        raise ProviderCallError(
            "http_error", f"backend returned HTTP {response.status_code}"
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderCallError(
            "malformed_response", "backend response is not valid JSON"
        ) from exc
    try:
        content = data["choices"][0]["message"]["content"]
    except (TypeError, KeyError, IndexError) as exc:
        raise ProviderCallError(
            "malformed_response",
            "backend response missing choices[0].message.content",
        ) from exc
    if not isinstance(content, str):
        raise ProviderCallError(
            "malformed_response", "choices[0].message.content is not a string"
        )
    # A 2xx whose content is empty or whitespace-only (thinking models that
    # exhaust the output budget in reasoning, gateways that return reasoning
    # in a side field alongside empty content) is a failed summarization, not
    # a successful one (design decision 1).
    if not content.strip():
        raise ProviderCallError(
            "empty_response",
            "backend returned empty or whitespace-only content",
        )
    return content


def summarize_with_provider(
    provider: Provider, model: str, text: str, timeout: float | None = None
) -> str:
    """Summarize ``text`` with the given provider/model and return the text.

    Emits exactly one structured event per call: ``summary_completed`` (info)
    or ``summary_failed`` (error) — never transcript/summary content, config
    file contents, or keys (design decision 13). Raises :class:`ProviderError`
    (HTTP 502 PROVIDER_ERROR) when the backend call fails.
    """
    logger = get_logger()
    start = time.monotonic()
    messages = [
        {"role": "system", "content": SUMMARY_INSTRUCTION},
        {"role": "user", "content": text},
    ]
    try:
        summary = _call_chat_completions(
            provider.base_url, model, messages, provider.api_key,
            summary_timeout() if timeout is None else timeout,
        )
    except ProviderCallError as exc:
        logger.error(
            "summary_failed",
            provider=provider.id,
            model=model,
            duration_ms=round((time.monotonic() - start) * 1000.0, 2),
            reason=exc.reason,
            detail=exc.detail,
        )
        raise ProviderError(
            f"The summarization backend failed ({exc.reason}). Please try again."
        ) from exc
    logger.info(
        "summary_completed",
        provider=provider.id,
        model=model,
        duration_ms=round((time.monotonic() - start) * 1000.0, 2),
        chars_in=len(text),
        chars_out=len(summary),
    )
    return summary


def save_summary(name: str, summary: str) -> None:
    """Best-effort write of the summary to ``<name>.summary`` (design 6).

    Overwrites any existing summary file on re-summarize and never raises:
    a write failure is reported only through a ``summary_save_failed`` error
    event carrying the transcript name, the target path, and the OS error.
    """
    path = transcript_dir() / (name + SUMMARY_EXTENSION)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(summary)
    except Exception as exc:
        get_logger().error(
            "summary_save_failed",
            name=name,
            path=str(path),
            reason=type(exc).__name__,
            detail=str(exc),
        )


def read_summary(name: str) -> tuple[bool, str]:
    """Read ``<name>.summary`` with the read-side discipline (design 6).

    Returns ``(ok, text)`` with the file's exact UTF-8 content. ``ok`` is
    False for a structurally invalid name (endpoint maps it to 400 via
    :func:`is_structurally_invalid_name` before any filesystem access) and
    for a missing or otherwise unreadable file (404). Validation order:
    structural reject, resolve-and-contain, regular-file check — the same
    traversal-safety rules as ``app.library.read_transcript``.
    """
    if is_structurally_invalid_name(name):
        return False, ""
    try:
        base = transcript_dir().resolve()
        target = (base / (name + SUMMARY_EXTENSION)).resolve()
        if not target.is_relative_to(base):
            return False, ""
        if not target.is_file():
            return False, ""
        return True, target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False, ""
