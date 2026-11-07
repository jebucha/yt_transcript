# Proposal

## Why

The code's rationale (module purposes, invariants, the "design decision N"
references in comments) is scattered across docstrings, archived change
design docs, and the README. A future maintainer — human or AI agent — has no
single browsable place to see what each file is for and which rules govern
it. This adds a per-file documentation set under `docs/` with a browsable
HTML entry point.

## What Changes

- New `docs/` directory: one Markdown page per file in `app/` — the 12
  Python modules (including `app/__init__.py`, documented as the package) and
  the 3 static UI files (`app.js`, `index.html`, `style.css`) — plus one page
  each for the two deployment configs (`Dockerfile`, `docker-compose.yml`,
  under `docs/deploy/`) and the provider config template
  (`providers.json.example`).
- A `docs/index.html` (and `index.md`) landing page with the system-flow map
  and links to every page, so the docs are browsable by opening a single file
  in a browser.
- Generated HTML counterparts for every page (Markdown is the single source
  of truth), a shared self-contained stylesheet, and a small generator
  script (`docs/generate.py`) that renders the `.md` files to `.html` with a
  shared navigation sidebar.
- One new dev-only dependency: `markdown` (exactly pinned), used by the
  generator only.
- README: a pointer line to `docs/` in the Layout section. No other README
  changes; user-facing content stays in the README.

## Capabilities

### New Capabilities

(none — documentation only; `skip_specs: true` is set in the change metadata)

### Modified Capabilities

(none — no spec-level behavior changes)

## Impact

- New files: `docs/*` (19 `.md` + 19 generated `.html` pages, `style.css`,
  `generate.py`).
- Modified: `README.md` (pointer line only), `providers.json.example`
  (sample updated to a single OpenAI-compatible provider entry),
  `pyproject.toml` / `uv.lock` (one pinned dev dependency via
  `uv add --dev markdown`).
- No runtime, API, or behavior changes. The application code is untouched.
