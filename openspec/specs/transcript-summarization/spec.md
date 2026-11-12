# transcript-summarization Specification

## Purpose

Summarizes the currently displayed transcript with an operator-configured OpenAI-compatible LLM backend: a provider config file, a secret-free provider listing endpoint, a summarize endpoint, summary files persisted alongside transcripts, and the UI picker, button, and summary panel.

## Requirements

### Requirement: Provider configuration file
The application SHALL read the summarization provider configuration from a JSON file at the `PROVIDERS_CONFIG` path (default `providers.json`). The file SHALL contain a top-level `provider` object mapping ids to objects with a display name, `options` (`baseURL` required, `apiKey` optional), and a `models` object keyed by model id in file order. Unknown fields SHALL be ignored and it SHALL be re-read per request. A missing file, malformed JSON, or no usable provider means "not configured".

#### Scenario: Providers are read from the file
- **WHEN** the config file lists provider `radai` with `options.baseURL` set and one model, and a request needs the provider list
- **THEN** the provider list contains provider `radai` with its display name and model id
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-001
  - **File:** tests/test_transcript_summarization.py::test_providers_read_from_config_file
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_providers_read_from_config_file -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Config path taken from environment
- **WHEN** `PROVIDERS_CONFIG` points to a file containing a provider and the default `providers.json` does not exist
- **THEN** the provider list is built from the file the environment variable names
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-002
  - **File:** tests/test_transcript_summarization.py::test_config_path_from_environment
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_config_path_from_environment -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Edits take effect without a restart
- **WHEN** a provider is removed from the config file after the application has served a request
- **THEN** the next request that needs the provider list no longer contains that provider
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-003
  - **File:** tests/test_transcript_summarization.py::test_config_edit_takes_effect_without_restart
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_config_edit_takes_effect_without_restart -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Malformed config is not configured
- **WHEN** the config file contains invalid JSON
- **THEN** the application is treated as not configured for summarization, no request crashes, and the failure is visible in the log without the file contents being echoed into an HTTP response
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-004
  - **File:** tests/test_transcript_summarization.py::test_malformed_config_treated_as_not_configured
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_malformed_config_treated_as_not_configured -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Unknown fields are ignored
- **WHEN** the config file contains fields the application does not use (for example `$schema` or a per-provider `npm` field)
- **THEN** the providers listed in the file are still usable
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-005
  - **File:** tests/test_transcript_summarization.py::test_unknown_config_fields_ignored
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_unknown_config_fields_ignored -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Missing display name falls back to the provider id
- **WHEN** a provider entry has no `name` field, or its `name` is empty
- **THEN** the provider is still usable and its display name is the provider id
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-038
  - **File:** tests/test_transcript_summarization.py::test_missing_display_name_falls_back_to_id
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_missing_display_name_falls_back_to_id -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Provider listing endpoint
The application SHALL expose a read-only `GET /api/providers` endpoint returning 200 with a `default` field (a provider id, or null) and a `providers` array of entries carrying the provider id, display name, and effective model ids in order: config-file models first, followed by models added through the model-management capability. Each entry SHALL also carry `addedModels`, the subset of its model ids supplied by the overrides store, so the interface can distinguish removable models. The response SHALL NOT contain API keys or base URLs. The default SHALL be the provider named by an explicit `default` key in the config file, otherwise the first provider in file order; when not configured, `providers` SHALL be empty and `default` SHALL be null. The effective model set SHALL be the set the summarize endpoint validates provider/model pairs against.

#### Scenario: Providers listed without secrets
- **WHEN** the config file defines a provider with an `apiKey` and a base URL and `GET /api/providers` is requested
- **THEN** the response lists the provider's id, display name, and model ids, and contains neither the API key nor the base URL anywhere in the response body
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-006
  - **File:** tests/test_transcript_summarization.py::test_providers_endpoint_omits_secrets
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_providers_endpoint_omits_secrets -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Default selection
- **WHEN** the config file has an explicit `default` key naming one of its providers
- **THEN** the endpoint's `default` field is that provider's id
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-007
  - **File:** tests/test_transcript_summarization.py::test_providers_endpoint_default_selection
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_providers_endpoint_default_selection -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Not configured lists nothing
- **WHEN** no usable provider configuration exists
- **THEN** `GET /api/providers` returns 200 with an empty `providers` array and a null `default`
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-008
  - **File:** tests/test_transcript_summarization.py::test_providers_endpoint_not_configured_empty
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_providers_endpoint_not_configured_empty -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Added models are listed after file models
- **WHEN** the overrides file adds a model to a configured provider and `GET /api/providers` is requested
- **THEN** the provider's listed model ids are its config-file models in file order followed by the added model
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-056
  - **File:** tests/test_transcript_summarization.py::test_providers_endpoint_includes_added_models
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_providers_endpoint_includes_added_models -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Overlay provenance is exposed
- **WHEN** a provider has both config-file models and overlay-added models
- **THEN** its listing entry's `addedModels` contains only the overlay-added ids, in the same order they appear in `models`
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-058
  - **File:** tests/test_transcript_summarization.py::test_providers_endpoint_exposes_added_models
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_providers_endpoint_exposes_added_models -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Summarize endpoint
The application SHALL expose a `POST /api/summarize` endpoint accepting the transcript `text`, file `name`, provider id, and model id, returning 200 with a `summary` field. Provider and model ids SHALL be validated against the effective provider list — config-file providers and models plus overlay-added models. Local rejections SHALL precede any backend call, checked in this order: invalid name, not configured, unknown provider or model, oversized text; when several apply, the earliest decides the response. Backend failures SHALL surface as provider errors. The endpoint SHALL NOT touch the single-flight limit or the fetch chain.

