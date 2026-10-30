# Tasks

## 1. File name derivation

- [x] 1.1 Create `app/persist.py` (no FastAPI imports) with the pure function `derive_file_name(title, video_id) -> str` implementing design decision 3: Unicode-aware lowercase, runs of non-alphanumeric characters replaced by a single `_`, edges trimmed, empty result falls back to the video ID, and names over 255 bytes (with `.txt`) are truncated on a character boundary with `_<video_id>` appended so the result still fits; verify by adding `tests/test_persistence.py` with `test_filename_typical_title`, `test_filename_punctuation_only_title_falls_back_to_video_id`, `test_filename_slash_in_title_stays_in_directory`, `test_filename_unicode_title_preserved`, and `test_filename_overlong_title_truncated_with_video_id` (T-TRANSCRIPT-PERSISTENCE-003 through 007) and running `python -m pytest tests/test_persistence.py -q` until all pass

## 2. Best-effort writer and save logging

- [x] 2.1 In `app/persist.py`, add a `transcript_dir()` helper that reads the `TRANSCRIPT_DIR` environment variable at call time with the default `/transcripts` (same pattern as `_listen_port` in `app/main.py`), and `save_transcript(text, title, video_id)` that writes `text` + trailing newline as UTF-8 to `<dir>/<derived name>` with plain overwrite, never raises to the caller, and logs `transcript_saved` (video ID, path, byte count) on success or `transcript_save_failed` (video ID, reason) on any write error (`except Exception`); verify with `test_directory_from_environment_variable` (T-TRANSCRIPT-PERSISTENCE-010), `test_unwritable_directory_still_returns_transcript` (T-TRANSCRIPT-PERSISTENCE-009), `test_successful_save_logged` (T-STRUCTURED-LOGGING-010), and `test_failed_save_logged` (T-STRUCTURED-LOGGING-011) in `tests/test_persistence.py` using a temporary directory and an unwritable path, and running `python -m pytest tests/test_persistence.py -q` until all pass

## 3. Endpoint integration

- [x] 3.1 In `app/main.py`, call the writer from `transcript_endpoint` after a successful `chain_mod.default_chain.run` via `asyncio.to_thread`, leaving the response construction untouched (design decisions 1 and 5); verify with `test_successful_fetch_writes_file` (T-TRANSCRIPT-PERSISTENCE-001, asserting file contents equal the response text plus a trailing newline), `test_failed_fetch_writes_no_file` (T-TRANSCRIPT-PERSISTENCE-002), and `test_refetch_overwrites_existing_file` (T-TRANSCRIPT-PERSISTENCE-008), and `test_distinct_videos_same_title_last_write_wins` (T-TRANSCRIPT-PERSISTENCE-011) in `tests/test_persistence.py` using the project's existing chain-mocking pattern, and running `python -m pytest tests/test_persistence.py -q` until all pass

## 4. Deployment configuration and docs

- [x] 4.1 Add `TRANSCRIPT_DIR=/transcripts` to the `ENV` block in `Dockerfile` and verify the build still succeeds (`docker build -t yt-transcript .`) with the variable present in the image
- [x] 4.2 Add `volumes: - "${TRANSCRIPTS_DIR:-/home/john/transcripts}:/transcripts"` to the `app` service in `docker-compose.yml` and verify the mount resolves with default and overridden values via `docker compose config` (and `podman compose config` where available, matching the README's dual-provider convention)
- [x] 4.3 Update `README.md`: adjust the "zero state, no database" line to describe the one-file-per-transcript bind-mounted directory, document the mount and the `TRANSCRIPTS_DIR` `.env` override in the compose section, and add the host-directory permissions note for native Linux (unprivileged `appuser` vs. host ownership); verify by re-reading the sections and confirming the smoke test instructions remain accurate (API behavior is unchanged)

## 5. Integration verification

- [x] 5.1 Run the full unit/API/logging suite with `uv run python -m pytest tests/ -q --ignore=tests/e2e` and confirm zero failures
- [x] 5.2 Run the end-to-end UI suite with `uv run python -m pytest tests/e2e/ -q` (installing Chromium once via `uv run python -m playwright install chromium` if needed) and confirm the page flow is unaffected
- [x] 5.3 Smoke test the deployed container per the README: `docker compose up -d --build`, fetch a known video with captions via the curl command in the README, and confirm the response is unchanged, a correctly named `.txt` file appears in `/home/john/transcripts`, and `docker logs yt-transcript` shows a `transcript_saved` event with the file path and byte count
