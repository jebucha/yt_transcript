# Spec Delta

## MODIFIED Requirements

### Requirement: Transcript file persistence
On every successful transcript fetch, the system SHALL write the transcript to a plain-text `.txt` file in the configured transcript directory, encoded as UTF-8. The file SHALL consist of the video's watch URL (`https://www.youtube.com/watch?v=<video_id>`) as its first line, followed by the same clean plain-text transcript returned in the response, and a single trailing newline. A failed fetch SHALL NOT create or modify any file.

#### Scenario: Successful fetch writes the file
- **WHEN** a transcript request succeeds for video `dQw4w9WgXcQ` whose title is `The End of LLMs? (NCM)`
- **THEN** a file `the_end_of_llms_ncm.txt` exists in the transcript directory and its contents equal the line `https://www.youtube.com/watch?v=dQw4w9WgXcQ`, then the transcript text from the response, followed by a single trailing newline
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-PERSISTENCE-001
  - **File:** tests/test_persistence.py::test_successful_fetch_writes_file
  - **Command:** python -m pytest tests/test_persistence.py::test_successful_fetch_writes_file -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Header line is the reconstructed watch URL
- **WHEN** a transcript is saved for video `dQw4w9WgXcQ`
- **THEN** the first line of the written file is `https://www.youtube.com/watch?v=dQw4w9WgXcQ` and the remainder of the file equals the transcript text plus a single trailing newline
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-PERSISTENCE-012
  - **File:** tests/test_persistence.py::test_saved_file_starts_with_video_url_header
  - **Command:** python -m pytest tests/test_persistence.py::test_saved_file_starts_with_video_url_header -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Failed fetch writes nothing
- **WHEN** a transcript request fails with any error code (`INVALID_URL`, `VIDEO_UNAVAILABLE`, `NO_CAPTIONS`, `UPSTREAM_FAILURE`, or `BUSY`)
- **THEN** no file is created or modified in the transcript directory
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-PERSISTENCE-002
  - **File:** tests/test_persistence.py::test_failed_fetch_writes_no_file
  - **Command:** python -m pytest tests/test_persistence.py::test_failed_fetch_writes_no_file -q
  - **Pass:** exit code 0, no skipped tests
