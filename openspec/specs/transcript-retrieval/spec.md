# transcript-retrieval Specification

## Purpose

Accepts a YouTube video URL and returns its caption text as a clean plain-text transcript, using a primary fetcher with an automatic fallback, and producing distinct, actionable errors for every failure mode.

## Requirements

### Requirement: YouTube video URL acceptance
The transcript endpoint SHALL accept a YouTube video URL in the standard watch form (`youtube.com/watch?v=<id>`), the `youtu.be/<id>` short form, and a bare video ID, and SHALL parse it to the video ID used for fetching.

#### Scenario: Standard watch URL
- **WHEN** the endpoint receives `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
- **THEN** it is parsed to video ID `dQw4w9WgXcQ` and the fetch proceeds
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-001
  - **File:** tests/test_url_parsing.py::test_standard_watch_url
  - **Command:** python -m pytest tests/test_url_parsing.py::test_standard_watch_url -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Short link
- **WHEN** the endpoint receives `https://youtu.be/dQw4w9WgXcQ`
- **THEN** it is parsed to video ID `dQw4w9WgXcQ` and the fetch proceeds
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-002
  - **File:** tests/test_url_parsing.py::test_short_link
  - **Command:** python -m pytest tests/test_url_parsing.py::test_short_link -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Bare video ID
- **WHEN** the endpoint receives the bare 11-character video ID `dQw4w9WgXcQ`
- **THEN** the fetch proceeds for that video
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-003
  - **File:** tests/test_url_parsing.py::test_bare_video_id
  - **Command:** python -m pytest tests/test_url_parsing.py::test_bare_video_id -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Rejection of invalid input
The transcript endpoint SHALL reject input that is not a recognizable YouTube video reference with an `INVALID_URL` error and HTTP 400, without contacting YouTube.

#### Scenario: Non-YouTube URL
- **WHEN** the endpoint receives `https://vimeo.com/123456789`
- **THEN** it responds with HTTP 400 and error code `INVALID_URL` and no YouTube request is made
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-004
  - **File:** tests/test_url_parsing.py::test_non_youtube_url_rejected_without_fetch
  - **Command:** python -m pytest tests/test_url_parsing.py::test_non_youtube_url_rejected_without_fetch -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Empty or malformed input
- **WHEN** the endpoint receives an empty string or a value with no recognizable video ID
- **THEN** it responds with HTTP 400 and error code `INVALID_URL`
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-005
  - **File:** tests/test_url_parsing.py::test_empty_or_malformed_input_rejected
  - **Command:** python -m pytest tests/test_url_parsing.py::test_empty_or_malformed_input_rejected -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Caption-track retrieval
The system SHALL retrieve the video's caption text using caption tracks only (no audio download, no speech-to-text), preferring manually created subtitles over auto-generated ones when multiple tracks are available.

#### Scenario: Manual captions preferred
- **WHEN** the video has both a manual and an auto-generated caption track in the preferred language
- **THEN** the manual track is used
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-006
  - **File:** tests/test_primary_fetcher.py::test_manual_track_preferred
  - **Command:** python -m pytest tests/test_primary_fetcher.py::test_manual_track_preferred -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Auto-generated captions used
- **WHEN** the video has only an auto-generated caption track
- **THEN** that track is used for the transcript
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-007
  - **File:** tests/test_primary_fetcher.py::test_auto_generated_track_used
  - **Command:** python -m pytest tests/test_primary_fetcher.py::test_auto_generated_track_used -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Language fallback and reporting
The system SHALL prefer English caption tracks; when no English track exists but other-language tracks do, it SHALL return the first available track and report the actual language used in the response metadata.

#### Scenario: English track available
- **WHEN** the video has an English caption track
- **THEN** the response reports `language` as English
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-008
  - **File:** tests/test_primary_fetcher.py::test_english_track_preferred
  - **Command:** python -m pytest tests/test_primary_fetcher.py::test_english_track_preferred -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Only a non-English track exists
- **WHEN** the video has caption tracks only in German
- **THEN** the transcript is returned from the German track and the response reports the German language code
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-009
  - **File:** tests/test_primary_fetcher.py::test_non_english_track_reported
  - **Command:** python -m pytest tests/test_primary_fetcher.py::test_non_english_track_reported -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Transcript output format
