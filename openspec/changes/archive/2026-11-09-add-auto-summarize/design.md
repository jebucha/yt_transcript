# Design

## Context

See `proposal.md` — Why. The summarization stack is shipped and settled: `app/providers.py` reads provider config per request (pure, FastAPI-free); `app/persist.py` resolves `TRANSCRIPT_DIR` at call time and writes best-effort, never creating the directory; `app/summarize.py` + `POST /api/summarize` own the backend call, the `.summary` write, and the 2-slot backend bound; the vanilla-JS UI (`app/static/app.js`) already tracks `currentTranscript` / `currentTranscriptName`, a monotonic `displayToken` (late responses must not paint a stale transcript), a `summarizing` in-flight guard, and a `loadProviders()` result carrying `defaultProviderId` with the picker pre-selecting the default provider's first model. Constraints: no blocking I/O on the event loop (all filesystem work via `asyncio.to_thread`); the single-flight semaphore governs only the fetch chain; DOM writes via `textContent` only; `providers.json` is mounted read-only in compose.

## Goals / Non-Goals

**Goals:**
- One durable boolean (`autoSummarize`) shared across browsers and rebuilds, with a safe off-default.
- Auto-summarize reuses the manual summarize path end-to-end — endpoints, guards, persistence, concurrency bound — so there is exactly one summarize code path in the UI.
- Zero changes to compose, Dockerfile, dependencies, and to every manual-flow behavior.

**Non-Goals:**
- Per-user or per-browser preference segregation (the setting is app-global).
- Auto-summarization of saved-transcript clicks, batch re-summarization, or a general settings framework beyond the one boolean (the endpoints may grow fields later; nothing is designed ahead of need).
- Cancelling an in-flight summarize when the user moves on (the existing `displayToken` staleness guard governs).

## Decisions

### D1 — Browser-triggered auto-fire, not server-side in the fetch chain
The UI fires `POST /api/summarize` itself after a successful fetch. Alternative considered: the fetch endpoint summarizes before responding. Rejected — the shipped spec makes "summarize must not touch the fetch chain" an explicit, tested invariant (T-TRANSCRIPT-SUMMARIZATION-017), it would slow every fetch, and it would burn tokens on throwaway fetches with no way to opt out per-request.

### D2 — Settings live in `<TRANSCRIPT_DIR>/settings.json`, not localStorage or providers.json
- `localStorage`: rejected — per-browser, lost on profile clear or a different device; the deployment is a container whose durable state is the host-mounted `/transcripts` volume (`/home/john/transcripts` on the host), so a file there survives rebuilds and is shared by every browser.
- `providers.json`: rejected — mounted `:ro` (the app must never write it), and its contract is provider config only; the proposal's settings surface needs writes.
- `settings.json` in the transcript directory is invisible to `GET /api/transcripts` by construction (list filters to `.txt`). No compose change: the volume is already writable.

### D3 — New `app/settings.py`, endpoints follow the existing thin-wrapper pattern
Pure, FastAPI-free module (mirroring `providers.py`): `settings_path()` resolving `TRANSCRIPT_DIR` at call time via `persist.transcript_dir()`, `load_settings()` reading per request (missing → default-off without logging; unreadable/malformed → one `settings_load_failed` error event with path + parse detail, never file contents; non-boolean flag → false), and `save_settings()` returning a success flag. `main.py` adds `GET /api/settings` (200 `{"autoSummarize": bool}`) and `POST /api/settings` (validate body first — non-object, missing, or non-boolean `autoSummarize` → 400 `INVALID_BODY`, no filesystem access; write via `asyncio.to_thread`; failure → 500 `WRITE_FAILED` + `settings_save_failed` log event; success → 200 echo). Neither endpoint touches the semaphore or the fetch chain. Writes use a sibling temp file + `os.replace` so a crash mid-write cannot leave a truncated settings file (reads stay simple; alternative: plain overwrite as `save_summary` does, rejected because settings have an atomically meaningful all-or-nothing reading that a half-written JSON breaks).

