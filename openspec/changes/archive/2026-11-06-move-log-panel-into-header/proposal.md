# Proposal: Move Log Panel Into Header

## Why

The "Show logs" panel currently renders at the bottom of the page, so once the operator opens it they must scroll past the rest of the page to see the log entries they asked for.

## What Changes

- Move the `#log-panel` element from the end of `main.container` into the page header, rendering it as a second row directly beneath the "Show logs" / "Hide logs" toggle button.
- Retune the header and log-panel styles so the panel renders in its new location and keeps its internal scrolling behavior.

## Capabilities

- **Modified**: `log-viewer` — the log panel toggle behavior now also specifies placement: when visible, the panel is displayed immediately beneath the toggle without requiring page scroll.

## Impact

- Primary edit surfaces: `app/static/index.html` and `app/static/style.css`. No backend, API, or data-layer changes.
- E2E tests in `tests/e2e/test_log_viewer.py` may need placement assertions adjusted.
