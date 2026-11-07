# `providers.json.example` — summarization provider config shape

## Purpose

An example JSON configuration file that defines one or more summarization providers
for the yt-transcript app. Mounted read-only at `/app/providers.json` inside the
Docker container (see docker-compose.yml), it tells the app which backend to send
transcripts through for summarization and how to address each provider's API.

The `.example` suffix is a convention: the file lives in git as a template; operators
copy or edit it to create the real `providers.json`, keeping secrets out of version control.

## Public surface

- **JSON structure:** top-level object with two keys — `"provider"` (map of provider
  definitions) and optionally `"default"` (which provider id to pre-select in the UI).
- **Per-provider fields:**
  - `name` — display name shown in the UI; falls back to `id` if omitted
  - `options.baseURL` — required; API endpoint URL for the provider
  - `options.apiKey` — optional; omitted or non-string values are treated as "no key"
  - `models` — required map of model-id → description (any string value); keys become
    the selectable model options in the UI

```json
{
    "provider": {
        "<id>": {
            "name": "<display name>",
            "options": {
                "baseURL": "https://api.example.com/v1",
                "apiKey": "<your-key>"
            },
            "models": {
                "<model-id-1>": "Model description or label",
                "<model-id-2>": "Another model"
            }
        }
    },
    "default": "<id>"
}
```

## Invariants

- **Valid JSON, top-level object.** Missing file → no providers configured (graceful).
  Invalid JSON or non-object top level → `config_load_failed` error logged.
- **`.example` is a template.** The real file (`providers.json`) must not be committed
  to git; secrets belong in the `.env`-adjacent config, never in version control.
- **Read-only mount.** docker-compose.yml mounts this as `ro`; the app reads it per request
  but never writes or caches it at startup. Edits take effect on the next API call.
- **Default must reference an existing provider id.** If `"default"` is missing, not a
  string, or references a removed provider, the first usable provider becomes default.

## Log events emitted

The app emits `config_load_failed` (error level) when the config file exists but cannot be
parsed — carrying the path, reason (`invalid_json`, `invalid_structure`), and a detail field
with the parse error message. A missing file produces no log entry; it is treated as "not
configured" rather than an error state.

## Error codes raised/handled

- **Missing or unreadable file** → app logs nothing at startup, returns empty provider list;
  `/api/summarize` endpoints return `NOT_CONFIGURED`; `/api/providers` returns an empty array
- **Invalid JSON** → `config_load_failed` logged; same degraded behavior as missing file
- **Missing or invalid `baseURL`** for a provider entry → that provider is silently skipped;
  other providers remain usable
- **No usable providers** (all entries malformed) → same as empty config

## Design decisions

Resolved from the archived change design docs:
- `add-transcript-summary` decision 3 — config read per request, never at startup. This means
  edits take effect immediately and a missing file is always treated as "not configured" rather
  than a hard failure.
- `add-transcript-summary` decision 7 — the `/api/providers` endpoint returns a secret-free list
  of providers (id + name only); API keys never leave the server. The UI picker pre-selects
  whichever provider is marked as default in this file.

## Cross-links

- [`docker-compose.yml`](deploy/compose-yml.html) — mounted at `/app/providers.json:ro` via volume
- [`app/providers.py`](providers.html) — reads and parses this config (`load_providers()`)
- [`main.py`](main.html) — `GET /api/providers` (secret-free listing), `POST /api/summarize`
