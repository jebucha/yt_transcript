# Design

## Context

See proposal.md - Why for motivation. This is a documentation-only change: all
edits go to `README.md` and no code, config, or tests change. The sections to
fix (Logging, usage, Transcript storage, Error-model, Layout, smoke test)
currently describe behavior that predates three implemented features, and
every fact to be added is already implemented in `app/` and specified under
`openspec/specs/`.

## Goals / Non-Goals

**Goals:**
- Bring the five drifted README areas in line with the code and the
  capability specs as of HEAD.
- Make every added claim traceable to a concrete source: `app/logbus.py`,
  `app/static/app.js`, `app/persist.py`, `app/main.py`, or a spec under
  `openspec/specs/`.

**Non-Goals:**
- No behavior, API, or dependency changes; no version bump.
- No README rewrite beyond the identified drift.
- No standing "keep Layout current" rule (possible follow-up, separate
  change).

## Decisions

- **Verify every added claim against code and specs before writing it.** Each
  task (1.1–3.1) names the source to check, and tasks 4.1/4.2 re-verify the
  whole README — smoke-test commands run against a locally running app, text
  re-read top to bottom. Alternative considered: rewriting the README from a
  general feature list — rejected because it risks introducing new unverified
  claims.
- **Keep edits additive and section-local.** Each "What Changes" bullet maps
  to one README section, so the diff stays reviewable. Alternative: a full
  README refresh — rejected as out of scope per the proposal.
- **Present the in-browser viewer as a second surface alongside
  `docker logs` / `podman logs`**, since both consume the same log stream —
  the viewer complements rather than replaces the container logs.

## Risks / Trade-offs

- [A verified detail drifts again after this change] → Drift prevention is
  out of scope (possible follow-up change); tasks 4.1/4.2 re-verify the full
  README before archiving.
- [The new smoke-test step proves unstable or environment-dependent] → Keep
  it minimal (`curl -N` showing SSE `data:` lines) and verify it as written
  against a locally running app before finalizing (task 1.2).

## Test Strategy

Docs-only change, so no new executable tests. Verification is per-task,
against code and specs: each task states the exact source to check
(`app/logbus.py`, `app/static/app.js`, `app/persist.py`, `app/main.py`,
`openspec/specs/log-viewer/spec.md`); task 4.1 runs every README smoke-test
command, including the new log-stream step, against `uv run python -m
app.main`; task 4.2 re-reads the final README top to bottom to confirm no
claim references removed behavior and no module under `app/` is missing from
Layout.

## Migration Plan

Nothing to deploy: a single `README.md` edit. Rollback is reverting the
commit — no data, API, or deployment surface is touched.
