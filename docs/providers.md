# `app/providers.py` — summarization provider config

## Purpose

Reads, parses, and validates the provider config file that drives
summarization — on **every call**, never at startup. The result is a plain
structure of usable providers plus the default provider id, or the empty
"not configured" state.

## Public surface

- `load_providers() -> ProviderConfig` — one config read.
- `config_path() -> Path` — resolves `PROVIDERS_CONFIG` (default
  `providers.json` in the working directory) at call time.
- `Provider` — frozen dataclass: `id`, `name` (display, falls back to the
  id), `base_url`, `api_key` (optional), `models` (tuple of ids, file
  order), and `added_models` (tuple of overlay-supplied ids; empty for
  file-only reads).
- `ProviderConfig` — frozen dataclass: `providers` (tuple) + `default`
  (id or `None`).

## Invariants

- **No FastAPI imports.** The reader is pure over the config file path so it
  is testable directly against `tmp_path`.
- **Read per call, never cached, never at startup.** Edits take effect on
  the next request without a restart, and the app boots with no config at
  all.
- **Missing file is the normal "not configured" state** — an empty result
  with *no* log entry. An unreadable file, malformed JSON, a malformed
  structure, or a file with no usable provider all return the empty result
  **without raising**, and additionally log one `config_load_failed` error
  event carrying the path and the parse error detail.
- **A provider is usable only with a non-empty string `options.baseURL` and
  a non-empty `models` map** (its keys are the model ids, in JSON file
  order). Unknown fields are ignored; a missing/empty display name falls
  back to the provider id; `apiKey` may be absent (keyless local backends).
- **`default` resolution:** an explicit top-level `"default"` key wins when
  it names a usable provider; otherwise the first provider in file order;
  otherwise `None`.
- **Secrets never leave this module's memory in logs.** The `detail` of a
  failed load is the parse error only — never the file's contents.

## Log events emitted

- `config_load_failed` (error): `path`, `reason`
  (`invalid_json`, `invalid_structure`, or the OS exception type name),
  `detail` (the parse error — never file contents).

## Error codes raised/handled

None raised — all failures degrade to the empty `ProviderConfig`; the
endpoint turns that into `NOT_CONFIGURED` 503.

## Design decisions

Resolved from `add-transcript-summary`:

- **decision 2** — module layout: FastAPI-free config reader, plain
  structure, zero FastAPI import leakage.
- **decision 3** — config read per request, never at startup: boot
  without config, hot-reload edits, tiny file so per-request reads are
  negligible. (An explicit `PROVIDERS_CONFIG` pointing at a host file is the
  compose deployment shape from **decision 12**.)
- **decision 13** — logging discipline: parse error detail only, never file
  contents; a missing file is not a logged failure.

## The writable overlay (provider_overrides.json)

This file is **operator-owned and read-only** (compose mounts it
read-only); the app never writes it. UI-added model ids do not go here —
they live in a separate writable overlay, `provider_overrides.json` in the
transcript directory, owned by [`provider_overrides.py`](provider_overrides.html)
(shape `{"<providerId>": ["model-id", ...]}`). The effective provider list
the endpoints see is the merge of the two, per request:

- the provider set comes **only** from this config file — the overlay can
  never introduce a provider, a base URL, or an API key, and entries for
  unknown provider ids are ignored;
- a provider's effective models are its config-file models in file order,
  followed by its non-duplicate overlay ids, and the overlay ids actually
  used are carried on `Provider.added_models` (the `addedModels` field of
  `GET /api/providers`);
- a missing or malformed overlay file means "no additions" (it degrades to
  exactly this file's models, logging `provider_overrides_load_failed`), so
  with no overlay the behavior is the file-only behavior exactly.

`load_providers()` stays file-only; the endpoints compose
`apply_overrides(load_providers(), load_overrides())` (see
[`provider_overrides.py`](provider_overrides.html)).

## Cross-links

- [`provider_overrides.py`](provider_overrides.html) — the writable model overlay merged over this config
- [`model_discovery.py`](model_discovery.html) — live discovery of a provider's `/models`
- [`summarize.py`](summarize.html) — consumes `Provider` for the backend call
- [`main.py`](main.html) — `GET /api/providers` (secret-free listing), the add/remove/discover endpoints, and the per-request reads
- [`errors.py`](errors.html) — `NOT_CONFIGURED` / `INVALID_PROVIDER` / `INVALID_MODEL` / `MODEL_NOT_REMOVABLE`
