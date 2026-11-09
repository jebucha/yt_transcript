# Proposal

## Why

Summarizing a freshly fetched transcript is always a manual second step: pick a provider/model and click Summarize. For the common case — "always summarize with my default provider" — this is friction, and transcripts fetched with the intent to summarize often never get one. An opt-in auto-summarize toggle makes the default path hands-off while leaving the manual flow untouched.

## What Changes

- A UI checkbox ("Auto-summarize") next to the provider picker. When enabled, every successful fresh fetch automatically summarizes the displayed transcript against the default provider's first model (the same target the picker pre-selects) by calling the existing `POST /api/summarize`.
- Auto-summarize never fires when a `<name>.summary` file already exists for the fetched transcript; in that case the existing saved summary is loaded and shown in the summary panel instead.
- Auto-summarize never fires for saved-transcript clicks (only for fresh fetches).
- Auto-summarization failures never use the red error banner: a subdued inline note appears near the summarize controls, and the manual Summarize button remains the explicit retry path.
- New `GET /api/settings` / `POST /api/settings` endpoints persisting a small JSON settings file (`settings.json`) in the transcript directory, holding the `autoSummarize` flag. A missing file means the flag is off. The file lives in the already host-mounted, writable transcript volume, so the toggle survives container rebuilds and is shared across browsers; compose needs no change.
- Manual summarization, the provider picker semantics, the backend error taxonomy, the `.summary` persistence, and the 2-slot summarize concurrency bound are unchanged.

## Capabilities

### New Capabilities
- `app-settings`: durable application-level UI preferences persisted server-side in the transcript directory, exposed through a read endpoint and a write endpoint, with a defined default when the settings file is absent or unusable.

### Modified Capabilities
- `transcript-summarization`: new auto-summarization behavior (toggle visibility/state, auto-fire on fresh fetch against the default target, skip-and-show when a saved summary exists, subdued non-banner failure indication) and a change to the summary panel requirement so a freshly fetched transcript loads its existing saved summary when auto-summarize is on and a summary exists.

## Impact

- `app/main.py`: two new endpoints (`GET /api/settings`, `POST /api/settings`); `settings.json` is invisible to `GET /api/transcripts` by construction (list is `.txt`-only).
- New settings persistence module (mirrors the per-request read / best-effort write patterns of `app/providers.py` and `app/persist.py`); filesystem work via `asyncio.to_thread`.
- `app/static/app.js` / `index.html` / `style.css`: checkbox control, settings load on page load, auto-fire hook in the fetch-success path, skip-and-show load, subdued note element.
- Tests: API tests for the settings endpoints, e2e tests for the auto-summarize flows (Playwright, matching the existing summarization e2e suite).
- No compose, Dockerfile, or dependency changes. User-visible: ships with a minor version bump before archive.
