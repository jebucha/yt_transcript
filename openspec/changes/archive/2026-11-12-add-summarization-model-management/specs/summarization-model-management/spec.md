# Spec Delta

## Purpose

Lets the operator extend and trim the set of selectable models for already-configured summarization providers from the web UI, without editing the read-only provider config file or restarting the application.

## ADDED Requirements

### Requirement: Provider overrides store
The application SHALL read UI-added model ids from `provider_overrides.json` in the transcript directory on every request, as a JSON object mapping provider ids to model-id arrays. A missing file SHALL mean no additions; an unreadable or malformed file SHALL degrade to no additions without raising and log `provider_overrides_load_failed` without file contents. Writes SHALL be atomic.

#### Scenario: Added models follow file models
- **WHEN** the config file lists provider `radai` with models `a` and `b`, and the overrides file adds `c` for `radai`
- **THEN** the effective model list for `radai` is `a`, `b`, `c`, in that order
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-001
  - **File:** tests/test_provider_overrides.py::test_overrides_merge_after_file_models
  - **Command:** python -m pytest tests/test_provider_overrides.py::test_overrides_merge_after_file_models -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Duplicate ids are not repeated
- **WHEN** the overrides file adds a model id that is already present in the provider's config-file model list
- **THEN** the effective model list contains that id exactly once
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-002
  - **File:** tests/test_provider_overrides.py::test_override_duplicates_not_repeated
  - **Command:** python -m pytest tests/test_provider_overrides.py::test_override_duplicates_not_repeated -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Missing overrides file means file-only models
- **WHEN** no overrides file exists and the provider list is read
- **THEN** each provider's model list equals its config-file models and no failure is logged
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-004
  - **File:** tests/test_provider_overrides.py::test_missing_overrides_means_file_only
  - **Command:** python -m pytest tests/test_provider_overrides.py::test_missing_overrides_means_file_only -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Malformed overrides degrade without raising
- **WHEN** the overrides file contains invalid JSON or a non-object top level
- **THEN** the effective provider list equals the config-file list, no request crashes, and one `provider_overrides_load_failed` event records the path and parse reason without file contents
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-005
  - **File:** tests/test_provider_overrides.py::test_malformed_overrides_degrades
  - **Command:** python -m pytest tests/test_provider_overrides.py::test_malformed_overrides_degrades -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Overrides edits take effect without a restart
- **WHEN** a model is added to the overrides file after the application has served a provider list request
- **THEN** the next provider list request includes the added model
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-006
  - **File:** tests/test_provider_overrides.py::test_overrides_edit_takes_effect_without_restart
  - **Command:** python -m pytest tests/test_provider_overrides.py::test_overrides_edit_takes_effect_without_restart -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Overrides file is not listed as a transcript
- **WHEN** the transcript directory contains `provider_overrides.json` and `GET /api/transcripts` is requested
- **THEN** the response does not list `provider_overrides.json`
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-007
  - **File:** tests/test_provider_overrides.py::test_overrides_file_excluded_from_list
  - **Command:** python -m pytest tests/test_provider_overrides.py::test_overrides_file_excluded_from_list -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Overlay scope
The overrides store SHALL only extend the model list of providers defined in the config file. It SHALL NOT introduce a provider, a base URL, or an API key, and entries for unknown provider ids SHALL be ignored.

#### Scenario: Overrides cannot introduce a provider
- **WHEN** the overrides file contains models for a provider id that is not in the config file
- **THEN** the effective provider list does not contain that provider
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-003
  - **File:** tests/test_provider_overrides.py::test_overlay_cannot_add_provider
  - **Command:** python -m pytest tests/test_provider_overrides.py::test_overlay_cannot_add_provider -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Add model endpoint
`POST /api/providers/{provider_id}/models` with body `{"model": "<id>"}` SHALL persist the trimmed id for a provider present in the config file and return 200 with the provider id, the added id, and the effective model ids in order. Adding an id already in the effective list SHALL succeed without duplicating it. An unknown provider SHALL return 400 `INVALID_PROVIDER`; a failed write SHALL return 500 `WRITE_FAILED` with no partial state.

