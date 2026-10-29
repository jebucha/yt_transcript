# Proposal

## Why

Deployment today is two shell commands (build + run) scattered in the README,
with no declarative home for the container's name, restart policy, port
mapping, or the ops hygiene a long-running unattended service needs. A
`docker-compose.yml` makes `docker compose up -d --build` the one-command
deployment path and lets the file express two things plain `docker run`
cannot: a healthcheck and container log rotation (the structured JSON
logger emits one line per request and per fetch attempt, and the default
json-file driver does not rotate).

## What Changes

- Add `docker-compose.yml`: a single `app` service wrapping the existing
  `Dockerfile` unchanged (same build context, `image: yt-transcript`,
  `container_name: yt-transcript`, `restart: unless-stopped`).
  - Host port mapping `"${PORT:-8000}:8000"` — the host port is overridable
    via an uncommitted `.env` file; the container always binds 8000.
  - Healthcheck: python probes `/` inside the container (no curl in the
    slim image; no new app endpoint).
  - Logging: json-file driver with `max-size`/`max-file` rotation.
  - File stays plain compose v2 (no profiles, build args, or exotic keys)
    so `podman compose` / podman-compose remain supported, matching the
    project's podman-parity stance.
- `README.md`: compose becomes the primary deployment path; the raw
  docker/podman two-liner is demoted to a "without compose" alternative;
  stop/remove becomes `docker compose down`; document the optional `.env`
  `PORT` override.
- Add `.gitignore` (repo currently has none): at minimum `.env`, plus
  `__pycache__/`, `*.pyc`, `.venv/`, `.pytest_cache/`, `*.log`. Protects the
  machine-local `.env` from accidental commit.
- No changes to `Dockerfile`, app code, or runtime behavior. No **BREAKING**
  changes; the existing raw `docker run` path keeps working.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This change is pure deployment tooling and documentation; no
spec-level behavior changes, so the change opts out of specs
(`skip_specs: true`).

## Impact

- New files: `docker-compose.yml`, `.gitignore`.
- Modified: `README.md` (deployment section reorganization only).
- Unaffected: `Dockerfile`, `app/`, `tests/`, existing specs
  (`structured-logging`, `transcript-retrieval`, `web-interface`).
- Operational: `docker compose down` replaces `docker stop/rm` for the
  compose-managed container (identical container name, so either works
  during the transition).
