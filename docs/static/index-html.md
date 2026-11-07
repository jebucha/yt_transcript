# `app/static/index.html` — the single static page

## Purpose

The entire web UI's markup: one page, no framework, no build step, no CDN.
It defines the DOM contract that `app.js` consumes — every id the script
reaches for — and the visible structure: header (with the log viewer), the
fetch form, the error banner, the result section (transcript panel +
summary panel), and the saved-transcripts section.

## Public surface

The asset set is exactly three files referenced with absolute paths:
`/style.css`, `/app.js`, and this page (served by the static mount at `/`).
The effective API is the id/class contract with `app.js`:

- Fetch flow: `url-input`, `fetch-form`, `fetch-btn`, `fetch-spinner`,
  `fetch-label`.
- Result: `error-banner`, `result`, `video-title`, `video-language`,
  `transcript-panel`, `copy-btn`, `download-btn`.
- Summarization: `provider-picker`, `summarize-btn`, `summarize-spinner`,
  `summary-panel`, `summary-text`, `summary-copy-btn`.
- Saved list: `saved-list`, `saved-empty`, `saved-count`,
  `saved-refresh-btn`.
- Log viewer: `logs-toggle`, `log-panel`.

## Invariants

- **No build step, no framework, no CDN.** The file is hand-maintained
  markup; anything requiring a transpiler or a third-party script is
  off-limits for this app.
- **The `hidden` attribute is the visibility contract**, and the CSS rule
  `[hidden] { display: none !important; }` in `style.css` keeps it
  authoritative even for styled elements. `app.js` toggles only `hidden`.
- **The log panel lives in the header, as the header's second row** — not
  at the bottom of the page flow — so opening it never requires scrolling.
  The header is a column of rows (titles + toggle on the first row, panel
  on the second), with row gap providing the spacing.
- **Accessibility is structural, not script-added:** `role="alert"` on the
  error banner, `aria-label`s on the input, panels, and provider picker,
  `tabindex="0"` on the scrollable `<pre>` panels, `type="button"` on
  non-submit buttons, `aria-hidden` on the spinners.
- **Buttons start disabled where `app.js` requires it** (copy, download,
  summarize, the provider picker); the script enables them as state allows.
- **The result section is hidden until the first transcript** — fresh fetch
  and saved-row display both render into this same single panel.

## Log events emitted

None (markup). The `log-panel` `<pre>` is where `app.js` appends the
humanized server log lines.

## Error codes raised/handled

None (markup). The `error-banner` element is where `app.js` surfaces them.

## Design decisions

Resolved from the archived change design docs:

- `2026-10-29-youtube-transcript` **D6** — one static page served by
  FastAPI's `StaticFiles`; no framework, no bundler, no CDN.
- `2026-11-02-add-saved-transcript-list` **decision 6** — the saved section
  below `#result`: header over a bounded, scrollable `<ul>`, rows as
  keyboard-accessible `<button>`s.
- `2026-11-03-add-log-viewer` **decision 6** — the `#logs-toggle` button and
  the `#log-panel` `<pre>` (monospace, scrollable, bounded max-height).
- `2026-11-06-move-log-panel-into-header` **D1–D3** — push-down placement in
  the header (normal document flow, not an overlay), the column-of-rows
  header with `align-items: stretch`, and row-gap spacing replacing the old
  `margin-top` while the panel keeps its `max-height: 40vh` internal scroll.

## Cross-links

- [`app.js`](app-js.html) — the script that owns the behavior
- [`style.css`](style-css.html) — the stylesheet that owns the look
- [`main.html`](../main.html) — the static mount that serves this file