#### Scenario: Manual add persists and is listed
- **WHEN** a configured provider receives a valid model id through the add endpoint
- **THEN** the response is 200, the overrides file contains the id, and a subsequent provider listing includes it after the config-file models
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-008
  - **File:** tests/test_model_management.py::test_add_model_persists_and_lists
  - **Command:** python -m pytest tests/test_model_management.py::test_add_model_persists_and_lists -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Adding an existing model is idempotent
- **WHEN** a model id already present in the provider's effective list is added again
- **THEN** the response is 200 and the effective list contains the id exactly once
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-009
  - **File:** tests/test_model_management.py::test_add_existing_model_is_idempotent
  - **Command:** python -m pytest tests/test_model_management.py::test_add_existing_model_is_idempotent -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Adding to an unknown provider is rejected
- **WHEN** the add endpoint is called with a provider id not present in the config file
- **THEN** the response is 400 with error code `INVALID_PROVIDER` and the overrides file is unchanged
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-010
  - **File:** tests/test_model_management.py::test_add_unknown_provider_rejected
  - **Command:** python -m pytest tests/test_model_management.py::test_add_unknown_provider_rejected -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Add write failure has no partial state
- **WHEN** the overrides file cannot be written and a valid add request arrives
- **THEN** the response is 500 with error code `WRITE_FAILED`, the failure is logged, and the effective model list is unchanged
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-011
  - **File:** tests/test_model_management.py::test_add_write_failure_no_partial_state
  - **Command:** python -m pytest tests/test_model_management.py::test_add_write_failure_no_partial_state -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Model management is independent of the fetch chain
Model-management endpoints SHALL NOT invoke the YouTube fetch chain or be subject to the single-flight fetch limit, and the add and remove endpoints SHALL NOT contact a summarization backend.

#### Scenario: Add does not touch the fetch chain
- **WHEN** a transcript fetch is in progress and a valid add request arrives
- **THEN** the add succeeds and does not invoke the fetch chain or touch the single-flight limit
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-012
  - **File:** tests/test_model_management.py::test_add_during_in_flight_fetch_succeeds
  - **Command:** python -m pytest tests/test_model_management.py::test_add_during_in_flight_fetch_succeeds -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Model id validation and bounds
A model id accepted by the add endpoint SHALL be a string of 1 to 200 characters after trimming, free of control characters, and each provider SHALL hold at most 50 overlay additions. A non-object body or a missing `model` field SHALL return 400 `INVALID_BODY`; a body whose `model` violates the id rules or would exceed the per-provider bound SHALL return 400 `INVALID_MODEL`. No rejected request SHALL write the overrides file.

#### Scenario: Blank model id is rejected
- **WHEN** the add endpoint receives a model id that is empty or whitespace-only
- **THEN** the response is 400 with error code `INVALID_MODEL` and nothing is written
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-013
  - **File:** tests/test_model_management.py::test_add_blank_model_rejected
  - **Command:** python -m pytest tests/test_model_management.py::test_add_blank_model_rejected -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Overlong model id is rejected
- **WHEN** the add endpoint receives a model id longer than 200 characters
- **THEN** the response is 400 with error code `INVALID_MODEL` and nothing is written
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-014
  - **File:** tests/test_model_management.py::test_add_overlong_model_rejected
  - **Command:** python -m pytest tests/test_model_management.py::test_add_overlong_model_rejected -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Control characters in a model id are rejected
- **WHEN** the add endpoint receives a model id containing a control character
- **THEN** the response is 400 with error code `INVALID_MODEL` and nothing is written
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-015
  - **File:** tests/test_model_management.py::test_add_control_char_model_rejected
  - **Command:** python -m pytest tests/test_model_management.py::test_add_control_char_model_rejected -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Per-provider addition cap is enforced
- **WHEN** a provider already has 50 overlay additions and another valid model is added
- **THEN** the response is 400 with error code `INVALID_MODEL` and nothing is written
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-016
  - **File:** tests/test_model_management.py::test_add_per_provider_cap_enforced
  - **Command:** python -m pytest tests/test_model_management.py::test_add_per_provider_cap_enforced -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Invalid body is rejected
- **WHEN** the add endpoint receives a non-object body or a body without a `model` field
- **THEN** the response is 400 with error code `INVALID_BODY` and nothing is written
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-017
  - **File:** tests/test_model_management.py::test_add_invalid_body_rejected
  - **Command:** python -m pytest tests/test_model_management.py::test_add_invalid_body_rejected -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Remove model endpoint
