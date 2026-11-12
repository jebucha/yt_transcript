# `app/provider_overrides.py` — provider model overlay

## Purpose

Reads and writes the writable model-overlay file
(`provider_overrides.json` in the transcript directory) that holds the model
ids the operator adds through the web UI. The file is read on **every
call**, never at startup, and merged over the read-only
[`providers.json`](providers.html) config into the effective provider list
the endpoints serve and validate against. The overlay shape is
`{"<providerId>": ["model-id", ...]}`.

## Public surface

- `load_overrides() -> dict[str, list[str]]` — one overlay read
  (provider id → model ids, file order).
- `apply_overrides(config, overrides) -> ProviderConfig` — pure merge: file
  models first, appended non-duplicate overlay ids, provenance in
  `Provider.added_models`.
- `add_model(provider, model_id) -> list[str] | None` — locked, atomic
  read-modify-write add; returns the effective model list, or `None` on a
  failed write.
- `remove_model(provider, model_id) -> list[str] | None` — locked, atomic
  remove of an overlay id; returns the remaining effective list, or `None`
  on a failed write.
- `is_valid_model_id(model_id) -> bool` — the id rules (design D5).
- `overrides_path() -> Path` — resolves the overlay file under
  `persist.transcript_dir()` at call time.
- `MAX_MODEL_ID_CHARS` (200) / `MAX_ADDED_PER_PROVIDER` (50) — the bounds.
- `ModelNotFoundError` — the remove-side 404 signal (plain HTTP status,
  deliberately outside the [`errors`](errors.html) taxonomy).

## Invariants

- **No FastAPI imports.** The reader, merge, and writer are pure over
  `persist.transcript_dir()` so they are testable directly against
  `tmp_path`, mirroring `providers.py` and `settings.py`.
- **Read per call, never cached, never at startup.** Edits on disk (by hand
  or by the endpoints) take effect on the next request without a restart,
  and the app boots with no overlay file at all.
- **A missing file is the normal "no additions" state** — an empty result
  with *no* log entry. An unreadable file, malformed JSON, or a non-object
  top level degrades to no additions **without raising** and logs exactly
  one `provider_overrides_load_failed` error event.
- **The overlay never widens the trust boundary.** It only extends the model
  list of providers defined in the config file: no new providers, base
  URLs, or API keys; entries for unknown provider ids are ignored (and left
  on disk — no destructive prune).
- **Merge order is fixed:** config-file models in file order, then overlay
  ids not already present (first occurrence kept). `added_models` carries
  only the overlay ids actually used, in the same order they appear in
  `models`.
- **Writes are atomic and locked.** `add_model` / `remove_model` run the
  read-modify-write under a module-level lock (the app is single-process; a
  multi-process deployment would need an OS file lock — documented
  non-goal) and persist via a sibling temp file + `os.replace`, so a crash
  mid-write never leaves a truncated file and a failure never leaves partial
  state.
- **Model id bounds (design D5):** a trimmed, non-empty id of at most 200
  characters, free of control characters, at most 50 overlay additions per
  provider.
- **Secret discipline.** No event carries an API key, a base URL, or the
  file's contents — only paths, machine-readable reasons, and OS/parse
  error details.

## Log events emitted

- `provider_overrides_load_failed` (error): `path`, `reason`
  (`invalid_json`, `invalid_structure`, or the OS exception type name),
  `detail` (the parse error — never file contents).
- `provider_overrides_save_failed` (error): `path`, `reason` (the OS
  exception type name), `detail`.
- `provider_model_added` (info): `provider`, `model` — one per successful
  new addition (an idempotent add of an already-present id logs nothing).
- `provider_model_removed` (info): `provider`, `model`.

## Error codes raised/handled

`add_model` raises `InvalidModelError` (`INVALID_MODEL` 400) when the
per-provider addition cap would be exceeded; `remove_model` raises
`ModelNotRemovableError` (`MODEL_NOT_REMOVABLE` 400) for a config-file model
and `ModelNotFoundError` (endpoint maps it to 404 `NOT_FOUND`) for an id in
neither set. A failed write returns `None` (the failure is already logged)
and the endpoints map it to 500 `WRITE_FAILED`. The endpoints also raise
`InvalidProviderError` for a provider id absent from the config file.

## Design decisions

Resolved from `add-summarization-model-management`:

- **D1** — a separate writable overlay in the already-mounted, writable
  transcript directory, not a writable `providers.json` (read-only mount,
  holds secrets) nor an extended `settings.json` (blind whole-file
  overwrite).
- **D2** — effective config = file config plus overlay, with provenance
  carried on `Provider.added_models`; the provider set comes only from the
  file config.
- **D3** — read-modify-write under a process lock with atomic `os.replace`,
  mirroring `settings.save_settings`; per-call reads so edits need no
  restart.
- **D5** — validation and bounds live here: trimmed 1–200 char id, no
  control characters, 50 additions per provider.

## Cross-links

- [`providers.py`](providers.html) — the read-only file config this overlay merges over
- [`model_discovery.py`](model_discovery.html) — live `/models` discovery the UI adds from
- [`persist.py`](persist.html) — `transcript_dir()`, the path this module shares
- [`library.py`](library.html) — the `.txt`-only listing that ignores `provider_overrides.json`
- [`main.py`](main.html) — the add/remove/discover endpoints that compose the merge
- [`errors.py`](errors.html) — `INVALID_MODEL` / `MODEL_NOT_REMOVABLE`
