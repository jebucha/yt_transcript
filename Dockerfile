# yt-transcript — single-stage image, podman-compatible.
# Final size: ~251 MB measured (podman build, arm64).
FROM astral/uv:python3.13-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

# Install pinned dependencies first (better layer caching).
COPY pyproject.toml uv.lock .
RUN uv sync --frozen --no-dev

# Application code (includes app/static/ for the frontend).
COPY app ./app

# Run as an unprivileged user.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uv", "run", "--frozen", "--no-dev", "python", "-m", "app.main"]
