# Tasks

## 1. Move log panel into header

- [x] 1.1 Move the `#log-panel` markup from the end of `main.container` into the header as a second row beneath the toggle button in `app/static/index.html`
- [x] 1.2 Retune `.header` (column of rows) and `.log-panel` spacing in `app/static/style.css`
- [x] 1.3 Confirm the toggle logic in `app/static/app.js` needs no change (selector/attribute-driven visibility)

## 2. Verify placement

- [x] 2.1 Extend the log-viewer e2e tests in `tests/e2e/test_log_viewer.py` to assert the panel renders beneath the toggle without requiring page scroll
- [x] 2.2 Run the log-viewer e2e suite and confirm it passes

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Bump the app minor version (`uv version --bump minor`) before release, since this is a user-visible change.
