# Design

## Context

`save_transcript(text, title, video_id)` in `app/persist.py` is the sole write path: it derives the file name from the title, writes `text + "\n"` as UTF-8 to the transcript directory, and never raises (best-effort, per the existing `transcript-persistence` spec). The endpoint in `app/main.py` calls it after a successful fetch with exactly `(result.text, result.title, result.video_id)`; the fetch chain and the fetchers deal only in video IDs — the original request URL is reduced to `video_id` by `app/urls.py` and never reaches the persistence layer. The read side (`app/library.py`) serves whatever bytes are in the file, content-agnostically. Requirements live in the `transcript-persistence` and `transcript-library` deltas; this document covers how.

## Goals / Non-Goals

**Goals:**
- Every newly written transcript file is self-describing: its first line is the video's watch URL, the rest is the transcript plus a single trailing newline.
- Confine the code change to `app/persist.py` and the tests — no signature changes, no call-site changes, no changes to the chain, the endpoint, or the read side.
- Keep the writer best-effort and its logging shape unchanged.

**Non-Goals:**
- Rewriting or backfilling files already on disk (old files keep their headerless format; the read path is content-agnostic, so mixed formats coexist harmlessly).
- Preserving the caller's original request URL (with `t=`, `list=`, etc.) — see decision 1.
- Adding a title or other metadata lines, a separator blank line, or a structured header format (JSON/YAML front matter).

## Decisions

### 1. The header is the watch URL reconstructed from the video ID
The original request URL is discarded when the reference is parsed, and `save_transcript` already receives `video_id`. The header is therefore `https://www.youtube.com/watch?v=<video_id>`, built inside `save_transcript` — no parameter or call-site changes.
- *Alternative: thread the original request URL through `main.py` → `save_transcript`* — rejected: it requires a signature change and a new call-site argument, and it would make the file content depend on the URL variant the caller happened to use. Two different watch URLs for the same video would produce different bytes for the same file, breaking the existing "re-fetch of the same video rewrites identical bytes" property that makes plain overwrite and crash-repair harmless. The watch URL is the canonical identity of the video and matches the spec's "the video's watch URL" wording.

### 2. Header format: bare URL, first line, no label, no blank separator
The written content becomes `url + "\n" + text + "\n"`. A bare URL (not `Video: <url>` or similar) keeps the line machine-parseable — the transcript is the file with its first line removed — and is the most literal reading of "video URL as a header". No blank line between header and transcript, so the transcript occupies exactly lines 2..N as before.
- *Alternative: labeled line (`Video: ...`)* — rejected as needless decoration; a consumer that wants the URL still has to strip a prefix, while the bare form is stripped with `splitlines(keepends=True)[1:]`.

### 3. Build the header in `save_transcript` before encoding; logging is untouched
The content string is assembled (URL line + transcript + trailing newline) before `content.encode("utf-8")`, so the existing `bytes` field of the `transcript_saved` log event — computed from the encoded content — naturally counts the header line with zero code change. The structured-logging spec is unaffected (its fields are unchanged and the `bytes` semantics — "byte count written" — still hold). The docstring of `save_transcript` is updated to describe the header.

### 4. No migration
Only writes performed by the new code carry the header. The read endpoint, the list endpoint, and the web interface are content-agnostic and work unchanged on both old and new files, including a directory that mixes them.

## Test Strategy

All changes are asserted against exact file bytes in the existing suites:
- `tests/test_persistence.py` —
  - **New** `test_saved_file_starts_with_video_url_header` (T-TRANSCRIPT-PERSISTENCE-012): writer-level — `save_transcript` for video `dQw4w9WgXcQ` produces a file whose first line is the watch URL and whose remainder equals the transcript text plus a trailing newline.
  - **Updated** content assertions in `test_directory_from_environment_variable`, `test_successful_fetch_writes_file` (T-001, expected content now `url + "\n" + response text + "\n"`), `test_refetch_overwrites_existing_file` (T-008), and `test_distinct_videos_same_title_last_write_wins` (T-011 — the winning line carries the second video's URL).
  - **Updated** `test_successful_save_logged` (T-STRUCTURED-LOGGING-010): the `bytes` expectation includes the header line's bytes.
- `tests/test_transcript_library.py` — **updated** `test_read_roundtrips_after_successful_fetch` (T-TRANSCRIPT-LIBRARY-008): expected read text and on-disk bytes are `url + "\n" + text + "\n"`.
- **Run** — `uv run python -m pytest tests/ -q --ignore=tests/e2e` (unit/API/logging) and `uv run python -m pytest tests/e2e/ -q` (UI; the e2e stub server serves the same content it always did for fetches, and the saved-transcript flow asserts file-vs-read equality rather than fixed content, so no e2e test body should change — if one fails, it indicates an unexpected content assumption to surface, not to silently patch).

## Risks / Trade-offs

- [Downstream consumers of saved files expect a bare transcript] → one extra leading line; documented as breaking for file consumers in the proposal. Consumers that extract the transcript can drop the first line.
- [Clicking a saved transcript in the UI now shows the URL line in the panel] → accepted: the panel already shows the file content verbatim (plain-text insertion only), and the URL is useful provenance there; no spec or UI code changes.
- [A directory mixes headerless (pre-change) and headed files] → accepted per decision 4; nothing in the read side or the list depends on the format.
- [The watch URL is a canonical guess, not the URL the user submitted] → accepted; the video ID is the file's identity, so the header stays stable across fetches of the same video (see decision 1).

## Migration Plan

Deploy the new build (`docker compose up -d --build` per README). No data migration, no mount or config change: only new writes carry the header, and existing files are served and re-overwritten (with the header) as they are re-fetched. Rollback: redeploy the previous build; both builds read and list any mix of file formats correctly.

## Open Questions

None — the only genuinely open design point (original URL vs. reconstructed watch URL) was resolved in decision 1.
