"""FastAPI application: lifecycle logging, request logging, static UI."""

from __future__ import annotations

import asyncio
import contextvars
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from queue import Empty

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import chain as chain_mod
from app import log as applog
from app import logbus
from app import model_discovery as discovery_mod
from app import summarize as summarize_mod
from app.errors import (
    InputTooLongError,
    InvalidModelError,
    InvalidProviderError,
    ModelNotRemovableError,
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
from app.provider_overrides import (
    ModelNotFoundError,
    add_model,
    apply_overrides,
    is_valid_model_id,
    load_overrides,
    remove_model,
)
from app.providers import ProviderConfig, load_providers
from app.settings import load_settings, save_settings

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_PORT = 8000

# How long a log stream waits for the next entry before looping again. The
# poll runs in an executor thread, so a client disconnect can cancel the
# in-flight poll instead of leaving a worker blocked in queue.get().
LOG_POLL_TIMEOUT = 0.5

# Max concurrent summarization backend calls. Each call pins a worker for up
# to the 120 s LLM timeout, so it runs on a bounded pool of its own rather
# than the default executor every other endpoint's blocking work shares;
# excess in-flight requests wait for a free slot instead of being rejected.
SUMMARIZE_MAX_CONCURRENCY = 2
SUMMARIZE_EXECUTOR = ThreadPoolExecutor(
    max_workers=SUMMARIZE_MAX_CONCURRENCY, thread_name_prefix="summarize"
)

# Max concurrent model-discovery calls (design D6): a dedicated bounded pool
# separate from SUMMARIZE_EXECUTOR — a 120 s summarize must not block a fast
# /models call, and a hanging discovery must not starve summarization.
DISCOVERY_MAX_CONCURRENCY = 2
DISCOVERY_EXECUTOR = ThreadPoolExecutor(
    max_workers=DISCOVERY_MAX_CONCURRENCY, thread_name_prefix="discovery"
)

# Max request-body size in bytes (5 MiB). Checked against the declared
# Content-Length before the body is read or parsed, so an oversized upload
# cannot exhaust process memory. The app's real payload ceiling is the
# 100k-char text cap (<1 MB worst case), so 5 MiB leaves wide headroom.
# Module-level so tests can monkeypatch it.
MAX_BODY_BYTES = 5 * 1024 * 1024


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


def effective_config() -> ProviderConfig:
    """The effective provider config: the file config merged with the
    per-call overlay read (design D2).

    Both reads run in a worker thread (blocking I/O off the event loop). The
    merge is pure; a missing/malformed overlay degrades to the file-only
    config, and the response is secret-free (keys and base URLs never leave
    the server).
    """
    return apply_overrides(load_providers(), load_overrides())


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

    # Registered before the logging middleware (Starlette applies the
    # first-added HTTP middleware as the outermost layer) so 413 rejections
    # are covered by the http_request log line. Header check only: the
    # declared length is compared without reading the body, which fires
    # before Starlette's full-body read + JSON parse.
    @app.middleware("http")
    async def limit_body_size(request, call_next):
        length = request.headers.get("content-length")
        if length is not None and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"error": {"code": "BODY_TOO_LARGE",
                                   "message": "Request body too large."}},
            )
        return await call_next(request)

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
        # Read the config and the overlay per request (design decision 3 /
        # D2): edits take effect without a restart, a missing/malformed file
        # degrades to "not configured". The effective list is the file
        # config merged with the overlay (file models first, then
        # non-duplicate overlay ids); ``addedModels`` carries the
        # overlay-supplied subset so the UI can distinguish removable models.
        # The response is secret-free: API keys and base URLs never leave
        # the server (design decision 7).
        config = await asyncio.to_thread(effective_config)
        return {
            "default": config.default,
            "providers": [
                {
                    "id": p.id,
                    "name": p.name,
                    "models": list(p.models),
                    "addedModels": list(p.added_models),
                }
                for p in config.providers
            ],
        }

    # The add/remove endpoints share one body rule (design D4/D5): the model
    # id travels in a JSON body — model ids routinely contain "/" (e.g.
    # "meta-llama/Llama-3"), which a {model} path segment would not carry
    # safely — and must be a string field named "model".
    async def _parse_model_body(request: Request) -> object:
        try:
            return await request.json()
        except Exception:
            return None

    def _model_body_error(body: object) -> JSONResponse | None:
        if not isinstance(body, dict) or not isinstance(body.get("model"), str):
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_BODY",
                                   "message": 'Expected a JSON object with a '
                                              '"model" field.'}},
            )
        return None

    def _error_response(code: str, message: str, status: int) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={"error": {"code": code, "message": message}},
        )

    @app.post("/api/providers/{provider_id}/models")
    async def add_model_endpoint(provider_id: str, request: Request):
        # The provider is validated against the *file* config: the overlay
        # never introduces a provider (design D2). Rejection precedence:
        # unknown provider, then body rules (design D5). The read-modify-
        # write runs in a worker thread off the event loop, and the endpoint
        # never touches the fetch chain or the single-flight semaphore, nor
        # any summarization backend.
        config = await asyncio.to_thread(load_providers)
        provider = next(
            (p for p in config.providers if p.id == provider_id), None
        )
        if provider is None:
            error = InvalidProviderError()
            return _error_response(error.code, error.message, error.status)
        body = await _parse_model_body(request)
        invalid_body = _model_body_error(body)
        if invalid_body is not None:
            return invalid_body
        model_id = body["model"].strip()
        if not is_valid_model_id(model_id):
            error = InvalidModelError()
            return _error_response(error.code, error.message, error.status)
        try:
            models = await asyncio.to_thread(add_model, provider, model_id)
        except InvalidModelError as exc:  # the per-provider addition cap
            return _error_response(exc.code, exc.message, exc.status)
        if models is None:
            # The overlay write failed; provider_overrides_save_failed is
            # already logged and no partial state was left.
            return _error_response(
                "WRITE_FAILED",
                "Could not save the provider overrides file.",
                500,
            )
        return {"provider": provider.id, "model": model_id, "models": models}

    @app.delete("/api/providers/{provider_id}/models")
    async def remove_model_endpoint(provider_id: str, request: Request):
        # Same body rule and file-config validation as the add endpoint.
        # Only overlay-added ids are removable: a config-file model is 400
        # MODEL_NOT_REMOVABLE, an id in neither set is 404 NOT_FOUND (plain
        # HTTP, outside the taxonomy), a failed write is 500 WRITE_FAILED.
        config = await asyncio.to_thread(load_providers)
        provider = next(
            (p for p in config.providers if p.id == provider_id), None
        )
        if provider is None:
            error = InvalidProviderError()
            return _error_response(error.code, error.message, error.status)
        body = await _parse_model_body(request)
        invalid_body = _model_body_error(body)
        if invalid_body is not None:
            return invalid_body
        model_id = body["model"].strip()
        try:
            models = await asyncio.to_thread(remove_model, provider, model_id)
        except ModelNotRemovableError as exc:
            return _error_response(exc.code, exc.message, exc.status)
        except ModelNotFoundError:
            return _error_response(
                "NOT_FOUND", "This model is not listed for that provider.", 404
            )
        if models is None:
            return _error_response(
                "WRITE_FAILED",
                "Could not save the provider overrides file.",
                500,
            )
        return {"provider": provider.id, "model": model_id, "models": models}

    @app.get("/api/providers/{provider_id}/available-models")
    async def available_models_endpoint(provider_id: str):
        # Discover the provider's models live from its OpenAI-compatible
        # /models (design D6). The provider is resolved against the *file*
        # config first: the overlay never changes which base URL is
        # contacted. The call runs on the dedicated bounded pool
        # (DISCOVERY_EXECUTOR), off the event loop, and the endpoint never
        # touches the fetch chain or the single-flight semaphore. The
        # response is a bare ``models`` array of id strings — no base URL,
        # no API key (design D6).
        config = await asyncio.to_thread(load_providers)
        provider = next(
            (p for p in config.providers if p.id == provider_id), None
        )
        if provider is None:
            error = InvalidProviderError()
            return _error_response(error.code, error.message, error.status)
        try:
            models = await asyncio.get_running_loop().run_in_executor(
                DISCOVERY_EXECUTOR,
                contextvars.copy_context().run,
                discovery_mod.list_models,
                provider,
            )
        except TranscriptError as exc:
            # ProviderError (PROVIDER_ERROR 502); the refresh-failure event
            # is already logged by list_models.
            return _error_response(exc.code, exc.message, exc.status)
        return {"models": models}

    @app.get("/api/settings")
    async def settings_read_endpoint():
        # Read settings.json per request (design D3): edits on disk take
        # effect without a restart, and a missing/unusable file degrades to
        # the safe off-default. Read-only and side-effect-free: it never
        # touches the fetch chain or the single-flight semaphore, and blocking
        # I/O runs off the event loop.
        settings = await asyncio.to_thread(load_settings)
        return {"autoSummarize": settings.auto_summarize}

    @app.post("/api/settings")
    async def settings_write_endpoint(request: Request):
        # Validate the body before any filesystem access (design D3): a
        # non-object body or a missing/non-boolean autoSummarize is a 400
        # INVALID_BODY with no write. A write failure is a 500 WRITE_FAILED
        # (save_settings already logged settings_save_failed). Never touches
        # the fetch chain or the single-flight semaphore.
        try:
            body = await request.json()
        except Exception:
            body = None
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_BODY",
                                   "message": "Expected a JSON object with a "
                                              "boolean autoSummarize field."}},
            )
        auto_summarize = body.get("autoSummarize")
        if not isinstance(auto_summarize, bool):
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_BODY",
                                   "message": "autoSummarize must be a "
                                              "boolean."}},
            )
        saved = await asyncio.to_thread(save_settings, auto_summarize)
        if not saved:
            return JSONResponse(
                status_code=500,
                content={"error": {"code": "WRITE_FAILED",
                                   "message": "Could not save the settings "
                                              "file."}},
            )
        return {"autoSummarize": auto_summarize}

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
        # and when several rejections apply the first failing step wins. The
        # provider/model pair is validated against the *effective* (merged)
        # list, which is the same set the listing endpoint serves — an
        # overlay-added model is immediately usable (design D2).
        if is_structurally_invalid_name(request.name):
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_NAME",
                                   "message": "Invalid transcript name."}},
            )
        config = await asyncio.to_thread(effective_config)
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
        # The backend call runs in a worker thread on the dedicated bounded
        # pool (SUMMARIZE_EXECUTOR), so in-flight LLM calls can never occupy
        # the default executor other endpoints share; excess in-flight
        # requests wait for a free pool slot. run_in_executor with a copied
        # context mirrors asyncio.to_thread's semantics — this runtime's
        # to_thread has no executor parameter (design D1 runtime note) — and
        # the endpoint never touches the fetch chain or the single-flight
        # semaphore (design decision 9).
        try:
            summary = await asyncio.get_running_loop().run_in_executor(
                SUMMARIZE_EXECUTOR,
                contextvars.copy_context().run,
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
    # App-wide connection backpressure: while 100 connections are in flight,
    # uvicorn itself rejects new ones with 503 (design D2).
    uvicorn.run(app, host=host, port=_listen_port(), log_level="warning",
                limit_concurrency=100)


if __name__ == "__main__":
    main()
