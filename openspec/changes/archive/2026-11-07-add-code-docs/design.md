# Design

## Context

See proposal.md for motivation. Constraints that shape the approach:

- The app itself is vanilla, no-build-step, no-CDN; the docs should honor
  the same spirit (browsable from a fresh clone by opening one file in a
  browser).
- Every `app/` module already carries a substantial docstring and
  rationale-bearing comments ("design decision N"). Those comments point at
  design docs buried in `openspec/changes/archive/*/design.md`.
- The environment has no pandoc; the repo uses uv with exact-pinned
  dependencies and a dev dependency group.
- 18 documented files: 12 Python modules (including the package's
  `__init__.py`), 3 static UI files, 2 deployment configs (`Dockerfile`,
  `docker-compose.yml`), and the provider config template
  (`providers.json.example`).

## Goals / Non-Goals

**Goals:**

- One browsable page per file in `app/`, module-level, invariant-forward,
  suitable for both a returning human and an AI agent working the repo.
- A single `docs/index.html` entry point with the system-flow map and links
  to every page; navigation works entirely via relative links, no CDN.
- One regeneration command to re-render all HTML from Markdown.

**Non-Goals:**

- No function-by-function walkthroughs (would restate code and drift first).
- No restructuring or moving of user-facing content out of README.md
  (pointer line only).
- No build tooling, framework, or site generator; no docs CI.
- No doc generation for `tests/`.

## Decisions

**D1: Markdown is the single source of truth; HTML is generated and
committed.**

Alternatives considered: (a) hand-written HTML only — no drift risk but a
harder edit surface for 16 pages; (b) hand-written both — double
maintenance, rejected; (c) generate on demand and git-ignore the HTML —
breaks "open one file in a fresh clone". Chosen: write `.md`, render to
`.html` with a small committed script, commit both. Editing docs means:
edit the `.md`, run `uv run python docs/generate.py`, commit the `.html`.

**D2: One pinned dev-only dependency — `markdown` — for the generator.**

No pandoc exists in the environment. `uv add --dev markdown` (uv pins
exactly by default) goes into the existing dev group; the runtime and the
image are unaffected (the Docker build installs the main group only).
The generator enables only `fenced_code` and `tables` extensions — no
pygments/codehilite, keeping the dependency surface at exactly one
package. Code blocks are styled by the shared CSS.

**D3: Layout — flat for Python modules, `static/` subfolder for UI files,
`deploy/` subfolder for deployment configs.**

`docs/index.{md,html}` is the landing page; the 12 module pages sit flat
(`docs/main.md`, …, `docs/__init__.md`). The 3 UI pages live under
`docs/static/` with prefixed names (`app-js`, `index-html`, `style-css`)
— required because the UI's own `index.html` would otherwise collide with
the docs landing page. The 2 deployment config pages live under
`docs/deploy/` with suffixed names (`Dockerfile`, `compose-yml`); the
provider config template page sits flat as `providers-json-example` so the
file's `.example` suffix stays out of the link target.

**D4: Page content contract (module level, ~40–80 lines each).**

Every page, in this order: purpose (what role the file plays), public
surface (what it exports and who uses it), invariants (rules that must
keep holding, e.g. "no FastAPI imports", "blocking I/O only via
`asyncio.to_thread`", "fetch-chain semaphore only"), log events emitted,
error codes raised/handled, design decisions (the relevant "design
decision N" items resolved from the archived change design docs), and
cross-links to related pages. Invariants lead for agent readers.
The landing page carries the ASCII system-flow map plus a table of
contents linking every page.

**D5: Shared shell — one stylesheet, one nav, injected by the generator.**

`docs/style.css` (self-contained, no fonts, no CDN) is referenced by every
generated page. The generator wraps each rendered page in a fixed shell:
title, a sidebar linking the index and all 18 pages, and the rendered
body. The landing `index.html` is rendered from `index.md` like any other
page.

## Risks / Trade-offs

- [Docs drift from code] → pages are deliberately short and invariant-
  forward (document *why* and *rules*, not *what the code says*); the
  contract in D4 makes stale-restatement less likely.
- [Committed HTML desyncs from its `.md` after an edit] → the regenerate
  command is one line and called out in the docs index and README pointer;
  a diff of the generated `.html` after regenerate is how drift shows up
  in review.
- [Generator becomes a second mini-app to maintain] → it is a single
  script (~100 lines), stdlib + `markdown` only, no config; if it ever
  rots, deleting it and hand-updating HTML is a bounded fallback.
- [New dev dependency] → exactly pinned, dev group only, zero runtime or
  image impact.

## Open Questions

(none)

## Test Strategy

No spec-level behavior changes (`skip_specs: true`), so this change
defines no Test Requirement blocks. Verification is the integration
checks in tasks.md group 5, run via `uv run`: idempotent regeneration
(5.1), link resolution (5.2), and the existing test suite plus the
Dockerfile dev-group exclusion (5.3).
