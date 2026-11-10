# Design

## Context

The result header (`app/static/index.html` `#result .result-header`) is a two-column flex row: `.result-meta` (`#video-title`, `#video-language`) on the left, `.result-actions` (copy, download, provider picker, auto-summarize label, summarize button) on the right with `flex-shrink: 0`. The container has a 760px `max-width` with 16px horizontal padding, leaving at most ~728px usable for the header; the toolbar's five controls consume most of it, `.result-meta` has `min-width: 0`, and `.video-title` has `overflow-wrap: anywhere` — so long titles collapse into a tall, character-wrapped vertical strip. The stylesheet currently has no responsive rules at all, so the toolbar itself overflows below roughly 700px viewport width regardless of the title.

Constraints: vanilla CSS/JS, no build step, no framework, no CDN; fetched content enters the DOM via `textContent` only. E2E tests assert on `#video-title`'s `innerText`/`textContent` and on button ids, so element ids and the full DOM text must be preserved. See proposal.md - Why for motivation and `specs/web-interface/spec.md` for the requirements.

## Goals / Non-Goals

**Goals:**
- Title never grows vertically beyond two lines, at any title length or viewport width.
- Title never shares a horizontal line with the action toolbar — it owns a full-width line above it.
- Action toolbar wraps gracefully at narrow widths (this incidentally gives the stylesheet its first responsive behavior, via wrapping rather than media queries).
- Zero churn to existing e2e assertions: element ids and full title text in the DOM stay intact.

**Non-Goals:**
- No changes to the saved-transcripts list, summary panel header, or log panel layout.
- No media-query overhaul of the whole page; only the result header is touched.
- No change to what is displayed (title, language, transcript) or how content is injected (`textContent` only stays).
- No clickable "expand title" interaction — the hover tooltip is enough.

## Decisions

**D1: Stack the header — `.result-header` becomes `flex-direction: column`.**
`.result-meta` becomes the full-width first line (title, then language beneath it, as today), `.result-actions` sits below. Column direction alone is not enough: `.result-header` keeps `align-items: flex-start`, which cross-sizes column items to fit-content, so the rule also sets `align-items: stretch` (equivalently `width: 100%` on `.result-meta`) to make the title line truly full-width. Chosen over `flex-wrap: wrap` with a `flex-basis: 100%` title: column direction is simpler, has no shrink interaction to reason about, and makes the `min-width: 0` / `flex-shrink: 0` interplay (the root cause) moot. Markup change is minimal: the existing `.result-meta` / `.result-actions` divs stay in place and DOM order already puts meta first, so this is essentially a CSS-only restructure (index.html likely needs no change at all).

**D2: Two-line clamp via `-webkit-line-clamp` on `.video-title`.**
`display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden` — the only build-free, JS-free way to get a real trailing ellipsis at exactly two lines, and supported by all current Chromium/Firefox/Safari versions. Also declare an explicit numeric `line-height` (e.g. `1.5`) on `.video-title`: nothing in the header chain currently sets one, so `getComputedStyle` returns the keyword `"normal"` and the e2e height assertion (D5) would have no numeric value to multiply; the explicit declaration makes the two-line bound precisely measurable and keeps the clamp's line box deterministic. Alternatives rejected: `max-height` + `overflow: hidden` (hard visual cut, no ellipsis); JS truncation (adds logic, mutates the text other tests read); single-line `text-overflow: ellipsis` (rejected by the user in exploration in favor of two lines). Keep `overflow-wrap: anywhere` as an overflow guard for pathological no-space titles (e.g. 200-char hashes): with the full-width line it fires rarely and stays clamped when it does.

**D3: Full title via `title` attribute set in `app.js`.**
Wherever `titleEl.textContent` is assigned — the fetch-result path (`data.title`) and the saved-restore path (`data.name`) — also set `titleEl.title = data.title || ""` (same for the restore path). Assigning a DOM property is not HTML injection, so the plain-text-only rule is honored; this mirrors the existing `row.title = entry.name` pattern in the saved list. Rejected: a custom tooltip widget (framework-ish complexity for no gain).

**D4: Toolbar wrapping via `flex-wrap: wrap` on `.result-actions`.**
Wraps controls onto additional lines within the container's ~728px usable width at narrow viewports. `flex-shrink: 0` stays (irrelevant once the toolbar owns its full-width line, but harmless and keeps button labels intact); gap becomes `8px` (the shorthand sets `row-gap: 8px` too, so wrapped rows don't collide). The provider picker keeps `max-width: 230px`. Rejected: media queries (more rules to maintain, wrapping handles it continuously).

**D5: E2E tests use the existing mocked-backend fixtures with a long synthetic title.**
Reuse the Playwright harness in `tests/e2e/test_ui.py` (which already drives fetch results with "Test Video Title"). Three new tests per the spec delta: (15) set a ~300-char title, fetch, assert `#video-title` bounding-box height ≤ 2 × computed `line-height` (plus rounding tolerance; the explicit `line-height` from D2 makes this computable), that the title is actually clipped — `scrollHeight` exceeds `clientHeight`, which is the DOM-verifiable evidence of truncation the `-webkit-line-clamp` renders as the visible ellipsis — and that the title sits above `#copy-btn` (title box bottom ≤ actions box top); (16) assert full title in both `textContent` and the `title` attribute; (17) set a narrow viewport (~420px), fetch with summarize controls enabled, and scope the no-overflow assertions to the result header — every `.result-actions` child's bounding box (including `#copy-btn`) right edge ≤ viewport width and bottom edge ≤ viewport height — rather than a page-global `documentElement.scrollWidth` check, so unrelated regions (page header, log panel, saved panel) cannot fail the test. CSS ellipsis does not alter `textContent`/`innerText` in Chromium, so existing assertions (lines 277, 304, 653, 711, 741) keep passing untouched.

## Test Strategy

The Test Requirement blocks in `specs/web-interface/spec.md` (T-WEB-INTERFACE-015 .. 017) run through the existing e2e harness in `tests/e2e/test_ui.py`: a real in-process uvicorn instance of the app with the upstream fetch chain stubbed (no real YouTube traffic), driven by headless Chromium via Playwright, matching the existing suite. Execute through uv from the repo root — the spec blocks' `python -m pytest …` commands become e.g. `uv run python -m pytest tests/e2e/test_ui.py::test_long_title_stays_bounded -q`. Prerequisite (already satisfied by the existing harness): `uv run python -m playwright install chromium`. Pass criterion for every block: exit code 0, no skipped tests. Test IDs 015-017 extend the module docstring's pinned range, which task 1.3 updates.

## Risks / Trade-offs

- [`-webkit-line-clamp` is a prefixed property] → Universally implemented across Chromium, Firefox (≥68), and Safari; the unprefixed `line-clamp` is declared alongside it. Worst case in some exotic engine: `overflow: hidden` still bounds the height, just without the ellipsis — the spec's height bound still holds.
- [Height assertion flakiness from line-height rounding] → Compare against `2 × line-height + tolerance` (e.g. 2px) using computed styles rather than a hard-coded pixel value; run headless Chromium only, matching the existing suite.
- [Hover tooltip is undiscoverable on touch devices] → Accepted trade-off: the transcript panel and saved list both carry the title context, and mobile users can open the saved entry; keeps the header free of extra interactive affordances.
- [Header grows ~24px when a long title uses both lines] → Intended (Option B: readable title over compact header); short titles render exactly one line, so the common case is unchanged height.
- [`title` attribute on the h2 may show a native tooltip on hover, slightly noisy for short titles] → Harmless; alternatively set the attribute unconditionally for consistency with the saved list's existing behavior.
