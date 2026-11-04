# Tasks

## 1. Log viewer documentation

- [x] 1.1 Add a sentence to the Logging bullet noting the in-browser viewer as a second surface alongside `docker logs` / `podman logs` (the **Show logs** button opens a live log panel; up to the 200 most recent entries are replayed on connect, then streamed live), and mention the button in the usage paragraph; verify every stated detail against `openspec/specs/log-viewer/spec.md`, `app/logbus.py`, and `app/static/app.js` (replay cap 200, display cap 200 lines, `GET /api/logs`)
- [x] 1.2 Add a smoke-test step for the log stream (e.g. `curl -N http://127.0.0.1:8000/api/logs` showing SSE `data:` lines, or a note that the **Show logs** button streams lines live); verify the documented command works as written against a locally running app (`uv run python -m app.main`)

## 2. Saved-file format and error-model accuracy

- [x] 2.1 Update the "Transcript storage" paragraph to state that each saved `.txt` begins with the video's watch URL (`https://www.youtube.com/watch?v=<video_id>`) as its first line, followed by the transcript and a single trailing newline; verify the wording matches `save_transcript` in `app/persist.py`
- [x] 2.2 Extend the Error-model bullet with the read-endpoint codes `INVALID_NAME` 400 and `NOT_FOUND` 404; verify the codes and statuses match the `/api/transcripts/{name}` handler in `app/main.py`

## 3. Layout section

- [x] 3.1 Add the missing modules to the Layout block — `persist.py` (title-to-file-name derivation + best-effort writer), `library.py` (read-side list/read of persisted transcripts), `logbus.py` (in-memory ring buffer backing the SSE log viewer) — and adjust the `main.py` line to reflect that it hosts multiple API endpoints; verify the block matches the actual contents of `app/`

## 4. Full-README re-verification

- [x] 4.1 Start the app locally (`uv run python -m app.main`) and re-run every command in the README smoke test, including the new log-stream step; verify each documented response/event matches actual output
- [x] 4.2 Re-read the final README top to bottom and check every feature claim against the code or the relevant spec under `openspec/specs/`; verify no claim references removed behavior (e.g. "zero state") and that no new module under `app/` is missing from Layout

## Workflow follow-up

- No version bump required: the change ships documentation only.
- Archive the change after the project's review requirements are satisfied (per `AGENTS.md`: validate in a fresh session with a model that did not write the change).
