# `app/static/app.js` — the frontend script

## Purpose

The entire frontend behavior, in one vanilla-JS IIFE with `"use strict"`:
fetch flow and result display, copy/download, the saved-transcripts list,
summarization, and the live log viewer. No framework, no build step, no CDN
— the file is served as-is at `/app.js` and references DOM ids defined in
`index.html`.

## Public surface

Nothing is exported (module-scoped IIFE). Its effective API is the set of DOM
ids it requires from `index.html`: `url-input`, `fetch-form`, `fetch-btn`,
`fetch-spinner`, `error-banner`, `result`, `video-title`, `video-language`,
`transcript-panel`, `copy-btn`, `download-btn`, `saved-list`, `saved-empty`,
`saved-count`, `saved-refresh-btn`, `provider-picker`, `summarize-btn`,
`summarize-spinner`, `summary-panel`, `summary-text`, `summary-copy-btn`,
`auto-summarize`, `auto-summarize-note`, `log-panel`, `logs-toggle`. It
also defines the `ERROR_MESSAGES` map (server error code → human message)
for the nine taxonomy codes.

## Invariants

- **No-`innerHTML` rule — absolute.** Every fetched string (transcript,
  title, names, summary, log lines) enters the DOM via `textContent` (or
  element construction) only; never as HTML. Markup-like content from
  YouTube or a backend cannot be rendered or executed.
- **Requests use the real file name, display uses a prettified one.** List
  rows keep the real name in `data-name`; the display label (extension
  stripped, underscores → spaces, CSS capitalization) is cosmetic and is
  *never* sent to the server.
- **Two distinct name variables, deliberately.** `currentSavedName` (a
  clicked saved row) drives Download's enabled predicate — a freshly fetched
  transcript does **not** enable Download. `currentTranscriptName` (the
  fetch response's derived name, or the saved row's name) is what Summarize
  sends for the alongside save.
- **`displayToken` invalidates stale results.** A monotonic token is bumped
  on every new transcript display; an in-flight saved-summary response or
  summarize response for a previously displayed transcript is discarded.
- **One summarize path, two entry points.** `doSummarize(auto)` serves the
  manual click (`auto=false`: picker selection, error banner on failure) and
  the post-fetch auto-fire (`auto=true`: the default target from
  `defaultSelection()`, the subdued note on failure). Both share the
  busy state (button, picker, and checkbox disabled + spinner), the
  `summarizing` guard, and the token staleness rule.
- **Auto-summarize fires on fresh fetches only.** The hook sits in
  `renderResult`, never in the saved-transcript click path. With the
  checkbox on it first reuses the saved-summary read: found → show it and
  skip (no summarize call); otherwise fire `doSummarize(true)` against the
  picker's default (`defaultSelection()`, the same target the picker
  pre-selects). The accepted consecutive-fetch race drops the second
  auto-fire via the `summarizing` guard (design D7).
- **Auto failures never raise the banner.** Every automatic failure shape
  (`PROVIDER_ERROR`, `NOT_CONFIGURED`, `INVALID_PROVIDER`, `INPUT_TOO_LONG`,
  network error, empty-`summary` 200) shows the subdued `#auto-summarize-note`
  (`textContent` only) and leaves the enabled Summarize button as the
  explicit retry; the manual path keeps the banner untouched. The note
  follows the same token staleness rule as the success path: a late failure
  for a superseded transcript is dropped, never painted onto a newer one.
- **The Auto-summarize checkbox mirrors the server setting.** Loaded once
  on page load via `GET /api/settings` (no polling); toggling POSTs the
  change and reverts the checkbox to the last persisted value if the write
  fails. It is interactive only when providers are configured and is
  disabled while any summarize is in flight.
- **No polling.** The saved list, the provider list, and the settings load
  once on page load, the list also reloads after each successful fetch and
  via its Refresh button. The provider list is never re-fetched (a stale
  picker after a config edit gets a clean 400 `INVALID_PROVIDER` telling
  the user to reload).
- **Copy works over plain HTTP.** `navigator.clipboard.writeText` first,
  falling back to a hidden-textarea `execCommand("copy")` — the Clipboard
  API does not exist in non-secure contexts, and plain HTTP is the normal
  access path.
- **A 2xx with no summary text is a failure for display** — show the error
  region, never an empty panel (same truthiness check as the saved-summary
  load).
- **The log panel is a display concern.** Entries keep accumulating while
  the panel is hidden, so re-showing it includes what was logged in the
  meantime; the panel trims to its 200-line display cap (mirroring the
  server buffer).
- **SSE is fire-and-forget.** `EventSource` reconnects automatically;
  unparseable payloads are dropped; no error handling is needed.

## Log events emitted

None (browser code). It *formats* server events for the panel via
`LOG_FORMATTERS` — one-line humanized formatters for the known events
(`server_started`, `server_stopped`, `http_request`, `fetch_attempt`,
`fetch_rejected`, `transcript_saved`, `transcript_save_failed`,
`summary_completed`, `summary_failed`, `summary_save_failed`,
`config_load_failed`, `unhandled_exception`), with a
`time  LEVEL  event  key=value …` fallback for unknown ones.

## Error codes handled

`INVALID_URL`, `VIDEO_UNAVAILABLE`, `NO_CAPTIONS`, `UPSTREAM_FAILURE`,
`BUSY`, `NOT_CONFIGURED`, `INVALID_PROVIDER`, `PROVIDER_ERROR`,
`INPUT_TOO_LONG` — via the `ERROR_MESSAGES` map (preferred over the server
message); network failures and unexpected shapes get a generic message.

## Design decisions

Resolved from the archived change design docs:

- `2026-10-29-youtube-transcript` **D6** — one static page, no build step,
  no framework, no CDN; the clipboard fallback for non-secure contexts; the
  no-HTML insertion rule (XSS).
- `2026-11-02-add-saved-transcript-list` **decision 6** — the saved section:
  reusable result panel, prettified labels with real-name requests,
  client-side Blob download, load-once-plus-refresh (no polling).
- `add-transcript-summary` **decision 5** (the fetch response's `name` lands
  in a *new* variable; Download's predicate is intentionally untouched),
  **decision 11** (the UI state machine: picker pre-selection, enabled
  predicate, `currentSummary` lifecycle, the e2e seam below
  `summarize_with_provider`).
- `2026-11-03-add-log-viewer` **decision 6** — the panel shape, the
  `EventSource` opened once at page load, the formatters, the 200-line cap.
- `add-auto-summarize` **D4** (`defaultSelection()` shared by the picker
  pre-selection and the auto target), **D5** (`doSummarize(auto)` as one
  code path, the hook after `renderResult` only, skip-and-show via the
  saved-summary read), **D6** (subdued note for auto failures, checkbox
  revert on a failed settings write), **D7** (accepted: a second auto-fire
  during an in-flight summarize is dropped).

## Cross-links

- [`index.html`](index-html.html) — the DOM it wires up
- [`style.css`](style-css.html) — the classes it toggles
- [`main.html`](../main.html) — the endpoints it consumes
