# Spec Delta

## MODIFIED Requirements

### Requirement: Humanized log entry display
The log panel SHALL render each received log entry as a single human-readable line showing the time, the level, and the event's key fields — not the raw JSON — for the known event types (`server_started`, `server_stopped`, `http_request`, `fetch_attempt`, `fetch_rejected`, `transcript_saved`, `transcript_save_failed`, `summary_completed`, `summary_failed`, `summary_save_failed`, `config_load_failed`, `unhandled_exception`). For an event type without a dedicated format, the panel SHALL display the event name together with the entry's remaining fields as key=value text.

#### Scenario: Fetch failure shown with cause
- **WHEN** a fetch attempt fails and the log panel is visible
- **THEN** the panel shows a line identifying the failed attempt (video ID, fetcher source, error code) together with the failure's cause detail
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-012
  - **File:** tests/e2e/test_log_viewer.py::test_fetch_failure_shown_with_cause
  - **Command:** python -m pytest tests/e2e/test_log_viewer.py::test_fetch_failure_shown_with_cause -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Save failure shown with path
- **WHEN** a transcript save fails and the log panel is visible
- **THEN** the panel shows a line identifying the failed save with the target file path and the OS error message
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-013
  - **File:** tests/e2e/test_log_viewer.py::test_save_failure_shown_with_path
  - **Command:** python -m pytest tests/e2e/test_log_viewer.py::test_save_failure_shown_with_path -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Summary failure shown with cause
- **WHEN** a summarization fails and the log panel is visible
- **THEN** the panel shows a line identifying the failed summarization (provider, model) together with the failure's cause detail
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-018
  - **File:** tests/e2e/test_log_viewer.py::test_summary_failure_shown_with_cause
  - **Command:** python -m pytest tests/e2e/test_log_viewer.py::test_summary_failure_shown_with_cause -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Summary success shown
- **WHEN** a summarization succeeds and the log panel is visible
- **THEN** the panel shows a line identifying the completed summarization (provider, model) with its duration
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-019
  - **File:** tests/e2e/test_log_viewer.py::test_summary_success_shown
  - **Command:** python -m pytest tests/e2e/test_log_viewer.py::test_summary_success_shown -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Unknown event fallback
- **WHEN** the panel receives an entry whose event name has no dedicated format
- **THEN** the panel shows a line with the event name and the entry's fields as key=value text
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-014
  - **File:** tests/e2e/test_log_viewer.py::test_unknown_event_fallback
  - **Command:** python -m pytest tests/e2e/test_log_viewer.py::test_unknown_event_fallback -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Panel grows with appended entries
- **WHEN** multiple log entries are received while the panel is visible
- **THEN** the panel shows them in chronological order, newest appended last, and remains scrollable without breaking the page layout
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-015
  - **File:** tests/e2e/test_log_viewer.py::test_panel_grows_with_entries
  - **Command:** python -m pytest tests/e2e/test_log_viewer.py::test_panel_grows_with_entries -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Panel display cap
- **WHEN** more entries are received than the panel's display cap (200 lines)
- **THEN** only the most recent entries, up to the cap, are displayed
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-016
  - **File:** tests/e2e/test_log_viewer.py::test_panel_display_cap
  - **Command:** python -m pytest tests/e2e/test_log_viewer.py::test_panel_display_cap -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Plain-text insertion
- **WHEN** a log entry's fields contain markup-like text
- **THEN** the panel displays that text verbatim as plain text and does not render or execute it
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-017
  - **File:** tests/e2e/test_log_viewer.py::test_markup_rendered_as_plain_text
  - **Command:** python -m pytest tests/e2e/test_log_viewer.py::test_markup_rendered_as_plain_text -q
  - **Pass:** exit code 0, no skipped tests