`DELETE /api/providers/{provider_id}/models` with body `{"model": "<id>"}` SHALL remove an overlay-added model for a provider in the config file and return 200 with the provider id, removed id, and remaining effective ids. A config-file model SHALL NOT be removable: 400 `MODEL_NOT_REMOVABLE`, overlay unchanged. An id in neither set SHALL return 404 `NOT_FOUND`, an unknown provider 400 `INVALID_PROVIDER`, and a failed write 500 `WRITE_FAILED`.

#### Scenario: Overlay model is removed
- **WHEN** a provider has an overlay-added model and the remove endpoint is called for it
- **THEN** the response is 200, the overrides file no longer contains it, and the provider listing no longer offers it
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-018
  - **File:** tests/test_model_management.py::test_remove_added_model
  - **Command:** python -m pytest tests/test_model_management.py::test_remove_added_model -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Config-file model is not removable
- **WHEN** the remove endpoint is called for a model present in the config file
- **THEN** the response is 400 with error code `MODEL_NOT_REMOVABLE` and the model remains in the effective list
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-019
  - **File:** tests/test_model_management.py::test_remove_file_model_rejected
  - **Command:** python -m pytest tests/test_model_management.py::test_remove_file_model_rejected -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Absent model returns 404
- **WHEN** the remove endpoint is called for a model that is neither an overlay addition nor in the config file
- **THEN** the response is 404 with error code `NOT_FOUND` and the overrides file is unchanged
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-020
  - **File:** tests/test_model_management.py::test_remove_absent_model_404
  - **Command:** python -m pytest tests/test_model_management.py::test_remove_absent_model_404 -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Removing from an unknown provider is rejected
- **WHEN** the remove endpoint is called with a provider id not present in the config file
- **THEN** the response is 400 with error code `INVALID_PROVIDER` and the overrides file is unchanged
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-021
  - **File:** tests/test_model_management.py::test_remove_unknown_provider_rejected
  - **Command:** python -m pytest tests/test_model_management.py::test_remove_unknown_provider_rejected -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Remove write failure has no partial state
- **WHEN** the overrides file cannot be written and a valid remove request arrives
- **THEN** the response is 500 with error code `WRITE_FAILED`, the failure is logged, and the model remains listed
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-022
  - **File:** tests/test_model_management.py::test_remove_write_failure_no_partial_state
  - **Command:** python -m pytest tests/test_model_management.py::test_remove_write_failure_no_partial_state -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Discover available models
`GET /api/providers/{provider_id}/available-models` SHALL request the provider's OpenAI-compatible `{baseURL}/models`, sending the configured API key as a bearer token when present, and return 200 with a `models` array of id strings (non-strings ignored, duplicates removed). An unknown provider SHALL return 400 `INVALID_PROVIDER`; any backend failure SHALL return 502 `PROVIDER_ERROR`. The response SHALL NOT contain the base URL or API key.

#### Scenario: Discovered ids are returned
- **WHEN** a configured provider's models endpoint returns a list of model objects
- **THEN** the response is 200 and `models` contains their id strings with duplicates removed and non-string entries ignored
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-023
  - **File:** tests/test_model_management.py::test_discover_models_returns_ids
  - **Command:** python -m pytest tests/test_model_management.py::test_discover_models_returns_ids -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Discovery uses the configured bearer token
- **WHEN** the provider config defines an API key and discovery is requested
- **THEN** the models request carries that key as a bearer token, and a keyless provider's request carries no authorization header
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-024
  - **File:** tests/test_model_management.py::test_discover_auth_header_only_when_key_present
  - **Command:** python -m pytest tests/test_model_management.py::test_discover_auth_header_only_when_key_present -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Unknown provider is rejected
- **WHEN** discovery is requested for a provider id not present in the config file
- **THEN** the response is 400 with error code `INVALID_PROVIDER` and no backend request is made
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-025
  - **File:** tests/test_model_management.py::test_discover_unknown_provider_rejected
  - **Command:** python -m pytest tests/test_model_management.py::test_discover_unknown_provider_rejected -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Discovery backend failure returns 502
