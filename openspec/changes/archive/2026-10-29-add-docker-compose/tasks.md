# Tasks

## 1. Compose file

- [x] 1.1 Create `docker-compose.yml` with a single `app` service per design.md decisions 1-5 (`build: .`, `image: yt-transcript`, `container_name: yt-transcript`, `restart: unless-stopped`, `ports: ["${PORT:-8000}:8000"]`, python `/`-probing healthcheck with a comment tying the hardcoded `127.0.0.1:8000` to the port-decoupling decision, json-file logging with `max-size: 10m` / `max-file: "3"`); verify with `docker compose config` (resolves and renders the intended file) and confirm no `version:` key, no profiles, no build args
- [x] 1.2 Verify podman parity: run `podman compose config` (or `podman-compose config`) if podman is available on this machine, and note in the README podman section whether compose is supported there; if no podman tooling is present, verify the file contains only the compose v2 keys listed in design.md decision 4 and record that podman-compose compatibility was verified by construction

## 2. .gitignore

- [x] 2.1 Create `.gitignore` with `.env`, `__pycache__/`, `*.pyc`, `.venv/`, `.pytest_cache/`, `*.log`; verify `git status --short` no longer lists `.venv/` or `.pytest_cache/` as untracked, and `git check-ignore -v .env` reports it ignored

## 3. README update

- [x] 3.1 Reorganize the "Build and run" section of `README.md` per proposal.md: compose as the primary path (`docker compose up -d --build`), document the optional uncommitted `.env` with `PORT=9000` (host port only; container stays 8000), demote the existing raw docker/podman two-liner to a "without compose" subsection, replace the stop/remove note with `docker compose down`, and add a one-line note that the container reports healthy via `docker compose ps` after startup; verify by re-reading the final section and confirming every documented command uses only files that exist in the repo

## 4. Integration verification

- [x] 4.1 Run the full compose smoke test: `docker compose up -d --build` (removing any pre-existing `yt-transcript` container first, per design.md Migration Plan), then verify `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/` returns 200, `docker compose ps` shows the container healthy, and `docker logs yt-transcript` shows the `server_started` JSON line; then confirm stop with `docker compose down` leaves no container behind
- [x] 4.2 Verify the `.env` port override: with `.env` containing `PORT=9000`, run `docker compose up -d` and verify the app answers on `http://127.0.0.1:9000/` while `docker logs yt-transcript` shows `server_started` with `port: 8000` (host-side decoupling per design.md decision 1); clean up with `docker compose down` and remove the temporary `.env`

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Verify the archived result.
