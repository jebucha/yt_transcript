# Design

## Context

The log panel (`#log-panel`) is the last child of `main.container`, so it renders at the bottom of the page flow and only appears after the operator scrolls. The toggle (`#logs-toggle`) lives in the single-row `.header` (flex row, `space-between`, `align-items: flex-start`) alongside the titles.

## Goals / Non-Goals

**Goals:**
- When the log panel is visible, it renders directly beneath the "Show logs" toggle without requiring the user to scroll the page.

**Non-Goals:**
- Overlay-style presentation of the panel.
- Changes to log stream plumbing, the in-memory buffer, or humanized formatting.
- Changing the panel's internal scroll behavior or display cap.

## Decisions

- **D1: Push-down placement inside the header (normal document flow) over an overlay.** The panel is moved into the header as a second row, so it participates in normal layout and the existing `[hidden] { display: none !important; }` rule keeps it hidden until shown. An overlay would require absolute positioning and viewport-attachment handling that the current styling does not need.
- **D2: Header becomes a column of rows.** The titles + toggle move into a new `.header-row` (first row, keeping the existing `space-between` row styles). The log panel becomes the second child of `.header`, i.e. a second row beneath the toggle row. The column container sets cross-axis alignment explicitly (`align-items: stretch`) so rows span the full header width rather than shrinking to content width. When hidden, the row (and panel) contributes no height.
- **D3: Panel spacing moves from `margin-top` to row gap.** The previous `.log-panel { margin: 32px 0 0; }` spacing is replaced by the header row gap so the panel sits close beneath the toggle when opened and adds no stray top margin in the header context. The panel keeps its `max-height: 40vh` and `overflow-y: auto` internal scrolling, so opening it never exceeds the viewport.

## Test Strategy

The modified requirement is verified by the e2e suite in `tests/e2e/test_log_viewer.py`, which carries one Test Requirement block per scenario (T-LOG-VIEWER-008 through T-LOG-VIEWER-020).

- **D1** → T-LOG-VIEWER-020: push-down placement is asserted by rendering the panel beneath the toggle without requiring page scroll.
- **D2** → T-LOG-VIEWER-020: retuned column-of-rows header layout is asserted by rendering the panel as a second row beneath the toggle row.
- **D3** → T-LOG-VIEWER-020: row-gap spacing is asserted by confirming the panel retains bounded internal scrolling (max-height / overflow) when opened.

## Risks / Trade-offs

- [Risk] Opening the panel grows the header height and pushes the rest of the page content down. → Mitigation: intended push-down behavior; panel is height-bounded (`max-height: 40vh`) and scrolls internally, so the layout shift stays bounded.
- [Risk] On short viewports the header plus a 40vh panel could crowd the viewport. → Mitigation: retain the bounded max-height and internal scroll; the panel scrolls rather than expanding the page.

## Migration Plan

No migration required. Static assets only (`app/static/index.html`, `app/static/style.css`); no data or API surface changes.
