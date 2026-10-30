# Tasks

## 1. Project init and dependency migration

- [x] 1.1 Run `uv init --bare --name yt-transcript --python 3.13` then `uv python pin 3.13` (writes `.python-version` — `uv init --bare` alone does not create it); verify `pyproject.toml` and `.python-version` (content `3.13`) exist and no scaffold files (`main.py`, hello file) were added to the repo root
- [x] 1.2 Populate `pyproject.toml`: `[project]` with name `yt-transcript`, `requires-python = ">=3.13"`, and the six verbatim runtime pins (fastapi==0.162.0, uvicorn==0.54.0, structlog==26.1.0, youtube-transcript-api==1.2.4, yt-dlp==2026.10.26, requests==2.34.2 with its explanatory comment); add PEP 735 `dependency-groups.dev` with pytest==9.2.0, httpx==0.28.1, playwright==1.64.1; run `uv lock`; verify `uv.lock` records exactly the pre-migration versions for all nine packages (`uv.lock` stores `name = "…"` and `version = "…"` on separate lines, so check each name/version pair rather than grepping for `pkg==version`)
- [x] 1.3 Rebuild the local environment: `rm -rf .venv && uv sync`; verify `uv run python --version` reports 3.13 and the recreated `.venv/` is still matched by the existing `.gitignore` and `.dockerignore` entries

## 2. Local verification under uv

- [x] 2.1 Run `uv run python -m pytest tests/ -q --ignore=tests/e2e`; verify all unit/API/logging tests pass
- [x] 2.2 Run the e2e suite under uv: `uv run python -m playwright install chromium` (one-time, only if browsers are not already installed) then `uv run python -m pytest tests/e2e/ -q`; verify all e2e tests pass in headless Chromium

## 3. Container migration (strategy A)

- [x] 3.1 Update `.dockerignore`: remove the `requirements-dev.txt` line; verify `pyproject.toml` and `uv.lock` are not listed (they must stay in the build context) and no other line references a deleted file
- [x] 3.2 Rewrite the `Dockerfile` per design decision 5: `FROM astral/uv:python3.13-bookworm-slim`, `COPY pyproject.toml uv.lock .` before app code, `RUN uv sync --frozen --no-dev`, drop `PIP_DISABLE_PIP_VERSION_CHECK`, keep `PYTHONDONTWRITEBYTECODE`/`PYTHONUNBUFFERED`/`PORT`/`HOST`, `appuser` + chown, `EXPOSE 8000`, `CMD ["uv", "run", "--frozen", "--no-dev", "python", "-m", "app.main"]` (the runtime `--no-dev` is required — without it `uv run` re-syncs the dev group at container start); update the stale `python:3.13-slim` reference in the `docker-compose.yml` healthcheck comment (comment-only, no functional change); verify `docker build -t yt-transcript .` succeeds
- [x] 3.3 Measure the built image size (`docker images yt-transcript`) and update the Dockerfile size-estimate comment with the measured figure; verify the comment no longer cites the obsolete estimate without the measured value
- [x] 3.4 Run `docker compose up -d --build`; verify the container reports healthy, then run the smoke test documented in the README (finalized in 4.1): UI 200, valid URL 200 with transcript, invalid URL 400; check `docker logs yt-transcript` for `fetch_attempt` lines with `"outcome": "success"`
- [x] 3.5 If a podman toolchain is available on the build machine, run the podman compose equivalents (`podman compose config`, `podman compose up -d --build`); verify healthy, or explicitly record unavailability in the task completion note

## 4. Docs, cleanup, and commit

- [x] 4.1 Rewrite the README Development section for uv (`uv sync`, `uv run python -m pytest tests/ -q --ignore=tests/e2e`, `uv run python -m playwright install chromium`, `uv run python -m pytest tests/e2e/ -q`, `uv run python -m app.main`); verify each documented command runs as written from a clean checkout of the new state
- [x] 4.2 Rewrite the README library-update runbook: `uv add 'youtube-transcript-api==<new-version>' 'yt-dlp==<new-version>'` (preserves exact pins — verified that `-U`/`--upgrade-package` do not move exact pins in uv 0.13.6), then commit the refreshed `pyproject.toml`/`uv.lock` (the `pip freeze | grep` re-pinning step is gone); verify no `pip`, `venv`, or `requirements` references remain in README.md
- [x] 4.3 Delete `requirements.txt` and `requirements-dev.txt`; verify the project's own surfaces (`README.md`, `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `app/`, `tests/`) contain no remaining references to `pip` or `requirements*.txt` — OpenSpec change docs (historical archives and this change's own artifacts), tooling docs (`.claude/`, `.opencode/`), and the `.venv/` ignore entries in `.gitignore`/`.dockerignore` (uv reuses that directory name) are intentionally out of scope
- [x] 4.4 Commit the change as a single commit; verify `git show --stat` shows `pyproject.toml`, `uv.lock`, `.python-version`, `Dockerfile`, `docker-compose.yml` (comment-only), `.dockerignore`, `README.md` modified/new and the two requirements files deleted

## Workflow follow-up

- Archive the change (`/opsx-archive`) after the project's review requirements are satisfied.
