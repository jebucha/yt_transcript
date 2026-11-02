# transcript-library Specification

## Purpose

Read access to persisted transcripts: a read-only list and single-transcript API over the transcript directory, plus a web interface section that shows the saved transcripts, displays the clicked one in the existing panel, and downloads it as a `.txt` file on the user's machine.

## Requirements

### Requirement: Transcript list endpoint
The system SHALL expose a read-only `GET /api/transcripts` endpoint that returns a JSON object containing a `transcripts` array of the persisted transcripts in the configured transcript directory. Each entry SHALL contain the file name, the size in bytes, and the last-modified time. Entries SHALL be ordered by last-modified time, most recent first, and only `.txt` files SHALL be listed.

#### Scenario: Saved transcripts are listed
- **WHEN** the transcript directory contains `the_end_of_llms_ncm.txt` and `another_video.txt`
- **THEN** `GET /api/transcripts` returns 200 with one entry per file, each carrying the file name, its size in bytes, and its last-modified time
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-001
  - **File:** tests/test_transcript_library.py::test_list_returns_name_size_and_modified
  - **Command:** python -m pytest tests/test_transcript_library.py::test_list_returns_name_size_and_modified -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Most recent transcript first
- **WHEN** two transcripts are saved and one was written more recently than the other
- **THEN** the list is ordered by last-modified time, most recent first
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-002
  - **File:** tests/test_transcript_library.py::test_list_sorted_most_recent_first
  - **Command:** python -m pytest tests/test_transcript_library.py::test_list_sorted_most_recent_first -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Non-.txt files are excluded
- **WHEN** the transcript directory contains a file that does not end in `.txt`
- **THEN** that file does not appear in the list
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-003
  - **File:** tests/test_transcript_library.py::test_list_excludes_non_txt_files
  - **Command:** python -m pytest tests/test_transcript_library.py::test_list_excludes_non_txt_files -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Empty directory lists nothing
- **WHEN** the transcript directory exists but contains no `.txt` files
- **THEN** the `transcripts` array is empty
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-004
  - **File:** tests/test_transcript_library.py::test_list_empty_directory_returns_empty_array
  - **Command:** python -m pytest tests/test_transcript_library.py::test_list_empty_directory_returns_empty_array -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Unusable directory is an empty list
When the transcript directory does not exist, is not a directory, or cannot be read, `GET /api/transcripts` SHALL return 200 with an empty `transcripts` array. The read side SHALL NOT create the directory and SHALL NOT return an error status for these conditions.

#### Scenario: Missing directory returns an empty list
- **WHEN** the transcript directory does not exist
- **THEN** the list returns 200 with an empty `transcripts` array and the directory is not created
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-005
  - **File:** tests/test_transcript_library.py::test_missing_directory_returns_empty_array
  - **Command:** python -m pytest tests/test_transcript_library.py::test_missing_directory_returns_empty_array -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Non-directory path returns an empty list
- **WHEN** the configured transcript path exists but is a file rather than a directory
- **THEN** the list returns 200 with an empty `transcripts` array
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-006
  - **File:** tests/test_transcript_library.py::test_non_directory_path_returns_empty_array
  - **Command:** python -m pytest tests/test_transcript_library.py::test_non_directory_path_returns_empty_array -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Single transcript read endpoint
`GET /api/transcripts/{name}` SHALL return 200 with the transcript whose file name matches, read from the transcript directory. The returned text SHALL be exactly the file's UTF-8 content — for a file written by the app, the transcript text plus one trailing newline — so the read result round-trips byte-for-byte with the saved file.

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
- **THEN** the read text equals the fetched transcript text plus a single trailing newline
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

### Requirement: Traversal-safe name handling
The read endpoint SHALL reject a requested name that is not a plain file name — containing a path separator or a `..` path component — with a 400 status, without reading any file. A requested name that resolves outside the transcript directory SHALL NOT be served.

#### Scenario: Name containing a path separator is rejected
- **WHEN** the requested name contains a path separator (e.g. `../outside.txt`)
- **THEN** the response is 400 and no file outside the transcript directory is read
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-011
  - **File:** tests/test_transcript_library.py::test_read_name_with_path_separator_returns_400
  - **Command:** python -m pytest tests/test_transcript_library.py::test_read_name_with_path_separator_returns_400 -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Dot-dot name is rejected
- **WHEN** the requested name is `..` or contains a `..` component
- **THEN** the response is 400 and no file outside the transcript directory is read
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-012
  - **File:** tests/test_transcript_library.py::test_read_dotdot_name_returns_400
  - **Command:** python -m pytest tests/test_transcript_library.py::test_read_dotdot_name_returns_400 -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Non-.txt name is not served
- **WHEN** the requested name does not end in `.txt`, even if a file of that name exists in the directory
- **THEN** the response is 404
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-013
  - **File:** tests/test_transcript_library.py::test_read_non_txt_name_returns_404
  - **Command:** python -m pytest tests/test_transcript_library.py::test_read_non_txt_name_returns_404 -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Read endpoints have no side effects
The list and read endpoints SHALL NOT create, modify, or delete files, SHALL NOT create the transcript directory, and SHALL NOT be subject to the single-flight fetch limit: they SHALL NOT return `BUSY` and SHALL NOT invoke the fetch chain, even while a fetch is in flight.

#### Scenario: List and read succeed while a fetch is in flight
- **WHEN** a transcript fetch is in progress and a list or read request arrives
- **THEN** the list/read request completes normally (not 503 `BUSY`) and does not invoke the fetch chain
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-014
  - **File:** tests/test_transcript_library.py::test_reads_during_in_flight_fetch_succeed
  - **Command:** python -m pytest tests/test_transcript_library.py::test_reads_during_in_flight_fetch_succeed -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Reading does not modify the file