The system SHALL respond to a successful fetch with the transcript as plain text (timestamps removed, HTML entities decoded) plus metadata containing the video ID, video title, the language code actually used, which fetcher source produced the result, and the transcript's derived file name (the `.txt` name the transcript is persisted under, computed with the same title-based derivation as persistence).

#### Scenario: Successful fetch response
- **WHEN** a transcript is fetched successfully
- **THEN** the response contains the plain transcript text, the video ID, the video title, the language code, and the source identifier, and the text contains no timestamp markers or VTT/SSML markup
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-010
  - **File:** tests/test_primary_fetcher.py::test_output_is_clean_plain_text
  - **Command:** python -m pytest tests/test_primary_fetcher.py::test_output_is_clean_plain_text -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Response name matches the persisted file name
- **WHEN** a transcript for a video whose title is `The End of LLMs? (NCM)` (video `dQw4w9WgXcQ`) is fetched successfully
- **THEN** the response's file-name field is `the_end_of_llms_ncm.txt`, the exact name the persistence layer writes the file under
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-017
  - **File:** tests/test_primary_fetcher.py::test_response_includes_derived_name
  - **Command:** python -m pytest tests/test_primary_fetcher.py::test_response_includes_derived_name -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Fallback fetcher
When the primary fetcher fails with an upstream error (rate limiting, IP blocking, HTTP failure, or malformed upstream response), the system SHALL retry the fetch once using the fallback fetcher (yt-dlp) and report the source that succeeded.

#### Scenario: Primary fails, fallback succeeds
- **WHEN** the primary fetcher fails with an upstream error and the fallback fetcher succeeds
- **THEN** the response is returned with the source identifier set to the fallback source
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-011
  - **File:** tests/test_fetch_chain.py::test_primary_fails_fallback_succeeds
  - **Command:** python -m pytest tests/test_fetch_chain.py::test_primary_fails_fallback_succeeds -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Both fetchers fail
- **WHEN** the primary fetcher fails and the fallback fetcher also fails with an upstream error
- **THEN** the system responds with an `UPSTREAM_FAILURE` error and HTTP 502
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-012
  - **File:** tests/test_fetch_chain.py::test_both_fetchers_fail_upstream_failure
  - **Command:** python -m pytest tests/test_fetch_chain.py::test_both_fetchers_fail_upstream_failure -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Error taxonomy
The system SHALL distinguish at least the following failure modes, each with a machine-readable error code and a human-readable message: `INVALID_URL` (400), `VIDEO_UNAVAILABLE` for private, deleted, or region-locked videos (404), `NO_CAPTIONS` for videos with no caption tracks in any language (404), and `UPSTREAM_FAILURE` when all fetchers fail (502).

#### Scenario: Private video
- **WHEN** the video exists but is private
- **THEN** the response is HTTP 404 with error code `VIDEO_UNAVAILABLE`
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-013
  - **File:** tests/test_error_taxonomy.py::test_private_video_video_unavailable
  - **Command:** python -m pytest tests/test_error_taxonomy.py::test_private_video_video_unavailable -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Video has no captions
- **WHEN** the video is public but has no caption tracks in any language
- **THEN** the response is HTTP 404 with error code `NO_CAPTIONS`
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-014
  - **File:** tests/test_error_taxonomy.py::test_no_captions
  - **Command:** python -m pytest tests/test_error_taxonomy.py::test_no_captions -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Transient upstream outage
- **WHEN** both fetchers fail because YouTube rejects or throttles requests
- **THEN** the response is HTTP 502 with error code `UPSTREAM_FAILURE`
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-015
  - **File:** tests/test_error_taxonomy.py::test_transient_upstream_outage
  - **Command:** python -m pytest tests/test_error_taxonomy.py::test_transient_upstream_outage -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Bounded upstream concurrency
The system SHALL run at most one YouTube fetch chain at a time; a transcript request arriving while another fetch is in flight SHALL be rejected with HTTP 503 and an error code `BUSY` rather than queued without bound.

#### Scenario: Concurrent request rejected
- **WHEN** a second transcript request arrives while a first fetch chain is still in flight
- **THEN** the second request receives HTTP 503 with error code `BUSY`
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-RETRIEVAL-016
  - **File:** tests/test_fetch_chain.py::test_concurrent_request_busy
  - **Command:** python -m pytest tests/test_fetch_chain.py::test_concurrent_request_busy -q
  - **Pass:** exit code 0, no skipped tests
