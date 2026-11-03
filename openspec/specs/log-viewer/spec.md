# log-viewer Specification

## Purpose

A browser-visible view of the server's structured log stream: a server-sent events log endpoint backed by an in-memory ring buffer, plus a show/hide log panel in the UI, so the operator can watch fetch and persistence events — including failure causes — without leaving the page.

## Requirements

### Requirement: Log stream endpoint
The application SHALL serve a server-sent events stream at `GET /api/logs`. While a client is connected, every log entry the application emits at info level or above SHALL be delivered to that client as an individual stream event whose payload is the entry encoded as a single JSON object containing at minimum the timestamp, the level, and the event name, plus the entry's own fields.

#### Scenario: Live event delivered to connected client
- **WHEN** a client is connected to the log stream and the application logs an event
- **THEN** the client receives a stream event whose payload is a JSON object containing the event's timestamp, level, and event name
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-001
  - **File:** tests/test_log_viewer.py::test_live_event_delivered
  - **Command:** python -m pytest tests/test_log_viewer.py::test_live_event_delivered -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Multiple concurrent clients
- **WHEN** two clients are connected to the log stream and the application logs an event
- **THEN** both clients receive the event
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-002
  - **File:** tests/test_log_viewer.py::test_multiple_clients_receive_event
  - **Command:** python -m pytest tests/test_log_viewer.py::test_multiple_clients_receive_event -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Stream does not affect the fetch chain
- **WHEN** a client is connected to the log stream and a transcript fetch is requested
- **THEN** the fetch proceeds normally, unaffected by the log stream connection
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-003
  - **File:** tests/test_log_viewer.py::test_log_stream_does_not_affect_fetch
  - **Command:** python -m pytest tests/test_log_viewer.py::test_log_stream_does_not_affect_fetch -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Log history replay
On connection to the log stream, the application SHALL first deliver the most recent log entries from an in-memory buffer, in chronological order, capped at 200 of the most recent entries. Entries older than the cap SHALL NOT be delivered.

#### Scenario: Recent history delivered on connect
- **WHEN** the application has recently logged several events and a client connects to the log stream
- **THEN** the client receives those events, in chronological order, before any newer live events
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-004
  - **File:** tests/test_log_viewer.py::test_history_replayed_on_connect
  - **Command:** python -m pytest tests/test_log_viewer.py::test_history_replayed_on_connect -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Buffer cap
- **WHEN** more events have been logged than the buffer cap holds and a client connects
- **THEN** the client receives only the most recent entries, up to the cap
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-005
  - **File:** tests/test_log_viewer.py::test_buffer_cap
  - **Command:** python -m pytest tests/test_log_viewer.py::test_buffer_cap -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Logging unaffected by the log viewer
The application SHALL continue writing every log entry to stdout as a single JSON line in the established format regardless of whether any log stream client is connected. The in-memory buffer SHALL be internal state only, not a log output destination, and the application SHALL NOT create log files.

#### Scenario: Stdout logging with no subscribers
- **WHEN** the application logs an event while no client is connected to the log stream
- **THEN** the event appears on stdout as a single JSON line in the established format
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-006
  - **File:** tests/test_log_viewer.py::test_stdout_without_subscribers
  - **Command:** python -m pytest tests/test_log_viewer.py::test_stdout_without_subscribers -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Stdout logging with subscribers
- **WHEN** the application logs an event while one or more clients are connected to the log stream
- **THEN** the event appears on stdout exactly once as a single JSON line in the established format
- **Test Requirement**
  - **ID:** T-LOG-VIEWER-007
  - **File:** tests/test_log_viewer.py::test_stdout_with_subscribers
  - **Command:** python -m pytest tests/test_log_viewer.py::test_stdout_with_subscribers -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Log panel and toggle
The interface SHALL provide a "Show logs" button that, when clicked, makes the log panel visible; the button SHALL then read "Hide logs" and, when clicked again, hide the panel. The panel SHALL be hidden when the page first loads.

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

### Requirement: Humanized log entry display
The log panel SHALL render each received log entry as a single human-readable line showing the time, the level, and the event's key fields — not the raw JSON — for the known event types (`server_started`, `server_stopped`, `http_request`, `fetch_attempt`, `fetch_rejected`, `transcript_saved`, `transcript_save_failed`, `unhandled_exception`). For an event type without a dedicated format, the panel SHALL display the event name together with the entry's remaining fields as key=value text.

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
