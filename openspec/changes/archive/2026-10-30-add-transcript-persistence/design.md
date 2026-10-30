# Design

## Context

The transcript endpoint (`app/main.py`) awaits `chain_mod.default_chain.run(url)` and returns the `FetchResult` as JSON. All blocking I/O in this codebase already runs through `asyncio.to_thread`; config is read from the environment at call time (see `_listen_port`); compose already supports `.env`-based overrides (`${PORT:-8000}`) while staying inside the key set that podman-compose accepts. The container runs as the unprivileged `appuser` and today writes no persistent state to disk (only short-lived temp files while fetching) — a bind-mounted directory changes that. Requirements live in the `transcript-persistence` and `structured-logging` deltas; this document covers how.

## Goals / Non-Goals

**Goals:**
- Persist every successful fetch to a plain-text file named after the title, best-effort, without changing the API response, the UI, the error taxonomy, or the fetch chain.
- Keep the title-to-file-name rule a pure, exhaustively unit-testable function.
- Stay testable outside Docker: tests point the transcript directory at a temporary path.

**Non-Goals:**
- Disambiguating distinct videos with identical titles (last write wins, per spec).
- Atomic file replacement (temp file + rename) — see decision 5.
- Auto-creating the transcript directory, serving saved files over HTTP, retention/GC, or any storage beyond flat files.

## Decisions

### 1. Hook point: the endpoint, after a successful fetch
The write happens in `transcript_endpoint` after `chain.run` returns, before the JSON response is built. Alternatives considered:
- *Inside `FetchChain.run`* — rejected: the chain is about fetching (single-flight semaphore, attempt logging) and is unit-tested purely on fetch semantics; adding disk I/O would entangle two concerns and complicate its tests.
- *FastAPI middleware / dependency* — rejected: no existing lifecycle hook maps to "fetch succeeded with a title."

Placing it in the endpoint also makes "failed fetch writes nothing" trivially true — the write is simply unreachable after a `TranscriptError`.

### 2. New module `app/persist.py`, pure derivation + writer
- `derive_file_name(title: str, video_id: str) -> str` — pure, no I/O, returns the full file name including `.txt`.
- `save_transcript(text, title, video_id) -> str | None` (working signature) — resolves the directory, derives the name, writes, and returns the path written; never raises to the caller (best-effort, decision 4).
- No FastAPI imports, so the derivation function is unit-testable directly and the writer is testable against `tmp_path`.
- Alternative: put both in `main.py` — rejected: the derivation rules are the richest test surface of the change and deserve their own home and `tests/test_persistence.py`; `fetchers.py` is out because it is about fetching, not storage.

### 3. Name derivation algorithm
1. Lowercase (Unicode-aware).
2. Keep Unicode letters and digits; replace every other character (punctuation, whitespace, symbols — including `/`, so output is inherently path-safe) in runs of one or more with a single `_`.
3. Trim leading/trailing `_`.
4. If empty → use `video_id`.
5. If the resulting name (with `.txt`) exceeds 255 bytes → truncate the title portion on a character boundary (never mid-codepoint), append `_<video_id>`, and truncate again so the whole name fits 255 bytes.
6. Result always gets `.txt`.

The video-ID suffix is applied *only when truncation happens*, so ordinary names match the agreed convention exactly (`The End of LLMs? (NCM)` → `the_end_of_llms_ncm.txt`) while overlong and colliding-truncated names stay unique.

### 4. Best-effort write with structured logging
`save_transcript` catches any write error (`except Exception`, covering missing directory, permissions, disk full, and encoding failures) and logs `transcript_save_failed` (error level, video ID + reason); on success it logs `transcript_saved` (info level, video ID, path, byte count) via the existing `get_logger()`. It never re-raises, so the response is built exactly as before. This implements the best-effort requirement; the log field names follow the `structured-logging` delta.
- Alternative: fail the request with a new error code — rejected explicitly during exploration; "displays as it does now, but also writes" makes persistence a side effect, and a new error code would ripple into the UI error display.

