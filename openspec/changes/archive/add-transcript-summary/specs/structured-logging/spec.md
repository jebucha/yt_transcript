# Spec Delta

## ADDED Requirements

### Requirement: Summary operation logging
The application SHALL log each summarization as a single structured JSON event: `summary_completed` at info level on success, `summary_failed` at error level on failure. Both carry the provider id, model id, and duration in milliseconds; success events additionally carry the transcript and summary character counts, and failure events carry a machine-readable reason and a human-readable message. Log entries SHALL NOT contain transcript or summary content, config file contents, or API keys.

#### Scenario: Successful summarization logged
- **WHEN** a summarization succeeds
- **THEN** one log entry records the `summary_completed` event with the provider id, model id, duration, transcript character count, and summary character count
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-015
  - **File:** tests/test_transcript_summarization.py::test_summary_completed_logged
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_summary_completed_logged -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Failed summarization logged
- **WHEN** a summarization fails because the backend is unreachable
- **THEN** one log entry records the `summary_failed` event at error level with the provider id, model id, the failure reason, and the failure detail
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-016
  - **File:** tests/test_transcript_summarization.py::test_summary_failed_logged
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_summary_failed_logged -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: No transcript content or keys in summary logs
- **WHEN** a summarization succeeds or fails and the transcript text and the provider's API key are non-empty
- **THEN** no log entry contains any part of the transcript text, the summary text, or the API key
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-017
  - **File:** tests/test_transcript_summarization.py::test_summary_logs_omit_content_and_keys
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_summary_logs_omit_content_and_keys -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Summary save and config-load failure logging
A failed summary save SHALL be logged as a `summary_save_failed` error event carrying the transcript name, the target path, and the OS error detail. A failed provider-config load SHALL be logged as a `config_load_failed` error event carrying the config path and the parse error detail, never the file's contents. These events SHALL NOT contain transcript or summary content or API keys.

#### Scenario: Summary save failure logged
- **WHEN** the transcript directory is not writable and a summarization succeeds at the backend
- **THEN** one error-level log entry records the `summary_save_failed` event with the transcript name, the target path, and the OS error detail, and the summarization's response is still successful
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-018
  - **File:** tests/test_transcript_summarization.py::test_summary_save_failure_logged
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_summary_save_failure_logged -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Config load failure logged
- **WHEN** the provider config file contains invalid JSON and a request needs the provider list
- **THEN** one error-level log entry records the `config_load_failed` event with the config path and the parse error detail, and no log entry contains the file's contents
- **Test Requirement**
  - **ID:** T-STRUCTURED-LOGGING-019
  - **File:** tests/test_transcript_summarization.py::test_config_load_failure_logged
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_config_load_failure_logged -q
  - **Pass:** exit code 0, no skipped tests
