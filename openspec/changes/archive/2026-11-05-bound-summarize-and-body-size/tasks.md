# Tasks

## 1. Summarize backend concurrency bound

- [x] 1.1 In `app/main.py`, add module-level `SUMMARIZE_MAX_CONCURRENCY = 2` and a dedicated bounded `SUMMARIZE_EXECUTOR` (`ThreadPoolExecutor`, `thread_name_prefix="summarize"`), and change `summarize_endpoint`'s backend dispatch to run `summarize_with_provider` on that pool via `loop.run_in_executor(SUMMARIZE_EXECUTOR, contextvars.copy_context().run, ...)` — this runtime's `asyncio.to_thread` has no `executor` parameter, so the original to_thread-based dispatch of design D1 was verified to leave the bound unenforced (see design D1 runtime note); verify with `uv run python -m pytest tests/test_transcript_summarization.py -q --ignore=tests/e2e` that all pre-existing summarize tests still pass
- [x] 1.2 Add `test_summarize_backend_concurrency_bounded` to `tests/test_transcript_summarization.py`: monkeypatch the summarize dispatch with a stub tracking peak concurrent invocations, fire 4 concurrent valid summarize requests, assert peak ≤ 2 and all responses 200; verify with `uv run python -m pytest tests/test_transcript_summarization.py::test_summarize_backend_concurrency_bounded -q`
- [x] 1.3 Add `test_summarize_does_not_starve_other_endpoints` to `tests/test_transcript_summarization.py`: keep 2 summarize calls in flight with a delayed stub backend, assert a concurrent `GET /api/transcripts` returns promptly (well under the summarize timeout); verify with `uv run python -m pytest tests/test_transcript_summarization.py::test_summarize_does_not_starve_other_endpoints -q`

## 2. HTTP request limits

- [x] 2.1 In `app/main.py`, add module-level `MAX_BODY_BYTES = 5 * 1024 * 1024` and a `limit_body_size` middleware in `create_app()` (registered before the logging middleware so rejections are logged) that returns 413 with `{"error": {"code": "BODY_TOO_LARGE", ...}}` when the numeric `Content-Length` header exceeds the limit, without reading the body (design D3); verify with `uv run python -m pytest tests/test_http_request_limits.py -q` (tests added in 2.2–2.3)
- [x] 2.2 Create `tests/test_http_request_limits.py` with `test_oversized_body_rejected_with_413`: assert `MAX_BODY_BYTES` equals 5 MiB, then monkeypatch the constant small, send an over-limit `POST /api/summarize` body, and assert 413 + `BODY_TOO_LARGE` with the endpoint's dispatch stub never invoked; verify with `uv run python -m pytest tests/test_http_request_limits.py::test_oversized_body_rejected_with_413 -q`
- [x] 2.3 Add `test_body_under_limit_processed_normally` to `tests/test_http_request_limits.py`: a valid small summarize body is handled by the endpoint as usual, and a bodyless request is unaffected; verify with `uv run python -m pytest tests/test_http_request_limits.py::test_body_under_limit_processed_normally -q`
- [x] 2.4 Pass `limit_concurrency=100` to `uvicorn.run(...)` in `main()` (design D2) and add `test_entry_point_sets_connection_limit` to `tests/test_http_request_limits.py` (monkeypatch `uvicorn.run`, call `main()`, assert the kwarg); verify with `uv run python -m pytest tests/test_http_request_limits.py::test_entry_point_sets_connection_limit -q`

## 3. Integration verification

- [x] 3.1 Run the full non-e2e suite and verify it is green: `uv run python -m pytest tests/ -q --ignore=tests/e2e`
- [x] 3.2 Run the e2e suite (one-time `uv run python -m playwright install chromium` if needed) and verify the summarize UI flow still passes: `uv run python -m pytest tests/e2e/ -q`
- [x] 3.3 Smoke-test the real server: start `uv run python -m app.main`, then `curl -X POST http://localhost:8000/api/summarize` with a >5 MiB body (e.g. `--data-binary @big.json`) and confirm a 413 `BODY_TOO_LARGE` response, then confirm a valid small request is still served normally

## Workflow follow-up

- Run `/opsx-validate` in a fresh session (a model that did not write the code) before archiving.
- Bump the minor version with `uv version --bump minor` before archiving (user-visible change; per AGENTS.md never hand-edit `pyproject.toml`).
- Archive the change with `/opsx-archive` after validation passes.
