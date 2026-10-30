# Design

## Context

Current dependency tooling (see proposal.md for motivation): a stdlib `venv`
at `.venv/` (git-ignored), `requirements.txt` (6 exact runtime pins) and
`requirements-dev.txt` (`-r`-including it, adding pytest/httpx/playwright), a
`Dockerfile` on `python:3.13-slim` that runs `pip install --no-cache-dir`, and
three `venv`/`pip` command blocks in `README.md`.

Constraints that shape the approach:

- The app is a **virtual (unpacked) project**: no build step, no packaging,
  run as `python -m app.main`. It must stay that way — nothing is
  distributed.
- `uv` 0.13.6 is installed on the development machine; Python 3.13 is the
  pinned interpreter.
- The compose file is deliberately inside the key set supported by both
  `docker compose` and `podman compose` (prior design decision, kept). The
  healthcheck calls plain `python -c 'import urllib.request; ...'` (stdlib
  only) and must keep working.
- Playwright must never enter the container image (dev-only e2e invariant).
- `tests/conftest.py` already inserts the project root into `sys.path`, so
  `uv run pytest` works even though the project is not installed into the
  venv (verified — no test-side changes needed).

## Goals / Non-Goals

**Goals:**

- One source of truth for dependencies: `pyproject.toml` (intent) + committed
  `uv.lock` (exact resolution), used by both local dev and the container build.
- Zero references to `pip`, `venv`, or `requirements*.txt` in the project's
  own code and docs (README, Dockerfile, .dockerignore, docker-compose.yml,
  `app/`, `tests/`); historical OpenSpec change docs and tooling docs are
  out of scope.
- Container build is reproducible offline-from-resolution: install strictly
  from `uv.lock` with no network dependency resolution at build time.

**Non-Goals:**

- No packaging of `app/` as an installable distribution.
- No dependency version upgrades — the nine direct pins migrate verbatim
  (transitive versions are re-resolved by `uv lock`, which is allowed — see
  risks); the runbook is updated, not exercised.
- No compose file changes, no app code/test/static changes, no CI addition.
- No changes to OpenSpec specs (no behavior change; `skip_specs: true`).

## Decisions

1. **Init with `uv init --bare --name yt-transcript --python 3.13`, then
   `uv python pin 3.13`.**
   Verified in uv 0.13.6: `uv init --bare` creates `pyproject.toml` and
   nothing else (no `.python-version`); the follow-up pin command writes
   `.python-version` (`3.13`). Plain `uv init` was rejected: it scaffolds a
   `main.py`-style hello file into the repo root and can rewrite the
   existing README.

2. **Virtual project layout, no build system.**
   `pyproject.toml` carries `[project]` metadata (name,
   `requires-python = ">=3.13"`) and dependency lists, but no
   `[build-system]`. `uv sync` then only installs dependencies. The app
   keeps running via `python -m app.main`; import resolution in tests is
   already handled by `tests/conftest.py`.

3. **PEP 735 `dependency-groups.dev` for dev/test deps** (pytest, httpx,
   playwright — verbatim pins). `uv sync` installs the dev group by default
   (local dev), and `uv sync --no-dev` in the container excludes it,
   preserving the "Playwright never enters the image" invariant. The legacy
   `[tool.uv] dev-dependencies` table and a third `requirements-dev.txt`
   were rejected (deprecated / contrary to the goal respectively).

4. **Commit `uv.lock`.** The lockfile is the pin record that replaces the
   two `requirements*.txt` files; the runbook's `pip freeze | grep` step
   disappears because `uv add 'pkg==<new-version>' ...` rewrites
   `pyproject.toml` + `uv.lock` in one step and the diff is the reviewable
   change. `-U`/`--upgrade-package` were rejected: verified in uv 0.13.6
   that neither moves exact pins (they leave `==` requirements unchanged).

