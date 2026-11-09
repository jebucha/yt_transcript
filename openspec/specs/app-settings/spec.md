# app-settings Specification

## Purpose

Persists durable application-level UI preferences server-side as a small JSON file in the transcript directory, exposed through a read endpoint and a write endpoint, with a safe default when the file is absent or unusable.

## Requirements

### Requirement: Settings read endpoint
The application SHALL expose a read-only `GET /api/settings` endpoint returning 200 with an `autoSummarize` boolean field, read from `settings.json` in the transcript directory at request time so edits on disk take effect without a restart.

#### Scenario: Stored flag is returned
- **WHEN** `settings.json` in the transcript directory contains `{"autoSummarize": true}` and `GET /api/settings` is requested
- **THEN** the response is 200 with `autoSummarize` true
- **Test Requirement**
  - **ID:** T-APP-SETTINGS-001
  - **File:** tests/test_settings.py::test_settings_read_returns_stored_flag
  - **Command:** python -m pytest tests/test_settings.py::test_settings_read_returns_stored_flag -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Settings edits take effect without a restart
- **WHEN** `settings.json` is changed on disk after the application has served a `GET /api/settings` request
- **THEN** the next `GET /api/settings` reflects the new file content
- **Test Requirement**
  - **ID:** T-APP-SETTINGS-004
  - **File:** tests/test_settings.py::test_settings_edit_takes_effect_without_restart
  - **Command:** python -m pytest tests/test_settings.py::test_settings_edit_takes_effect_without_restart -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Settings default when unusable
A missing settings file, an unreadable file, malformed JSON, or a non-boolean `autoSummarize` value SHALL yield `autoSummarize: false` from `GET /api/settings` — a safe default, never an error response. A malformed or unreadable file SHALL additionally be recorded in the log, and file contents SHALL NOT be echoed into the response.

#### Scenario: Missing settings file defaults to off
- **WHEN** the transcript directory contains no `settings.json` and `GET /api/settings` is requested
- **THEN** the response is 200 with `autoSummarize` false and no file is created
- **Test Requirement**
  - **ID:** T-APP-SETTINGS-002
  - **File:** tests/test_settings.py::test_settings_read_missing_file_defaults_off
  - **Command:** python -m pytest tests/test_settings.py::test_settings_read_missing_file_defaults_off -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Unusable settings file is not an error
- **WHEN** `settings.json` contains invalid JSON or a non-boolean `autoSummarize` value and `GET /api/settings` is requested
- **THEN** the response is 200 with `autoSummarize` false, the failure is visible in the log for the malformed-JSON case without the file contents appearing in the response, and no request crashes
- **Test Requirement**
  - **ID:** T-APP-SETTINGS-003
  - **File:** tests/test_settings.py::test_settings_read_unusable_file_defaults_off
  - **Command:** python -m pytest tests/test_settings.py::test_settings_read_unusable_file_defaults_off -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Settings write endpoint
The application SHALL expose `POST /api/settings` accepting a JSON body whose `autoSummarize` field is a boolean, persisting the setting to `settings.json` in the transcript directory and returning 200 with the persisted `autoSummarize` value. A body that is not a JSON object or whose `autoSummarize` is missing or not a boolean SHALL be rejected with 400 and error code `INVALID_BODY` without writing the file.

#### Scenario: Write persists and echoes the flag
- **WHEN** `POST /api/settings` is called with `{"autoSummarize": true}`
- **THEN** the response is 200 with `autoSummarize` true, `settings.json` in the transcript directory contains the setting, and a subsequent `GET /api/settings` returns true
- **Test Requirement**
  - **ID:** T-APP-SETTINGS-005
  - **File:** tests/test_settings.py::test_settings_write_persists_and_echoes
  - **Command:** python -m pytest tests/test_settings.py::test_settings_write_persists_and_echoes -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Invalid body is rejected without a write
- **WHEN** `POST /api/settings` is called with a non-object body, with `autoSummarize` missing, or with a non-boolean `autoSummarize`
- **THEN** the response is 400 with error code `INVALID_BODY` and the settings file content is unchanged
- **Test Requirement**
  - **ID:** T-APP-SETTINGS-006
  - **File:** tests/test_settings.py::test_settings_write_invalid_body_rejected
  - **Command:** python -m pytest tests/test_settings.py::test_settings_write_invalid_body_rejected -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Settings write failure resilience
When the settings file cannot be written, `POST /api/settings` SHALL return 500 with error code `WRITE_FAILED`, the failure SHALL be recorded in the log, and `GET /api/settings` SHALL keep returning the previously stored setting.

#### Scenario: Unwritable settings leave the old value readable
- **WHEN** the settings file cannot be written (for example the transcript directory is missing or read-only) and `POST /api/settings` is called with a valid body
- **THEN** the response is 500 with error code `WRITE_FAILED`, the failure is recorded in the log, and `GET /api/settings` still returns the previously stored value (or false when none was stored)
- **Test Requirement**
  - **ID:** T-APP-SETTINGS-007
  - **File:** tests/test_settings.py::test_settings_write_unwritable_directory_fails
  - **Command:** python -m pytest tests/test_settings.py::test_settings_write_unwritable_directory_fails -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Settings file isolation and independence
The settings SHALL be stored as `settings.json` in the transcript directory and SHALL NOT appear in `GET /api/transcripts` (the saved list contains only `.txt` files). The settings endpoints SHALL NOT invoke the fetch chain and SHALL NOT be subject to the single-flight fetch limit.

#### Scenario: Settings file is not listed as a transcript
- **WHEN** the transcript directory contains `settings.json` and `GET /api/transcripts` is requested
- **THEN** the response does not list `settings.json`
- **Test Requirement**
  - **ID:** T-APP-SETTINGS-008
  - **File:** tests/test_settings.py::test_settings_file_excluded_from_transcript_list
  - **Command:** python -m pytest tests/test_settings.py::test_settings_file_excluded_from_transcript_list -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Settings endpoints are not subject to the fetch limit
- **WHEN** a transcript fetch is in progress and a `GET /api/settings` or `POST /api/settings` request arrives
- **THEN** the settings request proceeds (it is not rejected as busy) and does not invoke the fetch chain
- **Test Requirement**
  - **ID:** T-APP-SETTINGS-009
  - **File:** tests/test_settings.py::test_settings_during_in_flight_fetch_succeeds
  - **Command:** python -m pytest tests/test_settings.py::test_settings_during_in_flight_fetch_succeeds -q
  - **Pass:** exit code 0, no skipped tests