#### Scenario: Successful summarization
- **WHEN** a provider is configured, and the endpoint is called with valid `text`, `name`, provider id, and model id, and the backend returns a summary
- **THEN** the response is 200 and its `summary` field contains the backend's summary text
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-009
  - **File:** tests/test_transcript_summarization.py::test_summarize_success_returns_summary
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_summarize_success_returns_summary -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Chat completions request shape
- **WHEN** the endpoint calls a configured backend
- **THEN** the request is the chat completions form (a message list, not a bare prompt), the transcript text is present as a user message, the requested model id is used, and the output length is bounded
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-010
  - **File:** tests/test_transcript_summarization.py::test_summarize_sends_chat_completions_shape
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_summarize_sends_chat_completions_shape -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Bearer token only when a key is configured
- **WHEN** the endpoint calls a provider whose config has no `apiKey`
- **THEN** the backend request carries no authentication header, while a provider with an `apiKey` is called with that key as a bearer token
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-011
  - **File:** tests/test_transcript_summarization.py::test_auth_header_only_when_key_present
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_auth_header_only_when_key_present -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Unknown provider or model rejected
- **WHEN** the endpoint is called with a provider id that is not in the effective provider list, or with a model id not listed for that provider in the effective model list
- **THEN** the response is 400 with error code `INVALID_PROVIDER` and no backend request is made
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-012
  - **File:** tests/test_transcript_summarization.py::test_unknown_provider_or_model_rejected
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_unknown_provider_or_model_rejected -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Structurally invalid name rejected before filesystem access
- **WHEN** the endpoint is called with a `name` containing a path separator or a `..` component
- **THEN** the response is 400 with error code `INVALID_NAME` and no file is read or written
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-013
  - **File:** tests/test_transcript_summarization.py::test_invalid_name_rejected
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_invalid_name_rejected -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Overlong text rejected without backend call
- **WHEN** the endpoint is called with `text` longer than 100,000 characters
- **THEN** the response is 400 with error code `INPUT_TOO_LONG` and no backend request is made
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-014
  - **File:** tests/test_transcript_summarization.py::test_overlong_text_rejected
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_overlong_text_rejected -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Not configured returns 503
- **WHEN** no usable provider configuration exists and the endpoint is called
- **THEN** the response is 503 with error code `NOT_CONFIGURED` and no backend request is made
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-015
  - **File:** tests/test_transcript_summarization.py::test_not_configured_returns_503
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_not_configured_returns_503 -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Backend failure returns 502
- **WHEN** the configured backend is unreachable, times out, returns a non-2xx status, or returns a malformed response body
- **THEN** the response is 502 with error code `PROVIDER_ERROR` and a message suggesting a retry
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-016
  - **File:** tests/test_transcript_summarization.py::test_backend_failure_returns_502
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_backend_failure_returns_502 -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Summarize is not subject to the fetch limit
- **WHEN** a transcript fetch is in progress and a summarize request arrives
- **THEN** the summarize request proceeds (it is not rejected with `BUSY`) and does not invoke the fetch chain
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-017
  - **File:** tests/test_transcript_summarization.py::test_summarize_during_in_flight_fetch_succeeds
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_summarize_during_in_flight_fetch_succeeds -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Added models are accepted by the summarize endpoint
- **WHEN** an overlay-added model id is submitted to `POST /api/summarize` for its provider
- **THEN** the request is accepted and forwarded to the backend instead of being rejected with `INVALID_PROVIDER`
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-057
  - **File:** tests/test_transcript_summarization.py::test_summarize_accepts_added_model
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_summarize_accepts_added_model -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Empty backend content is a failure
A backend 2xx response whose `choices[0].message.content` is empty or whitespace-only SHALL be treated as a backend failure: the response SHALL be 502 with error code `PROVIDER_ERROR` and no summary file SHALL be written.