### 5. Write mechanics: synchronous file write in a worker thread, plain overwrite
The write runs via `asyncio.to_thread`, matching the codebase's pattern of never doing blocking I/O on the event loop (fetches do the same). Files are small (KB to low MB), so the cost is negligible either way.
The file is written with `open(path, "w", encoding="utf-8")` — plain overwrite, no temp-file + `os.rename`. A crash mid-write could in theory leave a partial file, but a re-fetch of the same video rewrites identical bytes, and the project's own design docs value staying minimal. Concurrency is a non-issue: the single-flight semaphore ensures at most one fetch runs at a time. Two requests for the *same* video could in theory interleave (one write still in flight while a second fetch for that video completes), but both write the same transcript bytes for that video, and the accepted last-write-wins/plain-overwrite semantics make the overlap harmless.

### 6. Configuration
- `TRANSCRIPT_DIR` environment variable, default `/transcripts`, read at write time through a small module-level helper — the same pattern as `_listen_port()` reading `PORT` at call time. Tests use pytest's `monkeypatch` to point it at a temporary directory, consistent with how the app is already exercised in tests.
- `Dockerfile`: add `TRANSCRIPT_DIR=/transcripts` to the existing `ENV` block.
- `docker-compose.yml`: `volumes: - "${TRANSCRIPTS_DIR:-/home/john/transcripts}:/transcripts"` — mirrors the `${PORT:-8000}` override convention and adds only a plain `volumes` list, keeping podman-compose compatibility (no new key constructs).
- The directory is deliberately *not* created by the app or the Dockerfile: a bind mount is shadowed by host ownership, and a root-owned container-side directory would be a permissions trap. A missing directory degrades to the logged best-effort failure.

### 7. Deployment documentation
README updates: the "zero state, no database" line becomes "state: one plain-text file per fetched transcript on a bind-mounted directory"; the compose section documents the mount and the `TRANSCRIPTS_DIR` override; a permissions note for native Linux (container runs as `appuser`; host dir owned by the operator's uid → `chown`/`chmod` on `/home/john/transcripts` if writes fail). Docker Desktop bind mounts are permissive, so this is a Linux-server footnote, not a blocker.

## Test Strategy

All persistence logic lives in `app/persist.py` with no FastAPI imports, so it is exercised directly:
- **Unit** — `tests/test_persistence.py` covers `derive_file_name` (the pure derivation rules) and `save_transcript` (write + best-effort + logging) against pytest's `tmp_path`; the `TRANSCRIPT_DIR` helper is pointed at a temporary directory via `monkeypatch`.
- **API-level** — the endpoint write path (write-on-success, no-write-on-failure, overwrite, directory-from-env) reuses the project's existing chain-mocking pattern (`tests/test_api.py`: `FakeChain` + `monkeypatch.setattr(chain_mod, "default_chain", ...)`).
- **Run** — `uv run python -m pytest tests/ -q --ignore=tests/e2e` for the unit/API/logging suites, and `uv run python -m pytest tests/e2e/ -q` for the end-to-end UI check. Each spec scenario maps to a named test via its Test Requirement block.

## Risks / Trade-offs

- [Bind-mount ownership on native Linux denies writes] → best-effort design makes this a logged `transcript_save_failed`, never a broken app; README documents the `chown`/`chmod` fix. (Also why the app must not own creating the directory — decision 6.)
- [Identical titles for different videos silently overwrite] → accepted per exploration (last write wins is spec'd); the truncation path already disambiguates with the video ID, so only genuinely short identical titles collide.
- [Partial file after a crash mid-write] → accepted; plain overwrite per decision 5, re-fetch repairs.
- [Missing/unwritable directory produces one error log per successful request] → accepted; it is the operator's signal that the mount needs fixing, and log rotation (10 MB × 3) bounds it.
- [255-byte limit is filesystem-specific] → the hard limit is Linux/ext4's, which is the deployment target; truncation on other filesystems is simply never triggered.

## Migration Plan

Purely additive; no data migration. `docker compose up -d --build` with the updated compose file; create the host directory first (`mkdir -p /home/john/transcripts`) — or let Docker create it and apply the permissions note. Rollback: revert the commit and `docker compose down && up -d`; any files already written remain on the host, untouched.

## Open Questions

None — the blocking decision (best-effort vs. gated response) was resolved during exploration in favor of best-effort.
