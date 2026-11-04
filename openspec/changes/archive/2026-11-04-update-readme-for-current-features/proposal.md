# Proposal

## Why

Three recent feature commits updated the app but left the README behind. The
in-browser log viewer (commit 40a457a) — a headline user-facing feature with a
`Show logs` button, an SSE log stream, and its own spec — is not mentioned
anywhere in the README. The change that made saved `.txt` files start with the
video's watch URL (commit 4ab439f) is not reflected in the "Transcript
storage" description, so anyone reading a saved or downloaded file sees
unexpected content. And the Layout section has not been touched since the
initial commit: it is missing `persist.py`, `library.py`, and `logbus.py`.
Recent feature commits updated the README's behavior sections in-commit but
skipped these spots, and others left the README untouched entirely, so the
drift concentrates and grows with each feature.

## What Changes

All changes are to `README.md` (docs-only; no code, config, or test changes):

- **Document the in-browser log viewer**: the **Show logs** button in the
  page header toggles a live log panel fed by `GET /api/logs` (server-sent
  events: up to the 200 most recent entries replayed on connect, then live
  streaming; the panel displays the 200 most recent lines). Add a sentence to
  the Logging bullet noting the viewer alongside `docker logs` / `podman
  logs`, and mention the button in the usage paragraph.
- **Describe the saved-file format accurately**: each saved `.txt` now begins
  with the video's watch URL (`https://www.youtube.com/watch?v=<video_id>`) as
  its first line, followed by the transcript and a trailing newline. Update
  the "Transcript storage" paragraph accordingly.
- **Add a smoke-test step** verifying the log stream: a `curl` against
  `GET /api/logs` (SSE) or a note that the **Show logs** button streams log
  lines live.
- **Fix the Layout section**: add the three missing modules — `persist.py`
  (title-to-file-name derivation + best-effort writer), `library.py`
  (read-side: list and read persisted transcripts), `logbus.py` (in-memory
  ring buffer backing the SSE log viewer) — and adjust the `main.py` line to
  reflect that it now hosts multiple API endpoints.
- **Minor**: extend the Error-model bullet with the two read-endpoint codes
  added by the saved-transcript list (`INVALID_NAME` 400, `NOT_FOUND` 404).

Out of scope: no behavior changes; adding a standing "keep Layout current"
rule to `AGENTS.md` (possible follow-up, separate change); any rewrite beyond
the drift identified above.

## Capabilities

### New Capabilities

None — no new system behavior is introduced.

### Modified Capabilities

None — no spec-level requirement changes. The behavior of `log-viewer`,
`transcript-persistence`, `transcript-library`, and the other capabilities
remains exactly as specified; only their README documentation is corrected.
This change opts out of specs via `skip_specs: true`.

## Impact

- **Files:** `README.md` only.
- **Code / API / dependencies:** none.
- **Version:** no bump — a documentation correction ships no user-visible
  app change.
