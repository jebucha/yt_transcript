# Spec Delta

## MODIFIED Requirements

### Requirement: Single transcript read endpoint
`GET /api/transcripts/{name}` SHALL return 200 with the transcript whose file name matches, read from the transcript directory. The returned text SHALL be exactly the file's UTF-8 content — for a file written by the app, the video's watch URL as the first line, followed by the transcript text and a single trailing newline — so the read result round-trips byte-for-byte with the saved file.

#### Scenario: Known transcript is returned
- **WHEN** the transcript directory contains `the_end_of_llms_ncm.txt` whose content is `Hello there.\n` and a request is made for that file name
- **THEN** the response is 200 and its text equals `Hello there.\n`
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-007
  - **File:** tests/test_transcript_library.py::test_read_returns_file_content
  - **Command:** python -m pytest tests/test_transcript_library.py::test_read_returns_file_content -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Fetched transcript round-trips through the store
- **WHEN** a fetch succeeds (persisting a file) and the same transcript is then read back by file name
- **THEN** the read text equals the video's watch URL as the first line, followed by the fetched transcript text, and a single trailing newline
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-008
  - **File:** tests/test_transcript_library.py::test_read_roundtrips_after_successful_fetch
  - **Command:** python -m pytest tests/test_transcript_library.py::test_read_roundtrips_after_successful_fetch -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Unicode file names are read
- **WHEN** the transcript directory contains `café_bär_über_alles.txt`
- **THEN** a request for that (percent-encoded) name returns 200 with the file's content
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-009
  - **File:** tests/test_transcript_library.py::test_read_unicode_file_name
  - **Command:** python -m pytest tests/test_transcript_library.py::test_read_unicode_file_name -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Unknown name is a 404
- **WHEN** the requested file name does not exist in the transcript directory
- **THEN** the response is 404
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-010
  - **File:** tests/test_transcript_library.py::test_read_unknown_name_returns_404
  - **Command:** python -m pytest tests/test_transcript_library.py::test_read_unknown_name_returns_404 -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Name containing a path separator is rejected
- **WHEN** the requested file name contains a path separator (e.g. `../outside.txt`)
- **THEN** the response is 400 and no file outside the transcript directory is read
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-011
  - **File:** tests/test_transcript_library.py::test_read_name_with_path_separator_returns_400
  - **Command:** python -m pytest tests/test_transcript_library.py::test_read_name_with_path_separator_returns_400 -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Dot-dot name is rejected
- **WHEN** the requested file name is `..` or contains a `..` component
- **THEN** the response is 400 and no file outside the transcript directory is read
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-012
  - **File:** tests/test_transcript_library.py::test_read_dotdot_name_returns_400
  - **Command:** python -m pytest tests/test_transcript_library.py::test_read_dotdot_name_returns_400 -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Non-.txt name is not served
- **WHEN** the requested file name does not end in `.txt`, even if a file of that name exists in the directory
- **THEN** the response is 404
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-013
  - **File:** tests/test_transcript_library.py::test_read_non_txt_name_returns_404
  - **Command:** python -m pytest tests/test_transcript_library.py::test_read_non_txt_name_returns_404 -q
  - **Pass:** exit code 0, no skipped tests
