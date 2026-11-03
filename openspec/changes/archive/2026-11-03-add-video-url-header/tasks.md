# Tasks

## 1. Header in the writer

- [x] 1.1 In `app/persist.py`, change `save_transcript` to build the file content as `https://www.youtube.com/watch?v=<video_id>` + newline + the transcript text + a single trailing newline before encoding (design decisions 2 and 3), and update its docstring to describe the header; keep the signature, the best-effort catch-and-log behavior, and the `transcript_saved`/`transcript_save_failed` events unchanged; verify by adding `test_saved_file_starts_with_video_url_header` (T-TRANSCRIPT-PERSISTENCE-012) to `tests/test_persistence.py` — `save_transcript` for video `dQw4w9WgXcQ` writes a file whose first line is `https://www.youtube.com/watch?v=dQw4w9WgXcQ` and whose remainder equals the transcript text plus a trailing newline — and running `uv run python -m pytest tests/test_persistence.py -q` and confirming the new test passes (pre-existing content assertions will fail until group 2)

## 2. Persistence test suite

- [x] 2.1 Update the file-content assertions in `tests/test_persistence.py` to include the URL header line: `test_directory_from_environment_variable` (expected `"https://www.youtube.com/watch?v=dQw4w9WgXcQ\nhello world\n"`), `test_successful_fetch_writes_file` (T-TRANSCRIPT-PERSISTENCE-001, expected `url + "\n" + response.json()["text"] + "\n"`), `test_refetch_overwrites_existing_file` (T-TRANSCRIPT-PERSISTENCE-008), and `test_distinct_videos_same_title_last_write_wins` (T-TRANSCRIPT-PERSISTENCE-011; the winning content carries the second video's URL `https://www.youtube.com/watch?v=bbbbbbbbbbb`); verify with `uv run python -m pytest tests/test_persistence.py -q`
- [x] 2.2 Update `test_successful_save_logged` (T-STRUCTURED-LOGGING-010) so the expected `bytes` field counts the header line's bytes as well as `"hello\n"`; verify with `uv run python -m pytest tests/test_persistence.py -q` until the whole file passes

## 3. Library round-trip test

- [x] 3.1 Update `test_read_roundtrips_after_successful_fetch` (T-TRANSCRIPT-LIBRARY-008) in `tests/test_transcript_library.py` so the expected read text and the expected on-disk bytes are `https://www.youtube.com/watch?v=dQw4w9WgXcQ\n` + the transcript text + a trailing newline, and confirm the read still round-trips byte-for-byte with the saved file; verify with `uv run python -m pytest tests/test_transcript_library.py -q`

## 4. Integration verification

- [x] 4.1 Run the full unit/API/logging suite with `uv run python -m pytest tests/ -q --ignore=tests/e2e` and confirm zero failures
- [x] 4.2 Run the end-to-end UI suite with `uv run python -m pytest tests/e2e/ -q` (installing Chromium once via `uv run python -m playwright install chromium` if needed) and confirm the page flow, the saved-transcript list, and the download behavior are unaffected; if an e2e test fails on fixed transcript content, surface it as a design assumption to revisit rather than silently patching it (design Test Strategy)
- [x] 4.3 Smoke test the deployed container per the README: `docker compose up -d --build`, fetch a known video with captions via the curl command in the README, and confirm the HTTP response is unchanged, the `.txt` file in the mounted host directory starts with the video's watch URL followed by the transcript, and `docker logs yt-transcript` shows a `transcript_saved` event whose byte count includes the header line

## 5. Version bump

- [x] 5.1 Bump the app's minor version via `uv version --bump minor` (0.1.0 → 0.2.0 — the saved-file format change is BREAKING for file consumers per the proposal, and under 0.x versioning a breaking change takes a minor bump); verify `pyproject.toml` reads `version = "0.2.0"` and `uv.lock`'s root package version matches

## Workflow follow-up

- Validate the change in a fresh session (`/opsx-validate`) before archiving (`/opsx-archive`).
