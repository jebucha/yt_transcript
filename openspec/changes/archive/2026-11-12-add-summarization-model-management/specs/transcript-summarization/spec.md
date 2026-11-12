# Spec Delta

## MODIFIED Requirements

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