- **WHEN** the provider's models endpoint is unreachable, times out, returns a non-2xx status, or returns a malformed body
- **THEN** the response is 502 with error code `PROVIDER_ERROR` and a `provider_models_refresh_failed` event records the failure reason
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-026
  - **File:** tests/test_model_management.py::test_discover_backend_failure_returns_502
  - **Command:** python -m pytest tests/test_model_management.py::test_discover_backend_failure_returns_502 -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Discovery response omits secrets
- **WHEN** discovery is requested for a provider with an API key and base URL
- **THEN** neither the API key nor the base URL appears anywhere in the response body
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-027
  - **File:** tests/test_model_management.py::test_discover_response_omits_secrets
  - **Command:** python -m pytest tests/test_model_management.py::test_discover_response_omits_secrets -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Discovery does not touch the fetch chain
- **WHEN** a transcript fetch is in progress and discovery is requested
- **THEN** discovery proceeds without touching the single-flight limit and does not invoke the fetch chain
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-028
  - **File:** tests/test_model_management.py::test_discover_during_in_flight_fetch_succeeds
  - **Command:** python -m pytest tests/test_model_management.py::test_discover_during_in_flight_fetch_succeeds -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Model management section
The interface SHALL show an always-visible Summarization models section listing each configured provider with display name, model count, and a Manage control, before any transcript is fetched, with an empty state when no providers exist. A manage panel SHALL offer manual model-id entry with Add, discovery with Add actions, and UI-added models with Remove actions; config-file models SHALL NOT offer Remove. Every inserted value SHALL be plain text only.

#### Scenario: Section is available before a transcript
- **WHEN** the page loads with providers configured and no transcript displayed
- **THEN** the Summarization models section is visible and lists the providers
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-029
  - **File:** tests/e2e/test_model_management.py::test_section_visible_before_transcript
  - **Command:** python -m pytest tests/e2e/test_model_management.py::test_section_visible_before_transcript -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Providers and model counts are listed
- **WHEN** the section renders with two providers whose effective model counts differ
- **THEN** each provider's display name and model count are shown
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-030
  - **File:** tests/e2e/test_model_management.py::test_section_lists_providers_and_counts
  - **Command:** python -m pytest tests/e2e/test_model_management.py::test_section_lists_providers_and_counts -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Empty state without providers
- **WHEN** no providers are configured
- **THEN** the section shows an empty state and offers no manage actions
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-031
  - **File:** tests/e2e/test_model_management.py::test_section_empty_without_providers
  - **Command:** python -m pytest tests/e2e/test_model_management.py::test_section_empty_without_providers -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Manual add from the panel
- **WHEN** the user enters a model id in a provider's manage panel and clicks Add
- **THEN** the model is added, the provider's count increases, and the model appears in the provider's added list
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-032
  - **File:** tests/e2e/test_model_management.py::test_manual_add_from_panel
  - **Command:** python -m pytest tests/e2e/test_model_management.py::test_manual_add_from_panel -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Discovered models can be added
- **WHEN** the user triggers discovery for a provider and clicks Add beside a discovered model
- **THEN** that model is added and appears in the provider's added list
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-033
  - **File:** tests/e2e/test_model_management.py::test_discovered_model_can_be_added
  - **Command:** python -m pytest tests/e2e/test_model_management.py::test_discovered_model_can_be_added -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Added model can be removed
- **WHEN** the user clicks Remove beside a UI-added model
- **THEN** the model is removed, the provider's count decreases, and the model no longer appears in the added list
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-034
  - **File:** tests/e2e/test_model_management.py::test_added_model_can_be_removed
  - **Command:** python -m pytest tests/e2e/test_model_management.py::test_added_model_can_be_removed -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Config-file models have no remove action
- **WHEN** a provider's manage panel lists models supplied by the config file
- **THEN** those models are shown without a Remove action
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-035
  - **File:** tests/e2e/test_model_management.py::test_file_models_not_removable
  - **Command:** python -m pytest tests/e2e/test_model_management.py::test_file_models_not_removable -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Markup-like model ids are not rendered
- **WHEN** a provider or model name contains HTML-like markup
- **THEN** the markup is displayed as plain text in the section and is not executed
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-036
  - **File:** tests/e2e/test_model_management.py::test_markup_model_ids_shown_as_text
  - **Command:** python -m pytest tests/e2e/test_model_management.py::test_markup_model_ids_shown_as_text -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Model management refreshes the picker
