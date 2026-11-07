# `docker-compose.yml` — declarative single-service deployment

## Purpose

The Compose file that turns a local or VPS checkout into a running yt-transcript
instance in one command (`docker compose up -d --build`). Single service, no
profiles, no build args — deliberately scoped to the subset supported by both
Docker Compose v2 and podman-compose for parity.

## Public surface

- **Service name:** `app` (the only service)
- **Container image:** `yt-transcript` (built from `./`)
- **Container name:** `yt-transcript` (fixed, matches non-compose usage)
- **Host-side knobs** (via uncommitted `.env` file):

  | Variable | Default | Maps to | Notes |
  |----------|---------|---------|-------|
  | `PORT` | `8000` | Port mapping `${PORT:-8000}:8000` | Host port only; container always listens on 8000 |
  | `TRANSCRIPTS_DIR` | `/home/john/transcripts` | Volume mount `${...}:/transcripts` | Writable host directory; app never creates it |
  | `PROVIDERS_CONFIG` | `./providers.json` | Read-only volume `${...}:/app/providers.json:ro` | JSON config file kept out of git |

- **Healthcheck:** python urllib probe against `http://127.0.0.1:8000/`
  - interval 30s, timeout 5s, retries 3, start_period 5s
- **Log rotation:** json-file driver, max-size 10m, max-file 3 (max ~30 MB)

## Invariants

- **Host/container port decoupling.** The container always binds 8000 regardless
  of `PORT`. This keeps the healthcheck simple (hardcoded to 8000) and prevents
  a mismatch between mapped host port and logged `server_started` port.
- **Container-side paths are fixed.** `/transcripts`, `/app/providers.json` —
  only the host side is overridable via `.env`. A future change that remaps
  container paths must update both the volume mount *and* healthcheck address.
- **`.env` never committed.** It contains machine-local overrides; tracked in
  `.gitignore` (`.env`).
- **Single-instance only.** The fixed `container_name: yt-transcript` means two
  compose projects on one host cannot coexist — acceptable for a single-user
  self-hosted tool.
- **Read-only config mount.** `/app/providers.json` is mounted `ro`; the app's
  per-request config read never modifies it.

## Log events emitted

N/A — this file emits nothing. However, it controls operational behavior:
- Healthcheck failures surface as container restarts (3 retries then down)
- Log rotation limits how much structured log data accumulates (~30 MB max)
- The healthcheck probe (`/`) returns 200 when the static UI is served — this
  confirms the app process is alive but does *not* verify the fetch chain works

## Error codes raised/handled

Failure modes and their observable effects:
- **Port conflict on host** (EADDRINUSE) — compose logs show bind failure; fix by
  changing `PORT` in `.env` or killing the conflicting process
- **Missing TRANSCRIPTS_DIR** on host — container starts but transcript saves fail
  silently with a `config_load_failed` event logged by the app (best-effort behavior)
- **Missing or invalid providers.json** — app emits `config_load_failed`; summarization
  endpoints return `NOT_CONFIGURED`; UI provider picker remains empty; fetch still works

## Design decisions

Resolved from `2026-10-29-add-docker-compose`:
- **decision 1** — host/container port decoupling (`${PORT:-8000}:8000`); keeps healthcheck address hardcoded and unambiguous
- **decision 2** — python urllib probe instead of curl (no curl in slim image) or new `/health` endpoint (out of scope for a compose-only change)
- **decision 3** — json-file log rotation (10m × 3); prevents unbounded VPS disk growth from structured JSON log lines
- **decision 4** — plain compose v2, no `version:` key; filename chosen for podman-compose compatibility over the newer `compose.yaml` convention
- **decision 5** — fixed container name for single-instance assumption and smoke-test parity with documented `docker run` usage

Also from later changes:
- `add-transcript-summary` — provider config mount path `/app/providers.json` aligns with the app's runtime default; summary provider listing endpoint is secret-free (no keys exposed via compose)

## Cross-links

- [`Dockerfile`](Dockerfile.html) — builds this image (`build: .`)
- [`providers.json.example`](../providers-json-example.html) — config file shape for the mounted volume
- [`app/providers.py`](../providers.html) — reads `PROVIDERS_CONFIG` per request inside the container
- README.md → Deployment section (quick start, podman commands)
