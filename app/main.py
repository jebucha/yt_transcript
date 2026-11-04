"""FastAPI application: lifecycle logging, request logging, static UI."""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from queue import Empty

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import chain as chain_mod
from app import log as applog
from app import logbus
from app import summarize as summarize_mod
from app.errors import (
    InputTooLongError,
    InvalidProviderError,
    SummaryNotConfiguredError,
    TranscriptError,
)
from app.library import (
    is_structurally_invalid_name,
    list_transcripts,
    read_transcript,
)
from app.log import get_logger
from app.persist import derive_file_name, save_transcript
from app.providers import load_providers

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_PORT = 8000

# How long a log stream waits for the next entry before looping again. The
# poll runs in an executor thread, so a client disconnect can cancel the
# in-flight poll instead of leaving a worker blocked in queue.get().
LOG_POLL_TIMEOUT = 0.5


class TranscriptRequest(BaseModel):
    url: str = ""


class SummarizeRequest(BaseModel):
    text: str = ""  # the displayed transcript (source of truth, design 4)
    name: str = ""  # the transcript's file name (for the alongside save)
    provider: str = ""
    model: str = ""

# Configure JSON-to-stdout logging once, at import time, so every entry point
# (uvicorn app.main:app, python -m app.main, tests) emits the same format.
# Tests may reconfigure afterwards; loggers are created lazily, so nothing
# binds to the import-time configuration.
applog.setup_logging()