After a successful model addition or removal, the interface SHALL reload the provider list and re-render the provider picker so the change is reflected immediately. A model added in the current page session SHALL be selected in the picker; a removed model SHALL no longer be offered.

#### Scenario: Added model appears and is selected
- **WHEN** a model is added through the manage panel
- **THEN** the provider picker offers it and selects it for the current page session
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-037
  - **File:** tests/e2e/test_model_management.py::test_added_model_selected_in_picker
  - **Command:** python -m pytest tests/e2e/test_model_management.py::test_added_model_selected_in_picker -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Removed model leaves the picker
- **WHEN** a UI-added model is removed
- **THEN** the provider picker no longer offers it
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-038
  - **File:** tests/e2e/test_model_management.py::test_removed_model_leaves_picker
  - **Command:** python -m pytest tests/e2e/test_model_management.py::test_removed_model_leaves_picker -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Model management errors are reported safely
Failed model-management operations SHALL display a cause-specific message in the page's error region and leave the section usable. Invalid ids, unknown providers, write failures, and discovery failures SHALL map to distinct messages. A discovery failure SHALL NOT remove or alter existing models.

#### Scenario: Discovery failure is shown without changing models
- **WHEN** discovery fails for a provider
- **THEN** a discovery-specific error message is displayed, the provider's effective model list is unchanged, and the section remains usable
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-039
  - **File:** tests/e2e/test_model_management.py::test_discovery_failure_shown
  - **Command:** python -m pytest tests/e2e/test_model_management.py::test_discovery_failure_shown -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Invalid model message is shown
- **WHEN** the add request is rejected with `INVALID_MODEL`
- **THEN** an invalid-model message is displayed and no model is added
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-040
  - **File:** tests/e2e/test_model_management.py::test_invalid_model_error_shown
  - **Command:** python -m pytest tests/e2e/test_model_management.py::test_invalid_model_error_shown -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Write failure message is shown
- **WHEN** the add request is rejected with `WRITE_FAILED`
- **THEN** a save-failure message is displayed and the section remains usable
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-041
  - **File:** tests/e2e/test_model_management.py::test_write_failure_error_shown
  - **Command:** python -m pytest tests/e2e/test_model_management.py::test_write_failure_error_shown -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Model management observability
The application SHALL emit structured log events for additions and removals (`provider_model_added`, `provider_model_removed`, info, provider and model) and discovery failures (`provider_models_refresh_failed`, error, provider, reason, detail). Overlay load and save failures SHALL emit `provider_overrides_load_failed` / `provider_overrides_save_failed` with path, reason, and detail. No event SHALL contain an API key, base URL, transcript text, or the full model list.

#### Scenario: Add and remove are logged
- **WHEN** a model is added and then removed through the endpoints
- **THEN** one `provider_model_added` and one `provider_model_removed` event carry the provider id and model id
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-042
  - **File:** tests/test_model_management.py::test_add_and_remove_are_logged
  - **Command:** python -m pytest tests/test_model_management.py::test_add_and_remove_are_logged -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Discovery failure is logged with its reason
- **WHEN** discovery fails
- **THEN** a `provider_models_refresh_failed` event records the provider id, a machine-readable reason, and a safe detail
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-043
  - **File:** tests/test_model_management.py::test_discovery_failure_logged
  - **Command:** python -m pytest tests/test_model_management.py::test_discovery_failure_logged -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Overlay failures are logged
- **WHEN** the overrides file is malformed or cannot be written
- **THEN** a `provider_overrides_load_failed` or `provider_overrides_save_failed` event records the path, reason, and detail without file contents
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-044
  - **File:** tests/test_model_management.py::test_overlay_failures_logged
  - **Command:** python -m pytest tests/test_model_management.py::test_overlay_failures_logged -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Logs carry no secrets
- **WHEN** a provider with an API key and base URL is used for add, remove, and discovery
- **THEN** no emitted log event contains the API key or base URL
- **Test Requirement**
  - **ID:** T-SUMMARIZATION-MODEL-MANAGEMENT-045
  - **File:** tests/test_model_management.py::test_logs_carry_no_secrets
  - **Command:** python -m pytest tests/test_model_management.py::test_logs_carry_no_secrets -q
  - **Pass:** exit code 0, no skipped tests
