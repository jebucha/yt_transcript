# `app/static/style.css` — the stylesheet

## Purpose

The single self-contained stylesheet for the UI: the design tokens
(custom properties on `:root`), the page layout, and the class styles for
every region `app.js` drives. No web fonts, no CDN, no external references
of any kind — the app's no-CDN constraint applies to CSS as firmly as to JS.

## Public surface

Design tokens: `--bg`, `--panel`, `--text`, `--muted`, `--accent`,
`--accent-dark`, `--error-*`, `--border`. Class/element contract with
`index.html` / `app.js`: `.container` (the single 760px column),
`.header` / `.header-row`, `.row`, `.url-input`, `.btn` / `.btn-quiet`,
`.spinner`, `.error-banner`, `.result-*`, `.video-title`,
`.video-language`, `.transcript-panel`, `.provider-picker`,
`.auto-summarize-label` (the checkbox label; dims with the input's
`:disabled` via `:has()`), `.auto-note` (the muted auto-summarize failure
note), `.summary-*`, `.saved-*` (`.saved-row` is the button-styled list
item), `.model-management-*` (the section, list container, and empty
state), `.model-provider-*` (the button-styled row: name, count, manage),
`.model-panel*` (the manage panel and its labeled groups),
`.model-add-*` (the manual-add form), `.model-list*` (the model rows;
`.model-list-id` is the monospace id text), `.model-item-btn*` (the small
row buttons; `-remove` gets the error-color treatment), `.log-panel`.

## Invariants

- **Self-contained.** No `@import`, no web fonts, no external URLs; the
  font stacks are the system stack for text and `ui-monospace`/Menlo/Consolas
  for the log panel and transcript pre blocks.
- **`[hidden] { display: none !important; }` is load-bearing.** It keeps the
  `hidden` attribute authoritative even for styled elements (buttons and
  panels with display rules), so `app.js`'s visibility contract can never be
  silently defeated by a class.
- **The header is a column of rows** (`flex-direction: column`,
  `align-items: stretch`): titles + toggle in the first row (`.header-row`,
  `space-between`), the log panel as the second row. Spacing between rows
  comes from the column's `gap`, not from the panel's `margin-top` — the
  panel sits close beneath the toggle when opened and contributes no height
  when hidden.
- **Every long region scrolls internally with a bounded height:** the
  transcript panel `max-height: 60vh`, the summary text and saved list
  `40vh`, the log panel `40vh`, the model lists (added/discovered/config)
  `30vh` — opening any of them never grows the page without bound.
- **Buttons are keyboard- and state-honest:** `.btn:disabled` dims and
  forbids; `.saved-row` keeps `:focus-visible` outlines; hover states apply
  only to `:not(:disabled)`.
- **Long content wraps, never overflows:** `overflow-wrap: anywhere` on
  titles, transcript, saved names, provider names, model ids, and the log
  panel.

## Log events emitted

None (markup-adjacent styles only).

## Error codes raised/handled

None.

## Design decisions

Resolved from the archived change design docs:

- `2026-10-29-youtube-transcript` **D6** — the no-build, no-CDN front-end
  constraint this file obeys.
- `2026-11-02-add-saved-transcript-list` **decision 6** — the saved section's
  treatment: bounded scrollable `<ul>` matching the existing
  `.transcript-panel` treatment, button-styled rows, the cosmetic
  `text-transform: capitalize` on `.saved-name` (accepted trade-off:
  acronym-like words are lowercased cosmetically; the real name is always
  what is requested and downloaded).
- `2026-11-06-move-log-panel-into-header` **D2/D3** — the column-of-rows
  header (`align-items: stretch` so rows span the full width) and the
  row-gap spacing that replaced the old `.log-panel { margin: 32px 0 0; }`.
- `add-summarization-model-management` **D7** — the model-management
  section's treatment: button-styled provider rows on the same border/
  hover/focus recipe as `.saved-row`, the manage panel as a recessed
  (`--bg`) group of labeled lists, monospace model ids, and the
  error-colored Remove button.

## Cross-links

- [`index.html`](index-html.html) — the markup it styles
- [`app.js`](app-js.html) — the script that toggles the classes and `hidden`
