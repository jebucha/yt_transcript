# Tasks

## 1. Tooling (generator + shared shell)

- [x] 1.1 Add `markdown` as an exactly-pinned dev dependency via `uv add --dev markdown` and verify `pyproject.toml` shows the exact pin and `uv run python -c "import markdown"` succeeds
- [x] 1.2 Create `docs/generate.py` (stdlib + `markdown` only; `fenced_code` and `tables` extensions; fixed nav shell linking the index and all pages; relative links to `docs/style.css`) and `docs/style.css` (self-contained, no CDN, no web fonts), with a temporary minimal `docs/index.md`; verify `uv run python docs/generate.py` renders a well-formed `docs/index.html` with the nav and stylesheet reference

## 2. Python module pages (12)

Each page follows the D4 content contract: purpose, public surface, invariants, log events emitted, error codes raised/handled, resolved "design decision N" items (from `openspec/changes/archive/*/design.md`), cross-links. ~40–80 lines, module-level.

Resolution note: "design decision N" is numbered *per archived change* — N refers to the Nth decision in the design doc of the change that introduced the behavior (e.g. the decisions cited in `app/summarize.py` resolve to `archive/add-transcript-summary/design.md`, whose decisions are numbered 1–13; those cited in `app/library.py` resolve to `archive/2026-10-30-add-transcript-persistence/design.md`). Match each cited decision's content against the module's comments to find the right doc.

- [x] 2.1 Write `docs/__init__.md` (the `app` package: its role, import-time side effects, module inventory) and verify regeneration produces `docs/__init__.html` with the page content
- [x] 2.2 Write `docs/main.md` and verify regeneration produces `docs/main.html` with the page content
- [x] 2.3 Write `docs/chain.md` and verify regeneration produces `docs/chain.html` with the page content
- [x] 2.4 Write `docs/fetchers.md` and verify regeneration produces `docs/fetchers.html` with the page content
- [x] 2.5 Write `docs/urls.md` and verify regeneration produces `docs/urls.html` with the page content
- [x] 2.6 Write `docs/errors.md` and verify regeneration produces `docs/errors.html` with the page content
- [x] 2.7 Write `docs/persist.md` and verify regeneration produces `docs/persist.html` with the page content
- [x] 2.8 Write `docs/library.md` and verify regeneration produces `docs/library.html` with the page content
- [x] 2.9 Write `docs/providers.md` and verify regeneration produces `docs/providers.html` with the page content
- [x] 2.10 Write `docs/summarize.md` and verify regeneration produces `docs/summarize.html` with the page content
- [x] 2.11 Write `docs/log.md` and verify regeneration produces `docs/log.html` with the page content
- [x] 2.12 Write `docs/logbus.md` and verify regeneration produces `docs/logbus.html` with the page content

## 3. Static UI pages (3)

Same D4 contract, adapted for the UI files (behavior, DOM contracts, no-`innerHTML` rule, no-build/no-CDN constraint).

- [x] 3.1 Write `docs/static/app-js.md` and verify regeneration produces `docs/static/app-js.html` with the page content
- [x] 3.2 Write `docs/static/index-html.md` and verify regeneration produces `docs/static/index-html.html` with the page content
- [x] 3.3 Write `docs/static/style-css.md` and verify regeneration produces `docs/static/style-css.html` with the page content

## 4. Landing page + README pointer

- [x] 4.1 Replace the temporary `docs/index.md` with the real landing page (ASCII system-flow map, table of contents linking the other 15 pages, the one-line regenerate command) and verify `docs/index.html` links to every page and the map renders in a `<pre>`
- [x] 4.2 Add the pointer line to `docs/` in the README Layout section (no other README changes) and verify the pointer is visible in `README.md` and no user-facing content moved

## 5. Integration checks

- [x] 5.1 Verify regeneration is idempotent and Markdown is the source of truth: copy the current `docs/` tree to a temp dir, delete every `.html` under `docs/`, run `uv run python docs/generate.py`, and confirm the regenerated `.html` files are byte-identical to the copies (`diff -r`)
- [x] 5.2 Verify every internal link in `docs/index.html` and the generated pages resolves to an existing file under `docs/` (e.g. grep all `href` targets and check each exists)
- [x] 5.3 Verify nothing runtime-related changed: `uv run python -m pytest tests/ -q --ignore=tests/e2e` passes, and the Dockerfile's dependency install still excludes the dev group (inspect the Dockerfile's `uv` invocation)

## Workflow follow-up

- Validate the change (`/opsx-validate`, fresh session) before archiving.
- No version bump: docs are not shipped in the image and are not user-visible product behavior.
- Archive the change after validation.
