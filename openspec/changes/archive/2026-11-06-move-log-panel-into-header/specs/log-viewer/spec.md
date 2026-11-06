# Spec Delta

## MODIFIED Requirements

### Requirement: Log panel and toggle
The interface SHALL provide a "Show logs" button that, when clicked, makes the log panel visible; the button SHALL then read "Hide logs" and, when clicked again, hide the panel. The panel SHALL be hidden when the page first loads. When the panel is visible, it SHALL be displayed adjacent to the toggle — immediately beneath it — without requiring the user to scroll the page.

#### Scenario: Panel hidden by default
- **WHEN** the page loads
- **THEN** the log panel is not visible and the toggle button reads "Show logs"
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-008
  - **File:** tests/e2e/test_log_viewer.py::test_panel_hidden_by_default
  - **Command:** python -m pytest tests/e2e/test_log_viewer.py::test_panel_hidden_by_default -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Showing the panel
- **WHEN** the user clicks "Show logs"
- **THEN** the log panel becomes visible and the toggle button reads "Hide logs"
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-009
  - **File:** tests/e2e/test_log_viewer.py::test_show_logs_reveals_panel
  - **Command:** python -m pytest tests/e2e/test_log_viewer.py::test_show_logs_reveals_panel -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Hiding the panel
- **WHEN** the user clicks "Hide logs"
- **THEN** the log panel is hidden and the toggle button reads "Show logs"
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-010
  - **File:** tests/e2e/test_log_viewer.py::test_hide_logs_hides_panel
  - **Command:** python -m pytest tests/e2e/test_log_viewer.py::test_hide_logs_hides_panel -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Entries while hidden are still available
- **WHEN** the panel is hidden while the application logs events, and the user re-shows the panel
- **THEN** the panel displays the recent entries, including those logged while the panel was hidden
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-011
  - **File:** tests/e2e/test_log_viewer.py::test_entries_while_hidden_still_available
  - **Command:** python -m pytest tests/e2e/test_log_viewer.py::test_entries_while_hidden_still_available -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Panel appears beneath the toggle
- **WHEN** the user clicks "Show logs" and the log panel becomes visible
- **THEN** the log panel is displayed immediately beneath the toggle without requiring page scrolling
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-020
  - **File:** tests/e2e/test_log_viewer.py::test_panel_shown_beneath_toggle
  - **Command:** python -m pytest tests/e2e/test_log_viewer.py::test_panel_shown_beneath_toggle -q
  - **Pass:** exit code 0, no skipped tests