- **WHEN** a transcript is read successfully
- **THEN** the file's content is unchanged after the read
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-015
  - **File:** tests/test_transcript_library.py::test_read_does_not_modify_file
  - **Command:** python -m pytest tests/test_transcript_library.py::test_read_does_not_modify_file -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Saved transcripts list section
The web interface SHALL display a "Saved transcripts" section containing a scrollable list of the persisted transcripts, most recent first, each row showing a display name and the date of the last modification. The list SHALL load on page load and after each successful fetch, and the section SHALL provide a manual refresh affordance; there SHALL be no automatic polling. When no transcripts are saved, the section SHALL show an empty state instead of an empty list.

#### Scenario: Saved transcripts appear in the list
- **WHEN** the transcript directory contains saved transcripts and the page is loaded
- **THEN** the section lists each saved transcript, most recent first, inside a scrollable area
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-016
  - **File:** tests/e2e/test_ui.py::test_saved_list_shows_transcripts
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_saved_list_shows_transcripts -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Display name is prettified, request uses the real name
- **WHEN** a saved transcript's file name is `the_end_of_llms_ncm.txt`
- **THEN** the list row shows a prettified rendering of the name (underscores replaced with spaces, the trailing `.txt` extension stripped, and words capitalized) and any request triggered by that row targets the real file name `the_end_of_llms_ncm.txt`
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-017
  - **File:** tests/e2e/test_ui.py::test_saved_list_prettified_display_name
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_saved_list_prettified_display_name -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Empty state when nothing is saved
- **WHEN** no transcripts are saved
- **THEN** the section shows an empty state message and no list rows
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-018
  - **File:** tests/e2e/test_ui.py::test_saved_list_empty_state
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_saved_list_empty_state -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Long lists scroll
- **WHEN** more transcripts are saved than fit in the visible area of the section
- **THEN** the list scrolls without the page layout breaking
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-019
  - **File:** tests/e2e/test_ui.py::test_saved_list_scrolls
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_saved_list_scrolls -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: List refreshes after a successful fetch
- **WHEN** a transcript fetch succeeds
- **THEN** the list reloads and includes the newly saved transcript
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-020
  - **File:** tests/e2e/test_ui.py::test_saved_list_updates_after_fetch
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_saved_list_updates_after_fetch -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Refresh affordance reloads the list
- **WHEN** a new transcript file appears in the transcript directory without a fetch, and the user triggers the section's refresh affordance
- **THEN** the list is re-fetched and now includes the new transcript
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-026
  - **File:** tests/e2e/test_ui.py::test_saved_list_manual_refresh
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_saved_list_manual_refresh -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: No automatic polling
- **WHEN** the page is loaded and no fetch or refresh is triggered
- **THEN** the section makes exactly one list request on load and issues no further automatic list requests
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-027
  - **File:** tests/e2e/test_ui.py::test_saved_list_does_not_poll
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_saved_list_does_not_poll -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Click to display a saved transcript
Clicking a list row SHALL load that transcript and display its text in the existing transcript panel, showing the transcript's name as the title, with the existing copy behavior available. Insertion of the transcript text and its name into the page SHALL be as plain text only (for example, via `textContent`), never as HTML. If the transcript can no longer be loaded, the interface SHALL display an error message without breaking the page.

#### Scenario: Clicking a row displays the transcript
- **WHEN** the user clicks a saved transcript in the list
- **THEN** the transcript text is displayed in the transcript panel, the transcript's name is shown as the title, and the copy button is enabled
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-021
  - **File:** tests/e2e/test_ui.py::test_click_saved_transcript_displays_it
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_click_saved_transcript_displays_it -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Markup-like transcript content is not rendered
- **WHEN** a saved transcript's text contains HTML-like markup (for example a `<script>` tag)
- **THEN** the markup is displayed as plain text, not rendered or executed
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-022
  - **File:** tests/e2e/test_ui.py::test_saved_transcript_html_shown_as_text
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_saved_transcript_html_shown_as_text -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Clicking a deleted transcript shows an error
- **WHEN** the user clicks a row whose file was removed from the transcript directory after the list was loaded
- **THEN** an error message is displayed and the page remains usable
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-023
  - **File:** tests/e2e/test_ui.py::test_click_deleted_saved_transcript_shows_error
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_click_deleted_saved_transcript_shows_error -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Download a saved transcript
The interface SHALL provide a download action for the displayed transcript that saves it as a `.txt` file on the user's machine, named after the transcript's file name in the transcript directory, with content identical to the persisted file. The download SHALL be performed client-side and SHALL work over plain HTTP, not depending on HTTPS-only browser features.

#### Scenario: Download saves the transcript file
- **WHEN** the user displays a saved transcript and triggers the download
- **THEN** the browser downloads a `.txt` file named after the transcript's file name whose content equals the file's content in the transcript directory
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-024
  - **File:** tests/e2e/test_ui.py::test_download_saved_transcript_downloads_file
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_download_saved_transcript_downloads_file -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Download over plain HTTP
- **WHEN** the app is reached at `http://<server-ip>:<port>` and the user triggers the download
- **THEN** the `.txt` file is downloaded successfully without HTTPS
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-LIBRARY-025
  - **File:** tests/e2e/test_ui.py::test_download_over_plain_http
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_download_over_plain_http -q
  - **Pass:** exit code 0, no skipped tests