#### Scenario: Empty backend content is a provider error
- **WHEN** the configured backend returns a 2xx response whose `choices[0].message.content` is empty or whitespace-only
- **THEN** the response is 502 with error code `PROVIDER_ERROR`, no `.summary` file is written, and the `summary_failed` event carries the machine-readable reason `empty_response`
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-039
  - **File:** tests/test_transcript_summarization.py::test_empty_content_rejected_as_provider_error
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_empty_content_rejected_as_provider_error -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Summary file persistence
On a successful summarization, the application SHALL write the summary text (UTF-8) to `<transcript name>.summary` in the transcript directory, overwriting any existing summary file on re-summarize. A write failure SHALL NOT change the HTTP response: the response is still 200 with the generated summary, and the failure SHALL be reported only through a structured error log event. The saved list contains only `.txt` files, so summary files do not appear in the `GET /api/transcripts` list.

#### Scenario: Summary written alongside the transcript
- **WHEN** a summarization succeeds for the transcript file `the_end_of_llms_ncm.txt`
- **THEN** a file `the_end_of_llms_ncm.txt.summary` exists in the transcript directory and its content equals the returned summary text
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-018
  - **File:** tests/test_transcript_summarization.py::test_summary_written_alongside_transcript
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_summary_written_alongside_transcript -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Re-summarize overwrites the summary
- **WHEN** a transcript is summarized a second time and the backend returns different summary text
- **THEN** the summary file contains the second summary
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-019
  - **File:** tests/test_transcript_summarization.py::test_resummarize_overwrites_summary_file
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_resummarize_overwrites_summary_file -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Failed summary save does not change the response
- **WHEN** the transcript directory is not writable and a summarization succeeds at the backend
- **THEN** the response is still 200 with the generated summary, no file is written, and the failure is reported only through the log
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-020
  - **File:** tests/test_transcript_summarization.py::test_unwritable_directory_still_returns_summary
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_unwritable_directory_still_returns_summary -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Summary files are not listed as transcripts
- **WHEN** the transcript directory contains a `.summary` file
- **THEN** `GET /api/transcripts` does not list it
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-021
  - **File:** tests/test_transcript_summarization.py::test_summary_files_excluded_from_list
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_summary_files_excluded_from_list -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Summary read endpoint
The application SHALL expose a read-only `GET /api/transcripts/{name}/summary` endpoint returning 200 with a `summary` field containing the exact content of the `<name>.summary` file when it exists, and 404 with error code `NOT_FOUND` when it does not. Structurally invalid names SHALL be rejected with 400 and error code `INVALID_NAME` without filesystem access. The endpoint SHALL NOT create files or the transcript directory and SHALL NOT be subject to the single-flight fetch limit.

#### Scenario: Existing summary is returned
- **WHEN** the transcript directory contains `the_end_of_llms_ncm.txt.summary` and a request is made for `the_end_of_llms_ncm.txt`
- **THEN** the response is 200 and its `summary` field equals the file's content
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-022
  - **File:** tests/test_transcript_summarization.py::test_summary_read_returns_content
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_summary_read_returns_content -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Absent summary is a 404
- **WHEN** a transcript exists but no `.summary` file has been written for it
- **THEN** the response is 404 with error code `NOT_FOUND`
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-023
  - **File:** tests/test_transcript_summarization.py::test_summary_read_absent_returns_404
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_summary_read_absent_returns_404 -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Traversal-safe name handling
- **WHEN** the requested name contains a path separator or a `..` component
- **THEN** the response is 400 with error code `INVALID_NAME` and no file outside the transcript directory is read
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-024
  - **File:** tests/test_transcript_summarization.py::test_summary_read_traversal_rejected
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_summary_read_traversal_rejected -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Read endpoint has no side effects
- **WHEN** a summary is requested for a name with no `.summary` file while a transcript fetch is in flight
- **THEN** the response is 404 with error code `NOT_FOUND`, no file or directory is created, and the request neither invokes the fetch chain nor waits on the single-flight fetch limit
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-037
  - **File:** tests/test_transcript_summarization.py::test_summary_read_has_no_side_effects
  - **Command:** python -m pytest tests/test_transcript_summarization.py::test_summary_read_has_no_side_effects -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Provider picker and Summarize button
