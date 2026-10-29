"""Fetch chain orchestration.

One attempt on the primary fetcher; on a transient upstream failure (code
UPSTREAM_FAILURE) exactly one attempt on the fallback fetcher. A global
single-flight semaphore ensures at most one chain hits YouTube at a time;
concurrent callers are rejected immediately with BusyError (HTTP 503).

Every attempt is logged as one structured entry (event "fetch_attempt") with
the video ID, requested language, fetcher source, outcome (+ failure reason),
duration in ms, and the transcript character count on success.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from app import fetchers
from app.errors import (
    FALLBACK_CODES,
    BusyError,
    TranscriptError,
    UpstreamFailureError,
)
from app.log import get_logger
from app.urls import parse_video_ref

REQUESTED_LANGUAGE = "en"


@dataclass(frozen=True)
class FetchResult:
    text: str
    video_id: str
    title: str
    language: str
    source: str  # "primary" | "fallback"


class FetchChain:
    def __init__(
        self,
        primary=None,
        fallback=None,
        semaphore: asyncio.Semaphore | None = None,
        attempt_timeout: float = fetchers.ATTEMPT_TIMEOUT,
    ) -> None:
        self._primary = primary or fetchers.primary_fetch
        self._fallback = fallback or fetchers.fallback_fetch
        self._semaphore = semaphore or asyncio.Semaphore(1)
        self._attempt_timeout = attempt_timeout

    async def run(self, url: str) -> FetchResult:
        # Pure parsing: no network, no semaphore.
        video_id = parse_video_ref(url)

        if self._semaphore.locked():
            get_logger().warning(
                "fetch_rejected", video_id=video_id, reason="busy"
            )
            raise BusyError()
        await self._semaphore.acquire()
        try:
            try:
                text, language, title = await self._attempt("primary", video_id)
                return FetchResult(text, video_id, title, language, "primary")
            except TranscriptError as exc:
                if exc.code not in FALLBACK_CODES:
                    raise
                text, language, title = await self._attempt("fallback", video_id)
                return FetchResult(text, video_id, title, language, "fallback")
        finally:
            self._semaphore.release()

    async def _attempt(self, source: str, video_id: str) -> tuple[str, str, str]:
        """Run one fetcher in a worker thread with a hard timeout, logging
        exactly one structured entry for the attempt."""
        func = self._primary if source == "primary" else self._fallback
        logger = get_logger()
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(func, video_id, REQUESTED_LANGUAGE),
                timeout=self._attempt_timeout,
            )
        except TranscriptError as exc:
            logger.error(
                "fetch_attempt",
                video_id=video_id,
                language=REQUESTED_LANGUAGE,
                source=source,
                outcome="failure",
                reason=exc.code,
                duration_ms=round((time.monotonic() - start) * 1000.0, 2),
            )
            raise
        except asyncio.TimeoutError as exc:
            timeout_err = UpstreamFailureError(
                f"{source} fetch timed out after {self._attempt_timeout:.0f}s"
            )
            logger.error(
                "fetch_attempt",
                video_id=video_id,
                language=REQUESTED_LANGUAGE,
                source=source,
                outcome="failure",
                reason=timeout_err.code,
                duration_ms=round((time.monotonic() - start) * 1000.0, 2),
            )
            raise timeout_err from exc
        except Exception as exc:  # defensive: anything unexpected is upstream
            generic = UpstreamFailureError(
                f"{source} fetch failed: {type(exc).__name__}"
            )
            logger.error(
                "fetch_attempt",
                video_id=video_id,
                language=REQUESTED_LANGUAGE,
                source=source,
                outcome="failure",
                reason=generic.code,
                duration_ms=round((time.monotonic() - start) * 1000.0, 2),
            )
            raise generic from exc

        duration_ms = (time.monotonic() - start) * 1000.0
        text, language, _title = result
        logger.info(
            "fetch_attempt",
            video_id=video_id,
            language=REQUESTED_LANGUAGE,
            source=source,
            outcome="success",
            duration_ms=round(duration_ms, 2),
            chars=len(text),
        )
        return text, language, _title


# Module-level default chain used by the HTTP API (patchable in tests).
default_chain = FetchChain()
