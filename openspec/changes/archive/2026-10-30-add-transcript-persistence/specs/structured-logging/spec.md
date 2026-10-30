# Spec Delta

## ADDED Requirements

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