5. **Container strategy A — `astral/uv` base image, no pip anywhere.**
   `FROM astral/uv:python3.13-bookworm-slim`,
   `COPY pyproject.toml uv.lock .`, `RUN uv sync --frozen --no-dev`,
   `CMD ["uv", "run", "--frozen", "--no-dev", "python", "-m", "app.main"]`.
   - `--frozen` at build: install strictly from the lock, no resolution
     (fails loudly if lock and pyproject disagree).
   - `--frozen --no-dev` at runtime: no re-resolution (frozen) and no
     dev-group re-sync (no-dev), so startup performs no network access.
     Verified in uv 0.13.6: a bare `uv run --frozen` re-syncs the default
     dev group (pytest, httpx, playwright) against the image's empty cache —
     which would require network and break the Playwright invariant — while
     `uv run --frozen --no-dev` installs nothing.
   - The base image bundles a 3.13 interpreter matching `.python-version`,
     so no interpreter download happens at build time.
   - Alternatives rejected: (B) `python:3.13-slim` + curl-install uv — extra
     download step and non-idiomatic; (C) `uv export` to a generated
     `requirements.txt` + `pip` in the image — reintroduces pip and a
     generated file, directly contrary to the goal.
   - Existing Dockerfile structure is preserved: dependencies copied/installed
     before app code (layer caching), unprivileged `appuser` + chown,
     `PYTHONDONTWRITEBYTECODE`/`PYTHONUNBUFFERED`, `EXPOSE 8000`. The
     `PIP_DISABLE_PIP_VERSION_CHECK` ENV line is removed (no pip).
   - Compose healthcheck functionally unchanged: the uv image's bundled
     interpreter provides stdlib `urllib.request`. Only the stale
     `python:3.13-slim` reference in the `docker-compose.yml` healthcheck
     comment is updated (comment-only, no functional change).

6. **Local environment rebuild, same directory name.**
   `rm -rf .venv` → `uv sync`. uv's default venv location is `.venv`, so
   `.gitignore` (`.venv/`) and `.dockerignore` (`.venv/`) entries carry over
   untouched. If the interpreter is not yet in uv's cache, `uv sync` fetches
   CPython 3.13 automatically.

7. **Docs and build hygiene.**
   README development section becomes `uv sync` / `uv run python -m pytest` /
   `uv run python -m playwright install chromium` (one-time) /
   `uv run python -m app.main`; the library-update runbook becomes
   `uv add 'youtube-transcript-api==<new>' 'yt-dlp==<new>'` (exact pins
   preserved) + commit `pyproject.toml`/`uv.lock` + rebuild. `.dockerignore` drops the
   `requirements-dev.txt` line (file deleted); `pyproject.toml` and
   `uv.lock` must remain in the build context (they are not ignored).
   Dockerfile size-estimate comment is updated with the measured size after
   rebuild (previous estimate was a floor-boundary, not a hard target).

## Risks / Trade-offs

- [Image size drift vs the documented ~150–160 MB estimate] → the Astral base
  adds the uv binary; measure after rebuild on both architectures, update the
  Dockerfile comment with the new figure rather than asserting an old one.
- [Podman compatibility of the `astral/uv` image] → it is multi-arch on
  Docker Hub; verify with the existing validation pattern
  (`podman compose config` + `podman compose up -d --build` → healthy) if a
  podman toolchain is available on the build machine.
- [Transitive version drift: `uv lock` re-resolves all transitive
  dependencies (34 packages for this pin set), so they may differ from the
  current `.venv`] → accepted: only the nine direct pins are promised
  identical; tasks 2.1/2.2 (unit + e2e suites) are the acceptance check.
- [Lock/pyproject drift: local `uv run` silently re-locks stale state while
  the container build fails] → workflow discipline (commit the refreshed
  lock with any dependency change); `--frozen` builds make drift fail loudly
  at build time instead of shipping a surprise.
- [Bare-`python` commands elsewhere in docs] → grep-tracked: README is the
  only tracked file with venv/pip blocks (verified); archived change docs are
  historical and intentionally untouched.
- [Rollback] → single commit; `git revert` restores the requirements files
  and Dockerfile, and `uv sync` output (`.venv/`) is regenerable either way.

## Migration Plan

1. `uv init --bare --name yt-transcript --python 3.13`; `uv python pin 3.13`
   (writes `.python-version`); fill `[project].dependencies` (6 verbatim
   pins, keep the `requests` comment) and `dependency-groups.dev` (3
   verbatim pins).
2. `uv lock`; verify the lock records the exact pre-existing versions.
3. `rm -rf .venv && uv sync`; run `python -m pytest tests/ -q
   --ignore=tests/e2e` (via `uv run`) and the e2e suite.
4. Rewrite `Dockerfile` (strategy A) and `.dockerignore`; `docker build`,
   check size, `docker compose up -d --build` → healthy, run the README
   smoke test. Podman equivalents where available.
5. Update `README.md` (dev section + runbook); delete
   `requirements.txt` / `requirements-dev.txt`.
6. Commit `pyproject.toml`, `uv.lock`, `.python-version`, and the updated
   files in one commit (rollback unit = the commit).
