# Tasks

## 1. Result header layout (CSS)

- [x] 1.1 Restack `.result-header` in `app/static/style.css` to a vertical flex column (`flex-direction: column` with `align-items: stretch` so `.result-meta` is full-width first, `.result-actions` below with `flex-wrap: wrap` and an 8px row gap), per design D1/D4, and verify the existing e2e header assertions still pass: `uv run python -m pytest tests/e2e/test_ui.py -q`
- [x] 1.2 Apply the two-line clamp to `.video-title` (`display: -webkit-box` + `-webkit-box-orient: vertical` + `-webkit-line-clamp: 2` + `line-clamp: 2` + `overflow: hidden` + an explicit numeric `line-height` such as `1.5`, keeping `overflow-wrap: anywhere`), per design D2. This is a CSS-only change; verification is via the mocked e2e tests added in tasks 1.3 and 2.2 plus the untouched existing e2e suite (no live-network fetch needed).
- [x] 1.3 Add e2e tests `test_long_title_stays_bounded` (T-WEB-INTERFACE-015: ~300-char mocked title; assert `#video-title` height ≤ 2 × computed `line-height` + tolerance, the element is clipped (`scrollHeight` > `clientHeight`, evidencing the truncation the clamp renders as an ellipsis), and the title box sits above `#copy-btn`) and `test_result_actions_wrap_narrow` (T-WEB-INTERFACE-017: ~420px viewport; assert header-scoped no overflow — every `.result-actions` child's bounding box, including `#copy-btn`, fits within the viewport) to `tests/e2e/test_ui.py`, update the module docstring's pinned test-ID range to `T-WEB-INTERFACE-001 .. 017`, and verify: `uv run python -m pytest tests/e2e/test_ui.py::test_long_title_stays_bounded tests/e2e/test_ui.py::test_result_actions_wrap_narrow -q`

## 2. Full-title tooltip (JS)

- [x] 2.1 In `app/static/app.js`, set `titleEl.title` to the full title (empty string when absent) at both places `titleEl.textContent` is assigned — fetch-result path (`data.title`) and saved-restore path (`data.name`) — per design D3. Verification is via the mocked e2e test added in task 2.2 (no live-network fetch needed).
- [x] 2.2 Add e2e test `test_long_title_tooltip` (T-WEB-INTERFACE-016: assert `#video-title` `textContent` and `title` attribute both equal the full untruncated mocked title) to `tests/e2e/test_ui.py` and verify: `uv run python -m pytest tests/e2e/test_ui.py::test_long_title_tooltip -q`

## 3. Integration verification

- [x] 3.1 Run the full suite — `uv run python -m pytest tests/ -q --ignore=tests/e2e` then `uv run python -m pytest tests/e2e/ -q` — and verify exit code 0 with no skipped tests, confirming no regressions in the existing `#video-title` assertions (test_ui.py lines ~277, 304, 653, 711, 741). (Regression sweep across the whole `web-interface` capability; no single mapped requirement.)

## Workflow follow-up

- Validate the implementation in a fresh session with a model that did not write the code (`/opsx-validate`), per the project's OpenSpec workflow.
- Bump the minor version with `uv version --bump minor` before archiving (user-visible change, per AGENTS.md).
- Archive the change with `/opsx-archive` once validation passes.
