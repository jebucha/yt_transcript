# Proposal

## Why

The project manages Python dependencies with the stdlib `venv` + `pip` + two
hand-maintained `requirements*.txt` files, and the container image builds with
`pip install`. This gives no single source of truth (the two `.txt` files must
stay in sync via `-r` includes), no lockfile, and an extra `pip freeze | grep`
step in the library-update runbook. The project owner wants the entire
toolchain — local development, the lockfile, and the container build — to run
on `uv`, with `pip` and `venv` removed from every surface. `uv` 0.13.6 is
already installed on the development machine; the migration is a pure tooling
swap with no behavior change.

## What Changes

- **Remove** `requirements.txt` and `requirements-dev.txt`.
- **Add** `pyproject.toml` (created via `uv init --bare --name yt-transcript
  --python 3.13`) with the six runtime pins in `[project].dependencies` and the
  three dev/test deps (pytest, httpx, playwright) in a PEP 735
  `dependency-groups.dev` group; plus `.python-version` (`3.13`, written by a
  follow-up `uv python pin 3.13` — `uv init --bare` alone does not create it).
- **Add** `uv.lock`, committed, as the single source of truth for exact pins.
- **Recreate** the local environment with `uv sync` (the git-ignored `.venv/`
  is deleted and recreated; uv uses the same `.venv` directory name, so
  `.gitignore` and `.dockerignore` entries are unchanged).
- **Replace** the `Dockerfile` base image `python:3.13-slim` with
  `astral/uv:python3.13-bookworm-slim` and `pip install --no-cache-dir`
  with `uv sync --frozen --no-dev`; the entrypoint becomes
  `uv run --frozen --no-dev python -m app.main`. No `pip` anywhere in the image.
- **Update** `README.md`: development commands become `uv sync` / `uv run ...`,
  and the library-update runbook becomes `uv add
  'youtube-transcript-api==<new-version>' 'yt-dlp==<new-version>'` (exact
  pins preserved) plus committing the refreshed `pyproject.toml`/`uv.lock`
  (the `pip freeze | grep` step disappears).
- **Update** `.dockerignore` (drop the now-deleted `requirements-dev.txt`
  line; ensure `pyproject.toml` and `uv.lock` remain in the build context) and
  the Dockerfile size estimate comment.
- No **BREAKING** changes: same nine direct dependency pins (`uv lock`
  re-resolves transitive versions, which may differ from the current
  `.venv` — see design risks), same app behavior, same port/healthcheck/user
  model, compose file functionally unchanged (one stale base-image comment
  updated).

## Capabilities

### New Capabilities

(none — no new system behavior)

### Modified Capabilities

(none — `structured-logging`, `transcript-retrieval`, and `web-interface`
are unaffected: no spec-level requirement changes. This change opts out of
specs via `skip_specs: true`.)

## Impact

- **Files touched:** `pyproject.toml` (new), `uv.lock` (new, committed),
  `.python-version` (new), `Dockerfile`, `docker-compose.yml` (comment-only),
  `.dockerignore`, `README.md`; deleted: `requirements.txt`,
  `requirements-dev.txt`; local `.venv/` recreated by `uv`.
- **Dependencies:** identical direct pins (transitives re-resolved by
  `uv lock`); the `requests` direct pin (imported by `app/fetchers.py`) moves
  into `[project].dependencies` with its explanatory comment.
- **Build/deploy:** container image base changes (size estimate shifts
  slightly); compose file and healthcheck unchanged.
- **Docs:** README runbook and development sections rewritten for `uv`.