def _listen_port() -> int:
    try:
        return int(os.environ.get("PORT", DEFAULT_PORT))
    except ValueError:
        return DEFAULT_PORT


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = get_logger()
    logger.info("server_started", port=_listen_port())
    try:
        yield
    finally:
        get_logger().info("server_stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="yt-transcript", lifespan=lifespan)
    applog.install_excepthook()

    @app.middleware("http")
    async def log_http_requests(request, call_next):
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.monotonic() - start) * 1000.0
            get_logger().error(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=500,
                duration_ms=round(duration_ms, 2),
            )
            raise
        duration_ms = (time.monotonic() - start) * 1000.0
        get_logger().info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response

    @app.post("/api/transcript")
    async def transcript_endpoint(request: TranscriptRequest):
        try:
            result = await chain_mod.default_chain.run(request.url)
        except TranscriptError as exc:
            return JSONResponse(
                status_code=exc.status,
                content={"error": {"code": exc.code, "message": exc.message}},
            )
        # Best-effort persistence after a successful fetch: runs in a worker
        # thread (blocking I/O off the event loop) and never affects the
        # response (design decisions 1, 4 and 5).
        await asyncio.to_thread(
            save_transcript, result.text, result.title, result.video_id
        )
        # The derived persistence name (design decision 5): computed from the
        # title/video id, so the client gets it even when the best-effort
        # save above failed. Single source of truth for the file name.
        return {
            "text": result.text,
            "video_id": result.video_id,
            "title": result.title,
            "language": result.language,
            "source": result.source,
            "name": derive_file_name(result.title, result.video_id),
        }

    @app.get("/api/transcripts")
    async def list_transcripts_endpoint():
        # Read-only, best-effort: an unusable directory degrades to an empty
        # list (never an error). Blocking I/O runs off the event loop, as with
        # save_transcript; the endpoint never touches the fetch chain or the
        # single-flight semaphore (design decisions 1, 4 and 5).
        transcripts = await asyncio.to_thread(list_transcripts)
        return {"transcripts": transcripts}

    @app.get("/api/providers")
    async def providers_endpoint():
        # Read the config per request (design decision 3): edits take effect
        # without a restart, a missing/malformed file degrades to "not
        # configured". The response is secret-free: API keys and base URLs
        # never leave the server (design decision 7).
        config = await asyncio.to_thread(load_providers)
        return {
            "default": config.default,
            "providers": [
                {"id": p.id, "name": p.name, "models": list(p.models)}
                for p in config.providers
            ],
        }

    @app.get("/api/transcripts/{name}")
    async def read_transcript_endpoint(name: str):
        # Structural reject is the hard 400 rule (design decision 3, step 1),
        # applied before any filesystem access; a plain miss is a 404.
        if is_structurally_invalid_name(name):
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_NAME",
                                   "message": "Invalid transcript name."}},
            )
        ok, text = await asyncio.to_thread(read_transcript, name)
        if not ok:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "NOT_FOUND",
                                   "message": "This transcript is no longer available."}},
            )
        return {"name": name, "text": text}

    @app.get("/api/transcripts/{name}/summary")
    async def read_summary_endpoint(name: str):
        # Structural reject is the hard 400 rule, applied before any
        # filesystem access; a plain miss is a 404. Read-only and
        # side-effect-free, and it never touches the fetch chain or the
        # single-flight semaphore (design decisions 4 and 9).
        if is_structurally_invalid_name(name):
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_NAME",
                                   "message": "Invalid transcript name."}},
            )
        ok, summary = await asyncio.to_thread(summarize_mod.read_summary, name)
        if not ok:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "NOT_FOUND",
                                   "message": "No saved summary for this transcript."}},
            )
        return {"name": name, "summary": summary}

    @app.post("/api/summarize")
    async def summarize_endpoint(request: SummarizeRequest):
        # Validation order (design decision 8): cheap local checks precede
        # the expensive network call, every rejection path is backend-free,
        # and when several rejections apply the first failing step wins.
        if is_structurally_invalid_name(request.name):
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_NAME",
                                   "message": "Invalid transcript name."}},
            )
        config = await asyncio.to_thread(load_providers)
        if not config.providers:
            error = SummaryNotConfiguredError()
            return JSONResponse(
                status_code=error.status,
                content={"error": {"code": error.code,
                                   "message": error.message}},
            )
        provider = next(
            (p for p in config.providers if p.id == request.provider), None
        )
        if provider is None or request.model not in provider.models:
            error = InvalidProviderError()
            return JSONResponse(
                status_code=error.status,
                content={"error": {"code": error.code,
                                   "message": error.message}},
            )
        if len(request.text) > summarize_mod.MAX_INPUT_CHARS:
            error = InputTooLongError()
            return JSONResponse(
                status_code=error.status,
                content={"error": {"code": error.code,
                                   "message": error.message}},
            )
        # The backend call runs in a worker thread; the endpoint never touches
        # the fetch chain or the single-flight semaphore (design decision 9).
        try:
            summary = await asyncio.to_thread(
                summarize_mod.summarize_with_provider,
                provider, request.model, request.text,
            )
        except TranscriptError as exc:
            # ProviderError (PROVIDER_ERROR 502) and friends.
            return JSONResponse(
                status_code=exc.status,
                content={"error": {"code": exc.code, "message": exc.message}},
            )
        # Best-effort summary save: a failure is logged, never returned
        # (design decision 6).
        await asyncio.to_thread(summarize_mod.save_summary, request.name, summary)
        return {"summary": summary}

    @app.get("/api/logs")
    async def log_stream_endpoint():
        # Server-sent events stream of the in-memory log bus (design 2-4).
        # Read-only: no filesystem work, and it never touches the fetch chain
        # or the single-flight semaphore.
        bus = logbus.DEFAULT_BUS

        async def event_stream():
            # Subscribe before snapshotting: an entry logged between the two
            # would otherwise be lost on the first connect.
            queue = bus.subscribe()
            try:
                for entry in bus.snapshot():
                    yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
                while True:
                    try:
                        entry = await asyncio.to_thread(
                            queue.get, timeout=LOG_POLL_TIMEOUT
                        )
                    except Empty:
                        continue
                    yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
            finally:
                bus.unsubscribe(queue)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Mounted last so the API routes above take precedence.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()


def main() -> None:
    import uvicorn

    applog.setup_logging()
    applog.install_excepthook()
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=_listen_port(), log_level="warning")


if __name__ == "__main__":
    main()
