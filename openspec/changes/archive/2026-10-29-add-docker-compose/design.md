# Design

## Context

See proposal.md for motivation. Current state that shapes the approach:

- One stateless service; the `Dockerfile` already handles base image,
  dependency install, unprivileged user, `EXPOSE 8000`, and
  `CMD ["python", "-m", "app.main"]`.
- The app's entire runtime config surface is two env vars: `PORT`
  (default 8000, used by `app/main.py`) and `HOST` (default 0.0.0.0).
- No health endpoint exists — routes are `/` (static UI, 200) and
  `POST /api/transcript` only.
- The image is `python:3.13-slim`: no curl or other probe binary, but
  python is obviously present.
- The project promises podman parity (README documents podman commands
  everywhere); compose usage must stay within what podman compose /
  podman-compose support.
- The repo has no `.gitignore` and no commits yet.
- The app's single-flight semaphore means the design assumes exactly one
  instance — scaling is not a goal.

## Goals / Non-Goals

**Goals:**
- One-command deployment (`docker compose up -d --build`) that is fully
  declarative: name, restart policy, port mapping.
- Express healthcheck and container log rotation declaratively.
- Keep the raw `docker run` / `podman run` path fully functional as a
  fallback for hosts without a compose tool.
- Keep podman parity for the compose path.

**Non-Goals:**
- No HTTPS / reverse proxy (a separate future change).
- No new app endpoints (no `/health`), no Dockerfile changes, no app code
  changes.
- No multi-instance / scaling configuration.
- No dev-mode profiles, bind mounts, or in-container test runners.

## Decisions

1. **Decouple host port from container port (host-side mapping only).**
   The compose file maps `"${PORT:-8000}:8000"` and does not inject `PORT`
   into the container. The container always binds 8000, matching `EXPOSE`.
   Alternative considered: mirroring the README's existing behavior by
   injecting `PORT` into the container and mapping
   `"${PORT:-8000}:${PORT:-8000}"` — rejected because it couples two
   variables that must always agree and makes the logged
   `server_started port=` line ambiguous (which side is it?). The app's
   `PORT` env var remains available for non-compose runs, so nothing is
   lost. Consequence: the healthcheck can hardcode the container-side
   address (see decision 2).

2. **Healthcheck probes `/` with python, not a new endpoint or curl.**
   `test: ["CMD", "python", "-c", "import urllib.request;
   urllib.request.urlopen('http://127.0.0.1:8000/')"]`. `urlopen` raises
   on any 4xx/5xx, so a degraded app fails the probe. Alternatives:
   adding a `/health` endpoint — rejected (app change, out of scope);
   `curl` — not in the slim image, and installing it just for probing
   bloats a ~150 MB image. Timings: interval 30s, timeout 5s, retries 3,
   start_period 5s (the app starts in well under a second). The
   hardcoded `127.0.0.1:8000` is correct *because of* decision 1; the
   compose file carries a comment tying the two together so a future
   port re-coupling does not silently break the probe.

3. **Log rotation via json-file driver options.**
   `logging: {driver: json-file, options: {max-size: "10m", max-file: "3"}}`
   — worst case ~30 MB of logs retained per container. Rationale: the
   structured logger emits one JSON line per HTTP request and per fetch
   attempt (see `structured-logging` spec), and the driver default does
   not rotate, so on an unattended VPS the log would grow without bound.
   10m/3 is the common small-service default; large transcript payloads
   are not included in log lines (only character counts), so 10 MB
   represents a long window of requests.

4. **Filename `docker-compose.yml`, plain compose v2, no version key.**
   Both Docker Compose v2 and podman-compose auto-detect this name
   (podman-compose defaults to it); `compose.yaml` is the newer Docker
   docs convention but less compatible on the podman side. No `version:`
   key (obsolete in v2). No profiles, build args, extends, or other
   advanced keys — deliberately staying inside podman-compose's supported
   subset.

5. **Fixed `container_name: yt-transcript`.**
   Matches the README's existing `--name yt-transcript`, keeps the smoke
   test (`docker logs yt-transcript`) working unchanged, and enforces the
   single-instance assumption. Trade-off: two compose projects on one
   host cannot coexist — acceptable for a single-user self-hosted tool.

6. **`.gitignore` ships with this change.**
   The compose workflow encourages a machine-local `.env` (for the `PORT`
   override); without a `.gitignore`, `git add -A` would commit it. The
   repo is pre-first-commit, so this is the natural moment. Minimal
   content: `.env`, `__pycache__/`, `*.pyc`, `.venv/`, `.pytest_cache/`,
   `*.log`. No `.env.example` — a single documented variable does not
   warrant an example file; the README documents `PORT` instead.

## Risks / Trade-offs

- [Healthcheck semantics are "web server responds," not "fetch chain
  works"] → Accepted: with no `/health` endpoint, that is the strongest
  honest signal a stateless single-process service can give; the
  fetch-chain health shows up in the structured `fetch_attempt` logs.
- [Healthcheck hardcodes the container port] → Mitigated by an in-file
  comment linking the probe to decision 1.
- [podman-compose support for `healthcheck`/`logging` varies by version]
  → Mitigated by keeping the raw `docker run` / `podman run` path
  documented; worst case an older podman-compose ignores or errors on one
  key and the user falls back.
- [Log files are lost on container recreation (no volume)] → Accepted:
  matches current `docker run` behavior; persisting logs to a named
  volume is a possible follow-up, out of scope here.

## Migration Plan

No state, no data, no running-config migration:

1. Add `docker-compose.yml` and `.gitignore`; update the README.
2. Operators can switch at their convenience:
   `docker compose up -d --build` (the fixed container name means the
   first compose run recreates an existing `docker run`-created container
   of the same name cleanly — remove it first with
   `docker rm -f yt-transcript` if present).
3. Rollback: `docker compose down`, delete the compose file, use the
   documented raw commands (unchanged).