The interface SHALL load the provider list when the page loads, display a picker offering each configured provider's models (labeled by the provider's display name), and pre-select the default provider's first model. The interface SHALL provide a "Summarize" button that is enabled only when a transcript is currently displayed and at least one provider is configured. While a summarize request is in flight, the button and the picker SHALL be disabled and a loading indicator SHALL be shown.

#### Scenario: Picker lists configured providers
- **WHEN** the page is loaded and two providers are configured
- **THEN** the picker offers the providers' models, and the default provider's first model is pre-selected
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-025
  - **File:** tests/e2e/test_summarization.py::test_picker_lists_providers_with_default
  - **Command:** python -m pytest tests/e2e/test_summarization.py::test_picker_lists_providers_with_default -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Button disabled before a transcript
- **WHEN** the page is loaded with providers configured and no transcript has been displayed
- **THEN** the Summarize button is disabled
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-026
  - **File:** tests/e2e/test_summarization.py::test_summarize_disabled_before_transcript
  - **Command:** python -m pytest tests/e2e/test_summarization.py::test_summarize_disabled_before_transcript -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Button disabled when no providers are configured
- **WHEN** a transcript is displayed but no providers are configured
- **THEN** the picker offers no choices and the Summarize button is disabled
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-027
  - **File:** tests/e2e/test_summarization.py::test_summarize_disabled_without_providers
  - **Command:** python -m pytest tests/e2e/test_summarization.py::test_summarize_disabled_without_providers -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Summarize the displayed transcript
- **WHEN** a transcript is displayed and the user clicks Summarize
- **THEN** the request carries the displayed transcript's text, its file name, and the selected provider and model; the button and picker are disabled with a loading indicator until the response arrives, and the button is re-enabled afterwards
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-028
  - **File:** tests/e2e/test_summarization.py::test_summarize_sends_displayed_transcript
  - **Command:** python -m pytest tests/e2e/test_summarization.py::test_summarize_sends_displayed_transcript -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Summarize a selected saved transcript
- **WHEN** the user clicks a saved transcript in the list and then clicks Summarize
- **THEN** the summarize request carries that saved transcript's text and its file name
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-029
  - **File:** tests/e2e/test_summarization.py::test_summarize_selected_saved_transcript
  - **Command:** python -m pytest tests/e2e/test_summarization.py::test_summarize_selected_saved_transcript -q
  - **Pass:** exit code 0, no skipped tests

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

### Requirement: Empty summary responses are display failures
A summarize response whose `summary` field is an empty string SHALL be treated as a failed summarization for display: the summary panel stays hidden, the error region shows a message, and the Summarize button is re-enabled.

#### Scenario: Empty summary response never shows a panel
- **WHEN** a summarize response's `summary` field is an empty string
- **THEN** the summary panel remains hidden, the error region shows a message, and the Summarize button is re-enabled
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-040
  - **File:** tests/e2e/test_summarization.py::test_empty_summary_response_shows_no_panel
  - **Command:** python -m pytest tests/e2e/test_summarization.py::test_empty_summary_response_shows_no_panel -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Summarize backend concurrency bound
The application SHALL allow at most 2 concurrent summarization backend calls. When more than 2 summarize requests pass local validation at the same time, the excess requests SHALL wait for a free slot rather than being rejected. Backend calls SHALL run on a bounded pool of their own, so the shared thread pool that other endpoints use for their blocking work is not consumed by in-flight summarize calls.

#### Scenario: Excess concurrent summarize requests are queued
- **WHEN** 4 summarize requests with valid bodies are in flight at the same time against a stubbed backend that tracks concurrent invocations
- **THEN** the backend is never invoked with more than 2 concurrent calls and every request eventually completes with 200
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-041
  - **File:** tests/test_transcript_summarization.py::test_summarize_backend_concurrency_bounded
  - **Command:** uv run python -m pytest tests/test_transcript_summarization.py::test_summarize_backend_concurrency_bounded -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Other endpoints stay responsive while summarize calls are in progress
- **WHEN** 2 summarize backend calls are in flight (both bounded slots occupied) and a `GET /api/transcripts` request arrives
- **THEN** the transcript list response returns promptly (well under the summarize timeout) while the in-flight summarize calls are still running
- **Test Requirement**
  - **ID:** T-TRANSCRIPT-SUMMARIZATION-042
  - **File:** tests/test_transcript_summarization.py::test_summarize_does_not_starve_other_endpoints
  - **Command:** uv run python -m pytest tests/test_transcript_summarization.py::test_summarize_does_not_starve_other_endpoints -q
  - **Pass:** exit code 0, no skipped tests

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
