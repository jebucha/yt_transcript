# `Dockerfile` — single-stage podman-compatible image

## Purpose

The build definition for the yt-transcript container image: a single-stage
image (~251 MB as measured on arm64; size varies by architecture) built from
`astral/uv:python3.13-bookworm-slim`, running the app as an unprivileged user
with no dev dependencies installed. Designed
for podman parity — works identically under `docker build` and `podman build`.

## Public surface

- **Base image:** `astral/uv:python3.13-bookworm-slim` (Python 3.13, uv pre-installed)
- **Environment variables set in the image:**
  - `PYTHONDONTWRITEBYTECODE=1` — disable .pyc generation in the container
  - `PYTHONUNBUFFERED=1` — stdout flushes immediately (critical for log streaming)
  - `PORT=8000`, `HOST=0.0.0.0` — uvicorn defaults, overridable at runtime
  - `TRANSCRIPT_DIR=/transcripts` — absolute path where transcripts are written
- **Exposed port:** `8000/tcp` (HTTP)
- **Entry point:** `CMD ["uv", "run", "--frozen", "--no-dev", "python", "-m", "app.main"]`

## Invariants

- **Single-stage only.** No multi-build, no build args, no cache mounts — the
  Dockerfile must work under podman which has limited BuildKit support.
- **Layer cache discipline.** Dependencies are copied and installed *before* the
  application code (`COPY pyproject.toml uv.lock .` then `uv sync --frozen --no-dev`,
  then `COPY app ./app`). Changing only source code does not invalidate the
  dependency install layer.
- **`--no-dev` in both build and runtime.** The dev dependency group (pytest,
  playwright, markdown) is never installed — the image contains only runtime
  dependencies from the main group. This matches the compose healthcheck and log
  rotation that assume a minimal container footprint.
- **Unprivileged user.** `appuser` owns `/app`; no root operations after useradd.
  The UID/GID assignment at build time is deterministic.
- **Start-up under 1 second** (measured on typical VPS hardware). The image has
  no warmup dependencies — the app starts immediately when the container runs.

## Log events emitted

N/A — this file emits nothing. However, it configures the runtime environment
that controls logging behavior: `PYTHONUNBUFFERED=1` ensures log lines flush to
stdout on every write, which is essential for the SSE log viewer and Docker's
`docker logs` output. Without it, buffered writes would make real-time log
streaming impossible.

## Error codes raised/handled

Failure modes during build or runtime:
- **Missing `uv.lock`** — build fails with an exit error (pinned dependencies are mandatory)
- **Non-podman BuildKit features used** — podman may reject the build; kept to
  POSIX-compatible Dockerfile syntax only
- **Port already in use at runtime** — uvicorn exits with EADDRINUSE; the app
  has no retry logic for this

## Design decisions

Resolved from `2026-10-29-add-docker-compose` (archived design doc):
- The base image choice (`astral/uv:python3.13-bookworm-slim`) replaces the original
  `python:3.13-slim` — uv is available natively, no separate pip install step needed
- `--frozen` flag in both build and runtime ensures bit-for-bit reproducibility

Also from later changes:
- `add-transcript-summary` decision on provider config mount path compatibility with the image's `/app` working directory
- `2026-10-30-migrate-to-uv` — uv is now the dependency manager, reflected in the sync command

## Cross-links

- [`docker-compose.yml`](compose-yml.html) — builds this Dockerfile (`build: .`)
- [`app/main.py`](../main.html) — CMD entry point; `create_app()` + `main()`
- README.md → Deployment section (podman commands, runtime config)
