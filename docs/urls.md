# `app/urls.py` — YouTube video reference parsing

## Purpose

Pure parsing and normalization of the user-supplied video reference into the
11-character video ID that the rest of the app deals in. Nothing in this
module touches the network — it decides whether a string is a recognizable
YouTube reference and extracts the ID, or raises `InvalidUrlError`.

## Public surface

- `parse_video_ref(ref: str) -> str` — returns the video ID or raises.
- `VIDEO_ID_RE` — `^[A-Za-z0-9_-]{11}$`, the canonical ID shape.

Accepted inputs:

- Standard watch URLs: `https://www.youtube.com/watch?v=<id>` — and the
  `m.`, `music.`, or any subdomain variants of `youtube.com` and
  `youtube-nocookie.com`.
- Short links: `https://youtu.be/<id>`.
- Bare video IDs: 11 characters of `[A-Za-z0-9_-]`.

## Invariants

- **No network access, ever.** This is the first step of the fetch chain and
  runs *before* the single-flight semaphore is acquired, so a malformed URL
  can never consume the fetch slot.
- **Anything not recognized is `InvalidUrlError`** — the function fails
  closed: no lenient extraction, no guessing.
- **The original URL is discarded.** Downstream code (fetchers, persistence)
  works only with the video ID; the persisted file's header is the watch URL
  *reconstructed* from the ID, not the string the user pasted.
- Hostname matching is subdomain-aware (`hostname == host or endswith("." + host)`)
  and case-insensitive; the `v` query parameter is the only query parameter
  consulted.

## Log events emitted

None — parsing failures surface as the `InvalidUrlError` the endpoint maps to
HTTP 400 (the endpoint's `http_request` line is the only log of the request).

## Error codes raised/handled

Raises: `InvalidUrlError` (code `INVALID_URL`, HTTP 400). Handles: malformed
`urlparse` input (`ValueError` → `InvalidUrlError`).

## Design decisions

Resolved from `2026-10-29-youtube-transcript`:

- **D7** (API shape) — `POST /api/transcript` takes `{"url": "..."}` and the
  taxonomy's `INVALID_URL`/400 entry is how this module's rejection reaches
  the client.

The watch-URL-reconstructed-from-the-ID behavior this module enables is
settled in `2026-11-03-add-video-url-header` decision 1: the video ID is the
file's identity, so the persisted header stays stable across fetches of the
same video regardless of which URL variant the user pasted.

## Cross-links

- [`chain.py`](chain.html) — the caller; parsing happens before its semaphore
- [`errors.py`](errors.html) — `InvalidUrlError`
- [`persist.py`](persist.html) — reconstructs the watch URL from the same ID
