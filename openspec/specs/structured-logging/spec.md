# structured-logging Specification

## Purpose

Emit structured, machine-readable JSON log lines to stdout covering process lifecycle, incoming web requests, and every YouTube fetch attempt, so operators can fully reconstruct what the app did via `docker logs` / `podman logs`.

## Requirements

### Requirement: JSON line log format
The application SHALL write every log entry as a single JSON object on one line of stdout, including at minimum an ISO-8601 timestamp, a log level, and an event name or message. The application SHALL NOT write logs to files, and stdout SHALL be its only log output.

#### Scenario: Well-formed log line
- **WHEN** any event is logged
- **THEN** the corresponding stdout line parses as a single JSON object containing `timestamp`, `level`, and a message or event field
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-001
  - **File:** tests/test_logging_format.py::test_log_line_is_single_json_object
  - **Command:** python -m pytest tests/test_logging_format.py::test_log_line_is_single_json_object -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: No file logging
- **WHEN** the container runs
- **THEN** no log files are created inside the container and all log output appears on stdout
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-002
  - **File:** tests/test_logging_format.py::test_no_log_files_created
  - **Command:** python -m pytest tests/test_logging_format.py::test_no_log_files_created -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Lifecycle logging
The application SHALL log a startup event containing the listen port, a shutdown event when it terminates, and an error event (with exception detail) for any unhandled exception.

#### Scenario: Startup logged
- **WHEN** the application starts and begins serving
- **THEN** a startup event is logged that includes the listen port
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-003
  - **File:** tests/test_logging_lifecycle.py::test_startup_event_includes_port
  - **Command:** python -m pytest tests/test_logging_lifecycle.py::test_startup_event_includes_port -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Unhandled exception logged
- **WHEN** an unhandled exception occurs
- **THEN** an error-level event is logged containing the exception type and detail before the process exits or the request fails
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-004
  - **File:** tests/test_logging_lifecycle.py::test_unhandled_exception_logs_error_event
  - **Command:** python -m pytest tests/test_logging_lifecycle.py::test_unhandled_exception_logs_error_event -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Web request logging
The application SHALL log every incoming HTTP request, including method, path, response status, and duration in milliseconds.

#### Scenario: Successful request logged
- **WHEN** a request completes with status 200
- **THEN** a log entry records the method, path, status 200, and the request duration
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-005
  - **File:** tests/test_logging_requests.py::test_successful_request_logged
  - **Command:** python -m pytest tests/test_logging_requests.py::test_successful_request_logged -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Error request logged
- **WHEN** a request completes with a 4xx or 5xx status
- **THEN** a log entry records the method, path, that status, and the request duration
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-006
  - **File:** tests/test_logging_requests.py::test_error_request_logged
  - **Command:** python -m pytest tests/test_logging_requests.py::test_error_request_logged -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Fetch operation logging
The application SHALL log each YouTube fetch attempt individually — including any failed primary attempt followed by a fallback attempt — with the video ID, the requested language, the fetcher source, the outcome (success or failure reason), the duration, and, on success, the transcript length in characters.

#### Scenario: Successful primary fetch logged
- **WHEN** the primary fetcher succeeds
- **THEN** one log entry records the video ID, language, primary source, success, duration, and transcript length
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-007
  - **File:** tests/test_logging_fetch.py::test_primary_fetch_logged
  - **Command:** python -m pytest tests/test_logging_fetch.py::test_primary_fetch_logged -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Fallback chain logged
- **WHEN** the primary fetcher fails and the fallback fetcher succeeds
- **THEN** two log entries are recorded: one for the failed primary attempt including the failure reason, and one for the successful fallback attempt
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-008
  - **File:** tests/test_logging_fetch.py::test_fallback_chain_logs_two_entries
  - **Command:** python -m pytest tests/test_logging_fetch.py::test_fallback_chain_logs_two_entries -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: No sensitive data in logs
- **WHEN** any request or fetch is logged
- **THEN** no log entry contains raw HTTP request headers or credentials
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-009
  - **File:** tests/test_logging_fetch.py::test_no_headers_or_credentials_in_logs
  - **Command:** python -m pytest tests/test_logging_fetch.py::test_no_headers_or_credentials_in_logs -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Persistence operation logging
The application SHALL log each transcript file save operation as a single structured JSON event on stdout: a `transcript_saved` event at info level on success, and a `transcript_save_failed` event at error level on failure. The success event SHALL include the video ID, the file path written, and the number of bytes written. The failure event SHALL include the video ID and a machine-readable failure reason in the `reason` field (the exception type name).

#### Scenario: Successful save logged
- **WHEN** a fetched transcript is written to the transcript directory successfully
- **THEN** one log entry records the `transcript_saved` event with the video ID, the file path, and the byte count
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-010
  - **File:** tests/test_persistence.py::test_successful_save_logged
  - **Command:** python -m pytest tests/test_persistence.py::test_successful_save_logged -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Failed save logged
- **WHEN** a fetched transcript cannot be written to the transcript directory
- **THEN** one log entry records the `transcript_save_failed` event with the video ID and a failure reason
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-011
  - **File:** tests/test_persistence.py::test_failed_save_logged
  - **Command:** python -m pytest tests/test_persistence.py::test_failed_save_logged -q
  - **Pass:** exit code 0, no skipped tests
