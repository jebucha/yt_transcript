# Proposal

## Why

After a successful fetch, the result header places the video title in a flex row beside the action toolbar (Copy transcript, Download, provider picker, Auto-summarize, Summarize). The toolbar has `flex-shrink: 0` and consumes most of the container's ~728px usable width (760px `max-width` minus 16px horizontal padding), while the title column is allowed to shrink to zero with `overflow-wrap: anywhere` — so long video titles collapse into a narrow, very tall vertical strip of characters to the left of "Copy transcript", badly hurting readability and usability.

## What Changes

- Restructure the result header (Option B): the video title moves onto its own full-width line above the action toolbar instead of competing with it for horizontal space.
- Clamp the video title to at most two visible lines with an ellipsis; the full title remains available via a hover tooltip (`title` attribute, still plain text).
- Make the action toolbar wrap onto additional lines (`flex-wrap: wrap`) so its controls never overflow at narrow viewport widths.
- No changes to fetch/copy/summarize behavior, endpoints, or what content is displayed (title, language, transcript are all still shown, still inserted via `textContent` only).

## Capabilities

### New Capabilities

(None.)

### Modified Capabilities

- `web-interface`: gains a new **Result header layout** requirement — the video title renders on its own line above the action toolbar, bounded to at most two visible lines with ellipsis truncation (full title as hover tooltip), and the action toolbar wraps rather than overflow at narrow widths. The existing **Transcript display** requirement (title, language, plain-text-only insertion) is unchanged.

## Impact

- `app/static/index.html` — likely unchanged: existing `.result-meta` / `.result-actions` divs and DOM order already support the new column layout (CSS-only restructure); touched only if a wrapper tweak proves necessary.
- `app/static/style.css` — `.result-header`, `.result-meta`, `.result-actions`, `.video-title` layout rules; first responsive behavior in the stylesheet (wrapping instead of media queries).
- `app/static/app.js` — set the `title` tooltip attribute where the title element is populated (fetch result and saved-transcript restore paths).
- `tests/e2e/test_ui.py` — existing assertions on `#video-title` text keep passing (CSS truncation does not change `textContent`/`innerText`); three new layout tests for long titles and narrow viewports (T-WEB-INTERFACE-015 .. 017).
- No backend, API, or dependency changes. User-visible change: minor version bump (`uv version --bump minor`) before archiving, per project convention.
