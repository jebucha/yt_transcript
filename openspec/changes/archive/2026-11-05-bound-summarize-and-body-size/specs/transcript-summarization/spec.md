# Spec Delta

## ADDED Requirements

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
