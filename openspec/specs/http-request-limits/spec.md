# http-request-limits Specification

## Purpose

Bounds on inbound HTTP traffic: rejects oversized request bodies before they
are parsed and caps the number of concurrent connections the server serves, so
a single client cannot exhaust process memory or connections.

## Requirements

### Requirement: Request body size limit
The application SHALL reject any inbound request whose `Content-Length` header exceeds 5 MiB (5,242,880 bytes) with status 413 and error code `BODY_TOO_LARGE`, before the body is read or parsed and before any endpoint code runs. This SHALL apply to every route. Requests with a `Content-Length` at or below the limit SHALL be processed normally.

#### Scenario: Oversized body rejected before parsing
- **WHEN** a `POST /api/summarize` request arrives with a `Content-Length` above 5 MiB
- **THEN** the response is 413 with error code `BODY_TOO_LARGE`, no summarization backend call is made, and no transcript or summary file is read or written
- **Test Requirement**
  - **ID:** T-HTTP-REQUEST-LIMITS-001
  - **File:** tests/test_http_request_limits.py::test_oversized_body_rejected_with_413
  - **Command:** uv run python -m pytest tests/test_http_request_limits.py::test_oversized_body_rejected_with_413 -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Body at or below the limit is processed normally
- **WHEN** a `POST /api/summarize` request with a valid body well under 5 MiB (for example a 100,000-character transcript, under 300 KB as JSON) arrives
- **THEN** the request passes the size check and is handled by the endpoint as usual, and a request with no body or an empty body is likewise unaffected
- **Test Requirement**
  - **ID:** T-HTTP-REQUEST-LIMITS-002
  - **File:** tests/test_http_request_limits.py::test_body_under_limit_processed_normally
  - **Command:** uv run python -m pytest tests/test_http_request_limits.py::test_body_under_limit_processed_normally -q
  - **Pass:** exit code 0, no skipped tests

### Requirement: Connection concurrency cap
The server entry point SHALL run uvicorn with a concurrent-connection limit of 100 (`limit_concurrency`), so that while 100 connections are in flight, additional connections are rejected with status 503 instead of being accepted.

#### Scenario: Entry point configures the connection limit
- **WHEN** the application is started through its `main()` entry point
- **THEN** uvicorn is started with `limit_concurrency` set to 100
- **Test Requirement**
  - **ID:** T-HTTP-REQUEST-LIMITS-003
  - **File:** tests/test_http_request_limits.py::test_entry_point_sets_connection_limit
  - **Command:** uv run python -m pytest tests/test_http_request_limits.py::test_entry_point_sets_connection_limit -q
  - **Pass:** exit code 0, no skipped tests
