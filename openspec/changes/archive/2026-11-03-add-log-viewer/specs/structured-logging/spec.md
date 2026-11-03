# Spec Delta

## ADDED Requirements

### Requirement: Fetch failure detail
A failed `fetch_attempt` log entry SHALL additionally include a `detail` field containing the human-readable error message of the raised failure, so the cause of the failure (for example a timeout duration or the fetcher's failure cause) is visible from the log alone.

#### Scenario: Timeout failure detail logged
- **WHEN** a fetch attempt is aborted by its timeout
- **THEN** the failure log entry's `detail` field contains the timeout message, including the timeout duration
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-012
  - **File:** tests/test_logging_fetch.py::test_timeout_failure_includes_detail
  - **Command:** python -m pytest tests/test_logging_fetch.py::test_timeout_failure_includes_detail -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Fetcher failure detail logged
- **WHEN** a fetcher raises an error for a fetch attempt
- **THEN** the failure log entry's `detail` field contains that error's message
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-013
  - **File:** tests/test_logging_fetch.py::test_fetcher_failure_includes_detail
  - **Command:** python -m pytest tests/test_logging_fetch.py::test_fetcher_failure_includes_detail -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Save failure detail
A `transcript_save_failed` log entry SHALL additionally include the target file path in a `path` field and the error's message (the OS error string) in a `detail` field, in addition to the existing `video_id` and `reason` fields.

#### Scenario: Save failure logged with path and detail
- **WHEN** a transcript save fails
- **THEN** the failure log entry includes `path` set to the file path that was attempted to be written and `detail` set to the error's message
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-014
  - **File:** tests/test_persistence.py::test_failed_save_includes_path_and_detail
  - **Command:** python -m pytest tests/test_persistence.py::test_failed_save_includes_path_and_detail -q
  - **Pass:** exit code 0, no skipped tests
