# Spec Delta

## MODIFIED Requirements

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