### D4 — Auto target = the picker's pre-selected default, via one shared helper
The picker already computes `providerOptions[selectedIndex]` where `selectedIndex` is the default provider's first model. Auto-summarize calls the same computation (extract a small `defaultSelection()` helper). Rejected: "remember the model the user last picked manually" — it couples two independent user decisions and makes the auto behavior non-reproducible across sessions.

### D5 — Auto-fire is `doSummarize` with an `auto` flag, hooked after `renderResult`
`doSummarize(auto)` keeps one code path: same busy state (button, picker, and now the checkbox disabled + spinner), same `summarizing` guard, same response handling, same `displayToken` staleness rule. The hook runs only in the fetch-success path (`renderResult`), never in `displaySavedTranscript`. Before firing, the auto path checks for an existing summary by attempting the same `GET /api/transcripts/{name}/summary` read that saved clicks already use: 200-with-text → show it (skip-and-show, no summarize call); anything else → fire. This reuses `loadSavedSummary` rather than adding a new existence endpoint; the panel is already cleared by `renderResult` first, so the "new transcript clears the summary" requirement still holds (what may appear is the *new* transcript's own summary).

### D6 — Failures: subdued note for auto, banner untouched; checkbox reverts on settings-write failure
A note element (hidden by default, muted style, `textContent` only) sits next to the summarize controls. The auto path shows it for every failure shape — `PROVIDER_ERROR`, `NOT_CONFIGURED`, `INVALID_PROVIDER`, `INPUT_TOO_LONG`, network error, empty-`summary` 200 — and never calls `showError`; the manual path keeps the existing banner behavior untouched. On a failed `POST /api/settings` (500/network), the checkbox reverts to the last known persisted value so the UI never claims a state the server does not hold. Rationale: unasked-for red-banner errors on every over-long or provider-down fetch are exactly the annoyance that would make the toggle unusable; the note keeps the retry affordance (an enabled manual Summarize button) visible.

### D7 — Consecutive-fetch race: first fetch wins, second auto-fire is dropped (documented)
If fetch B starts while auto-A is in flight, B's auto-fire is dropped by the `summarizing` guard, and A's late response is discarded by `displayToken` — so B ends up with no auto-summary. Accepted: queueing/re-firing adds state for a rare self-inflicted race in a single-user tool, and the user can always click Summarize. Recorded here so validate/apply does not "fix" it.

## Risks / Trade-offs

- [Re-fetched video shows a stale saved summary under skip-and-show] → Deliberate (decision record): showing the existing summary beats silence; the manual button re-summarizes and overwrites on demand.
- [Transcript directory missing/read-only → toggle silently never persists] → `POST` returns 500 `WRITE_FAILED`, the checkbox reverts (D6), and `settings_save_failed` makes it diagnosable in the log viewer; mirrors the accepted summary-save trade-off.
- [Auto-fire with stale picker state (providers edited mid-session)] → Server re-validates provider/model per request (existing `INVALID_PROVIDER` taxonomy); the auto path surfaces it as the subdued note, and a page reload refreshes the picker.
- [Note element and banner could both show] → The auto path clears neither user-visible error surface the other owns; the note is only shown by auto calls and cleared by any new fetch/click, the banner only by manual calls — e2e scenario T-...-052/054 pins the split.
- [e2e timing flake: auto-fire races the fetch render] → Tests await the stubbed summarize request (same pattern as `test_summarize_sends_displayed_transcript`), never fixed sleeps.

## Migration Plan

Backward compatible: no existing endpoint changes, no data migration (a missing `settings.json` is simply "off"), no compose edits. Deploy = rebuild the image. Rollback = older image; a leftover `settings.json` is inert for old code (unknown file in the transcripts directory, invisible to the `.txt` list). Per repo workflow, bump the minor version (`uv version --bump minor`) before archive since this ships user-visible changes.

## Open Questions

None blocking. (Note styling specifics — muted color, wording — are implementation-time choices with no spec surface.)
