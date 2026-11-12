# `app/model_discovery.py` — live model discovery

## Purpose

Discovers the models a configured provider actually serves by calling its
OpenAI-compatible `GET {baseURL}/models` endpoint on demand — the backing
call for `GET /api/providers/{id}/available-models`, which powers the UI's
"Refresh from backend" affordance. Discovery is **advisory**: it only lists
what the backend offers; the operator explicitly adds models (see
[`provider_overrides.py`](provider_overrides.html)), and a failed discovery
never alters the effective model list.

## Public surface

- `list_models(provider, timeout=None) -> list[str]` — one discovery call
  for a file-config `Provider`; returns the discovered id strings.
- `discovery_timeout() -> float` — resolves `MODEL_DISCOVERY_TIMEOUT`
  (default 15 s) at call time; non-numeric values fall back to the default.
- `DEFAULT_DISCOVERY_TIMEOUT` (15.0) / `MAX_DISCOVERED_MODELS` (200).
- `ModelDiscoveryError` — the failure signal with a machine-readable
  `reason` and a safe `detail`.
- `_get_provider_models(base_url, api_key, timeout) -> dict` — the HTTP
  seam (the test double point, mirroring `summarize._call_chat_completions`).

## Invariants

- **No FastAPI imports.** The call is a plain synchronous function meant to
  be run in a worker thread; the endpoint runs it on its own bounded pool
  (`DISCOVERY_EXECUTOR`, 2 workers) — separate from the summarization pool
  so a hanging `/models` call cannot starve summarization and vice versa.
- **Only operator-configured base URLs are contacted.** The endpoint
  resolves the provider against the read-only file config first; the overlay
  never changes which URL discovery hits. No other URL is ever reachable
  through this endpoint.
- **Bearer token only when a key is configured.** The `Authorization` header
  is attached only when the provider defines an `apiKey` (keyless local
  backends get none).
- **Secrets never leave the server.** The response is a bare `models` array
  of id strings; no base URL, no API key. Log details are type names and
  app-constructed reasons — never the URL or the response body.
- **Strict parsing, bounded output.** Only dict entries of the `data` array
  with a non-empty string `id` are kept; duplicates are removed preserving
  first occurrence; the result is capped at 200 ids.
- **Every failure is a 502 `PROVIDER_ERROR`** with a machine-readable
  reason (`unreachable`, `timeout`, `http_error`, `malformed_response` — the
  same taxonomy as the summarization call).

## Log events emitted

- `provider_models_refreshed` (info): `provider`, `count`, `duration_ms`.
- `provider_models_refresh_failed` (error): `provider`, `reason`
  (machine-readable), `detail` (safe), `duration_ms`.

Exactly one of the two per call.

## Error codes raised/handled

`ProviderError` (`PROVIDER_ERROR` 502) on any backend failure; the endpoint
maps an unknown provider id to `InvalidProviderError` (`INVALID_PROVIDER`
400) before any network call.

## Design decisions

Resolved from `add-summarization-model-management`:

- **D6** — a separate FastAPI-free module with a replaceable HTTP seam, a
  bounded 15 s timeout (`MODEL_DISCOVERY_TIMEOUT`), a dedicated 2-worker
  executor, strict `data[].id` parsing with dedupe/cap, and secret-free
  failure reporting.
- **D6 (rejected alternative)** — auto-adding every discovered model was
  rejected: discovery is advisory, so an unexpected backend cannot silently
  expand the picker. Manual entry always works as the fallback when a
  provider has no `/models` endpoint.

## Cross-links

- [`providers.py`](providers.html) — the file config the provider is resolved against
- [`provider_overrides.py`](provider_overrides.html) — the overlay the UI adds discovered ids to
- [`summarize.py`](summarize.html) — the sibling backend call whose seam and failure taxonomy this mirrors
- [`main.py`](main.html) — `GET /api/providers/{id}/available-models`
- [`errors.py`](errors.html) — `PROVIDER_ERROR` / `INVALID_PROVIDER`
