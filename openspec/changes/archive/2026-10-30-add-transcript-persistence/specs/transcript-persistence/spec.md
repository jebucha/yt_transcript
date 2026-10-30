# Spec Delta

## Purpose

Persists each successfully fetched YouTube transcript to a plain-text file on disk, named after the video title, so operators keep a durable, machine-readable record of fetched transcripts without a database or extra service.

## ADDED Requirements

### Requirement: Transcript file persistence
On every successful transcript fetch, the system SHALL write the transcript text to a plain-text `.txt` file in the configured transcript directory. The file SHALL contain exactly the same clean plain-text transcript returned in the response, encoded as UTF-8, followed by a single trailing newline. A failed fetch SHALL NOT create or modify any file.

#### Scenario: Successful fetch writes the file
- **WHEN** a transcript request succeeds for a video whose title is `The End of LLMs? (NCM)`
- **THEN** a file `the_end_of_llms_ncm.txt` exists in the transcript directory and its contents equal the transcript text from the response plus a trailing newline
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-PERSISTENCE-001
  - **File:** tests/test_persistence.py::test_successful_fetch_writes_file
  - **Command:** python -m pytest tests/test_persistence.py::test_successful_fetch_writes_file -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Failed fetch writes nothing
- **WHEN** a transcript request fails with any error code (`INVALID_URL`, `VIDEO_UNAVAILABLE`, `NO_CAPTIONS`, `UPSTREAM_FAILURE`, or `BUSY`)
- **THEN** no file is created or modified in the transcript directory
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-PERSISTENCE-002
  - **File:** tests/test_persistence.py::test_failed_fetch_writes_no_file
  - **Command:** python -m pytest tests/test_persistence.py::test_failed_fetch_writes_no_file -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Title-based file name
The file name SHALL be derived from the video title by converting it to lowercase, replacing each run of one or more non-alphanumeric characters (any character that is not a Unicode letter or digit — including punctuation, whitespace, and symbols) with a single underscore, and trimming leading and trailing underscores; the `.txt` extension is appended. Unicode letters and digits are preserved, not transliterated, and the derived name SHALL NOT contain a path separator.

#### Scenario: Typical title
- **WHEN** the video title is `The End of LLMs? (NCM)`
- **THEN** the file name is `the_end_of_llms_ncm.txt`
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-PERSISTENCE-003
  - **File:** tests/test_persistence.py::test_filename_typical_title
  - **Command:** python -m pytest tests/test_persistence.py::test_filename_typical_title -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Path separator in title cannot escape the directory
- **WHEN** the video title is `Foo/Bar: The Story`
- **THEN** the derived file name is `foo_bar_the_story.txt` and contains no path separator, so writing it cannot create a file outside the transcript directory
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-PERSISTENCE-005
  - **File:** tests/test_persistence.py::test_filename_slash_in_title_stays_in_directory
  - **Command:** python -m pytest tests/test_persistence.py::test_filename_slash_in_title_stays_in_directory -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Unicode title preserved
- **WHEN** the video title is `Café & Bär: Über alles`
- **THEN** the file name is `café_bär_über_alles.txt`
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-PERSISTENCE-006
  - **File:** tests/test_persistence.py::test_filename_unicode_title_preserved
  - **Command:** python -m pytest tests/test_persistence.py::test_filename_unicode_title_preserved -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Fallback and truncation for degenerate names
A title that sanitizes to the empty string SHALL use the video ID as the file name. A derived name longer than the 255-byte file-name limit SHALL be truncated to fit, with the video ID appended so the resulting name still fits within the limit.

#### Scenario: Punctuation-only title falls back to video ID
- **WHEN** the video title is `???`
- **THEN** the file name is the video ID with the `.txt` extension (for video `dQw4w9WgXcQ`: `dQw4w9WgXcQ.txt`)
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-PERSISTENCE-004
  - **File:** tests/test_persistence.py::test_filename_punctuation_only_title_falls_back_to_video_id
  - **Command:** python -m pytest tests/test_persistence.py::test_filename_punctuation_only_title_falls_back_to_video_id -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Overlong title truncated with video ID suffix
- **WHEN** the video title sanitizes to more than 255 bytes
- **THEN** the file name is truncated to fit within 255 bytes with the video ID appended, and the file is written under that name
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-PERSISTENCE-007
  - **File:** tests/test_persistence.py::test_filename_overlong_title_truncated_with_video_id
  - **Command:** python -m pytest tests/test_persistence.py::test_filename_overlong_title_truncated_with_video_id -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Overwrite on re-fetch
When a fetch succeeds and the derived file name already exists in the transcript directory, the existing file SHALL be overwritten with the newly fetched transcript text. Distinct videos whose titles derive the same file name are not disambiguated; the most recent write wins.

#### Scenario: Re-fetch replaces the file
- **WHEN** the same video is fetched successfully a second time
- **THEN** the pre-existing file is replaced and contains the transcript text of the second fetch
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-PERSISTENCE-008
  - **File:** tests/test_persistence.py::test_refetch_overwrites_existing_file
  - **Command:** python -m pytest tests/test_persistence.py::test_refetch_overwrites_existing_file -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Distinct videos with the same title overwrite each other
- **WHEN** two different videos whose titles derive the same file name are both fetched successfully, in sequence
- **THEN** the file contains the transcript of the most recently fetched video (last write wins)
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-PERSISTENCE-011
  - **File:** tests/test_persistence.py::test_distinct_videos_same_title_last_write_wins
  - **Command:** python -m pytest tests/test_persistence.py::test_distinct_videos_same_title_last_write_wins -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Best-effort write behavior
A failure to write the transcript file — the transcript directory missing, unreadable, or unwritable, or any other write error — SHALL NOT change the HTTP response: the request SHALL still complete successfully with the same response body as if no file had been written, and the failure SHALL be reported only through a structured error log event (see the structured-logging specification).

#### Scenario: Unwritable directory does not fail the request
- **WHEN** a transcript request succeeds but the transcript directory is not writable
- **THEN** the HTTP response is still 200 with the transcript text and no transcript file is written
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-PERSISTENCE-009
  - **File:** tests/test_persistence.py::test_unwritable_directory_still_returns_transcript
  - **Command:** python -m pytest tests/test_persistence.py::test_unwritable_directory_still_returns_transcript -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Configurable transcript directory
The transcript directory SHALL be configurable through the `TRANSCRIPT_DIR` environment variable, with a default of `/transcripts`. The system SHALL NOT create the directory automatically; a missing directory is a write failure handled per the best-effort write behavior.

#### Scenario: Directory taken from environment
- **WHEN** `TRANSCRIPT_DIR` is set to a directory that exists
- **THEN** transcript files are written into that directory
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-PERSISTENCE-010
  - **File:** tests/test_persistence.py::test_directory_from_environment_variable
  - **Command:** python -m pytest tests/test_persistence.py::test_directory_from_environment_variable -q
  - **Pass:** exit code 0, no skipped tests
