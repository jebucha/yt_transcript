"""FastAPI application: lifecycle logging, request logging, static UI."""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import chain as chain_mod
from app import log as applog
from app.errors import TranscriptError
from app.log import get_logger
from app.persist import save_transcript

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_PORT = 8000


class TranscriptRequest(BaseModel):
    url: str = ""

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
        return {
            "text": result.text,
            "video_id": result.video_id,
            "title": result.title,
            "language": result.language,
            "source": result.source,
        }

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
