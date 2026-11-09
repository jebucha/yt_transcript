# Spec Delta

## ADDED Requirements

### Requirement: Auto-summarize toggle control
The interface SHALL provide an "Auto-summarize" checkbox whose checked state reflects the `autoSummarize` application setting on page load. Toggling it SHALL persist the new value through the application settings endpoint. The checkbox SHALL be interactive only when at least one summarization provider is configured, and SHALL be disabled, like the Summarize button and provider picker, while a summarize request (manual or automatic) is in flight.

#### Scenario: Checkbox reflects the stored setting
- **WHEN** the page is loaded and the stored `autoSummarize` setting is true
- **THEN** the Auto-summarize checkbox is checked
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-043
  - **File:** tests/e2e/test_auto_summarize.py::test_checkbox_reflects_saved_setting_on_load
  - **Command:** python -m pytest tests/e2e/test_auto_summarize.py::test_checkbox_reflects_saved_setting_on_load -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Toggling persists across reload
- **WHEN** the user checks the Auto-summarize checkbox and the page is reloaded
- **THEN** the checkbox is checked again after the reload (the setting was persisted server-side)
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-044
  - **File:** tests/e2e/test_auto_summarize.py::test_toggle_persists_across_reload
  - **Command:** python -m pytest tests/e2e/test_auto_summarize.py::test_toggle_persists_across_reload -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Checkbox disabled when no providers are configured
- **WHEN** the page is loaded and no summarization providers are configured
- **THEN** the Auto-summarize checkbox is disabled
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-045
  - **File:** tests/e2e/test_auto_summarize.py::test_auto_checkbox_disabled_without_providers
  - **Command:** python -m pytest tests/e2e/test_auto_summarize.py::test_auto_checkbox_disabled_without_providers -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Failed settings write reverts the checkbox
- **WHEN** the user toggles the Auto-summarize checkbox and the settings write request fails
- **THEN** the checkbox returns to the last persisted value and no new setting is stored
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-055
  - **File:** tests/e2e/test_auto_summarize.py::test_toggle_reverts_on_failed_write
  - **Command:** python -m pytest tests/e2e/test_auto_summarize.py::test_toggle_reverts_on_failed_write -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Auto-summarize on fresh fetch
When auto-summarize is enabled and a fresh transcript fetch succeeds, the interface SHALL automatically submit the displayed transcript text and its derived file name to the summarize endpoint using the default provider's first model — the same target the provider picker pre-selects — without any user click. Displaying a saved transcript SHALL never trigger automatic summarization, and with the toggle off the fetch flow SHALL behave exactly as before.

#### Scenario: Automatic summarize fires after a fetch
- **WHEN** providers are configured, auto-summarize is enabled, a fetch succeeds, and the fetched transcript has no saved summary
- **THEN** a summarize request is sent without a click carrying the fetched text, the derived file name, the default provider id, and its first model id, and the returned summary is displayed in the summary panel
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-046
  - **File:** tests/e2e/test_auto_summarize.py::test_auto_summarize_fires_after_fetch
  - **Command:** python -m pytest tests/e2e/test_auto_summarize.py::test_auto_summarize_fires_after_fetch -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Busy state while auto-summarizing
- **WHEN** an automatic summarize request is in flight
- **THEN** the Summarize button, the provider picker, and the Auto-summarize checkbox are disabled and the loading indicator is shown, and they are restored when the response arrives
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-047
  - **File:** tests/e2e/test_auto_summarize.py::test_auto_summarize_shows_busy_state
  - **Command:** python -m pytest tests/e2e/test_auto_summarize.py::test_auto_summarize_shows_busy_state -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Saved transcript clicks never auto-fire
- **WHEN** auto-summarize is enabled and the user clicks a saved transcript without a saved summary
- **THEN** no summarize request is sent and the existing saved-summary load behavior is unchanged
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-048
  - **File:** tests/e2e/test_auto_summarize.py::test_saved_click_does_not_auto_fire
  - **Command:** python -m pytest tests/e2e/test_auto_summarize.py::test_saved_click_does_not_auto_fire -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Toggle off keeps the manual flow
- **WHEN** auto-summarize is disabled and a fetch succeeds
- **THEN** no summarize request is sent and the summary panel stays hidden until the user clicks Summarize
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-049
  - **File:** tests/e2e/test_auto_summarize.py::test_auto_off_fetch_does_not_summarize
  - **Command:** python -m pytest tests/e2e/test_auto_summarize.py::test_auto_off_fetch_does_not_summarize -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Auto-summarize skips an existing summary
When auto-summarize is enabled and a fresh fetch succeeds for a transcript whose derived file name already has a saved summary, the interface SHALL NOT call the summarize endpoint and SHALL load the existing saved summary into the summary panel as a best-effort read; a 404 or network failure leaves the panel hidden without any error display.

#### Scenario: Re-fetch of a summarized transcript shows the saved summary
- **WHEN** auto-summarize is enabled, a fetch succeeds for a transcript whose `<name>.summary` file already exists, and that summary is readable
- **THEN** no summarize request is sent and the summary panel shows the saved summary text
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-050
  - **File:** tests/e2e/test_auto_summarize.py::test_refetch_with_existing_summary_shows_saved
  - **Command:** python -m pytest tests/e2e/test_auto_summarize.py::test_refetch_with_existing_summary_shows_saved -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Fetch without a saved summary still auto-fires
- **WHEN** auto-summarize is enabled and a fetch succeeds for a transcript with no saved summary
- **THEN** the automatic summarize fires as specified by the auto-summarize on fresh fetch requirement
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-051
  - **File:** tests/e2e/test_auto_summarize.py::test_refetch_without_summary_auto_fires
  - **Command:** python -m pytest tests/e2e/test_auto_summarize.py::test_refetch_without_summary_auto_fires -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Auto-summarize failures are subdued
A failed automatic summarization SHALL NOT display the page's error banner: the interface SHALL show a subdued inline note near the summarize controls indicating the automatic summarization failed, the summary panel SHALL stay hidden, and the manual Summarize control SHALL remain enabled as the explicit retry path. Failures of manual summarization SHALL continue to display the cause-specific error banner.

#### Scenario: Backend failure during auto-summarize shows a note
- **WHEN** auto-summarize is enabled and the automatic summarize request fails with `PROVIDER_ERROR`
- **THEN** the error banner stays hidden, a subdued note is shown near the summarize controls, the summary panel stays hidden, and the Summarize button is enabled
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-052
  - **File:** tests/e2e/test_auto_summarize.py::test_auto_failure_shows_note_not_banner
  - **Command:** python -m pytest tests/e2e/test_auto_summarize.py::test_auto_failure_shows_note_not_banner -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Empty automatic summary shows the note, not an empty panel
- **WHEN** an automatic summarize response is 200 with an empty `summary` field
- **THEN** the summary panel stays hidden, the subdued note is shown, and the error banner stays hidden
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-053
  - **File:** tests/e2e/test_auto_summarize.py::test_auto_empty_summary_shows_note
  - **Command:** python -m pytest tests/e2e/test_auto_summarize.py::test_auto_empty_summary_shows_note -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Manual failures still use the error banner
- **WHEN** auto-summarize is enabled and the user clicks Summarize manually and the request fails
- **THEN** the cause-specific error message is displayed in the error banner as before
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-054
  - **File:** tests/e2e/test_auto_summarize.py::test_manual_failure_still_uses_banner
  - **Command:** python -m pytest tests/e2e/test_auto_summarize.py::test_manual_failure_still_uses_banner -q
  - **Pass:** exit code 0, no skipped tests

## MODIFIED Requirements

### Requirement: Summary panel and copy
On a successful summarization, the interface SHALL display the summary in a dedicated panel with a copy action; the panel SHALL stay hidden until shown, clear when a new transcript is displayed, and load a previously saved summary when the saved transcript has one. When auto-summarize is enabled and a freshly fetched transcript already has a saved summary, the panel SHALL also load and show it. The copy action SHALL copy the full summary with a visible "Copied!" confirmation. Failed summarizations SHALL display a cause-specific error message. Summary text SHALL be inserted as plain text only, never HTML.

#### Scenario: Summary shown on success
- **WHEN** a summarize request succeeds
- **THEN** the summary panel is visible, shows the summary text, and its copy action is available
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-030
  - **File:** tests/e2e/test_summarization.py::test_summary_shown_on_success
  - **Command:** python -m pytest tests/e2e/test_summarization.py::test_summary_shown_on_success -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Copy summary to clipboard
- **WHEN** a summary is displayed and the user triggers the summary copy action
- **THEN** the full summary text is on the clipboard and the action shows a "Copied!" confirmation
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-031
  - **File:** tests/e2e/test_summarization.py::test_copy_summary_to_clipboard
  - **Command:** python -m pytest tests/e2e/test_summarization.py::test_copy_summary_to_clipboard -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: New transcript clears the summary
- **WHEN** a summary is displayed and the user fetches a different transcript (or clicks another saved transcript)
- **THEN** the summary panel no longer shows the previous summary
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-032
  - **File:** tests/e2e/test_summarization.py::test_new_transcript_clears_summary
  - **Command:** python -m pytest tests/e2e/test_summarization.py::test_new_transcript_clears_summary -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Saved summary loaded with its transcript
- **WHEN** a saved transcript with an existing summary file is clicked in the list
- **THEN** the transcript is displayed and the summary panel shows the saved summary
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-033
  - **File:** tests/e2e/test_summarization.py::test_saved_summary_loaded_with_transcript
  - **Command:** python -m pytest tests/e2e/test_summarization.py::test_saved_summary_loaded_with_transcript -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Saved transcript without summary shows no panel
- **WHEN** a saved transcript without a summary file is clicked in the list
- **THEN** the transcript is displayed and the summary panel stays hidden
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-034
  - **File:** tests/e2e/test_summarization.py::test_no_summary_panel_without_saved_summary
  - **Command:** python -m pytest tests/e2e/test_summarization.py::test_no_summary_panel_without_saved_summary -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Summarization error shown
- **WHEN** a summarize request fails with the `PROVIDER_ERROR`, `NOT_CONFIGURED`, or `INVALID_PROVIDER` error code
- **THEN** an error message specific to that cause is displayed in the error region, no summary panel content is shown, and the page remains usable with the Summarize button re-enabled
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-035
  - **File:** tests/e2e/test_summarization.py::test_summarize_error_shown
  - **Command:** python -m pytest tests/e2e/test_summarization.py::test_summarize_error_shown -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Markup-like summary content is not rendered
- **WHEN** a summary contains HTML-like markup (for example a `<script>` tag)
- **THEN** the markup is displayed as plain text, not rendered or executed
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-036
  - **File:** tests/e2e/test_summarization.py::test_summary_markup_shown_as_text
  - **Command:** python -m pytest tests/e2e/test_summarization.py::test_summary_markup_shown_as_text -q
  - **Pass:** exit code 0, no skipped tests
