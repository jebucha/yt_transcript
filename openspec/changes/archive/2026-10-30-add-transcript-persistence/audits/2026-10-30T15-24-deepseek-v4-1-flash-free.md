# Audit Report: add-transcript-persistence

**Schema:** spec-driven
**Model:** DeepSeek V4.1 Flash Free (deepseek-v4.1-flash-free)
**Audited:** 2026-10-30T15-24
**Artifacts checked:** proposal.md, design.md, specs/transcript-persistence/spec.md, specs/structured-logging/spec.md, tasks.md
**Base specs consulted:** openspec/specs/structured-logging/spec.md, openspec/specs/transcript-retrieval/spec.md, openspec/specs/web-interface/spec.md
**Code verified against:** app/main.py, app/chain.py, app/fetchers.py, app/errors.py, app/log.py, Dockerfile, docker-compose.yml, README.md, pyproject.toml, tests/test_api.py, tests/test_logging_format.py, tests/conftest.py

### Summary
- Errors: 0
- Warnings: 4
- Info: 10

---

### Findings

| ID | Category | Severity | Description | Evidence |
|----|----------|----------|-------------|----------|
| AC-1 | Accuracy | Warning | The design's catch scope is narrower than the spec's best-effort guarantee. The spec requires that a missing/unreadable/unwritable directory "or any other write error" not change the HTTP response, but the design catches only `OSError`, and task 2.1 says both "never raises to the caller" and "on `OSError`". A non-`OSError` failure (e.g. `UnicodeEncodeError` from a lone surrogate in a title) would escape `asyncio.to_thread` and turn a 200 into a 500. | spec.md L94 vs design.md L45/L49; tasks.md §2.1 |
| AC-2 | Accuracy | Warning | A normative clause in "Overwrite on re-fetch" has no scenario. "Distinct videos whose titles derive the same file name are not disambiguated; the most recent write wins" is stated as requirement text, but the only scenario covers re-fetching the *same* video, and design.md L64 relies on this behavior as "spec'd". | spec.md L81–91; design.md L64 |
| AC-3 | Accuracy | Info | Terminology drift between the container env var `TRANSCRIPT_DIR` and the host `.env` mount override `TRANSCRIPTS_DIR`. The one-letter difference is intentional but easy to conflate during implementation and operations; a README table would help. | proposal.md L9 vs L14; design.md L53 vs L55; tasks.md §2.1 vs §4.2 |
| AC-4 | Accuracy | Info | Terminology drift: "failure reason" (spec) vs "reason" (design, tasks) for the same log field. First use in the spec is the canonical term. | structured-logging spec.md L6/L19 vs design.md L45 vs tasks.md §2.1 |
| AC-5 | Accuracy | Info | Design Context claims the app "today writes nothing to disk", but the fallback fetcher writes subtitle files to a `tempfile.TemporaryDirectory`. The claim is true only for *persistent* state. | design.md L5 vs app/fetchers.py L255 |
| AC-6 | Accuracy | Info | Design and task 4.3 refer to the README's "zero state, no database" text as a bullet; it is the intro paragraph, not a list item. Implementers looking for a bullet may not find the target text. | design.md L59; tasks.md §4.3; README.md L5 |
| CM-1 | Completeness | Info | Deployment and verification tasks map to no spec requirement: compose volumes (4.2), README (4.3), and suite/smoke verification (5.1–5.3). Acceptable as deployment detail; noted for awareness. | tasks.md §4.2–5.3 |
| CM-2 | Completeness | Info | `design.md` has no `## Test Strategy` section. All 12 scenarios carry complete `File`/`Command`/`Pass` blocks, so nothing blocks application; only the centralization convention is absent. | design.md (absent section) |
| VL-1 | Validity | Warning | The "Title-based file name" requirement is internally contradictory: it says "removing all punctuation" and then "replacing each remaining run of whitespace or other non-alphanumeric characters with a single underscore". Applied literally in order, `Foo/Bar: The Story` becomes `foobar_the_story.txt`, contradicting the scenario's `foo_bar_the_story.txt`. | spec.md L31 vs L42–44 |
| VL-2 | Validity | Warning | The test block for "Path separator in title cannot escape the directory" does not exercise the scenario's declared outcome. The scenario asserts the file *is written* inside the directory and nothing outside it, but the mapped test is listed in task 1.1 among pure derivation tests (no I/O), so it can only assert the derived name has no separator. | spec.md L42–49; tasks.md §1.1 |
| VL-3 | Validity | Info | "machine-readable failure reason" is required but its format and JSON field name are undefined, so implementers must invent them. The codebase precedent is `reason=exc.code` (`app/chain.py` L94), which would be a reasonable explicit choice. | structured-logging spec.md L6/L19 |
| FS-1 | Feasibility | Info | The compose default host path is machine-specific: `${TRANSCRIPTS_DIR:-/home/john/transcripts}` hardcodes the operator's home directory. It works here by design, but other hosts need an `.env` file or the default path is created root-owned on the host. | proposal.md L14; design.md L55; tasks.md §4.2 |
| FS-2 | Feasibility | Info | The concurrency rationale in decision 5 is imprecise: it says any write overlap "touches different files", but the single-flight semaphore is released inside `FetchChain.run` before the endpoint performs the write, so two requests for the same video can target the same file. The accepted last-write-wins/plain-overwrite behavior makes this harmless, but the justification should not be relied on for correctness. | design.md L50; app/chain.py L73–74 |
| CO-1 | Coherence | Info | Tasks 1.1–3.1 are coarse: each bundles module/writer/endpoint creation with 4–5 test implementations in one checkbox. Each is verifiable via its referenced test IDs, so this is a granularity observation, not a blocker. | tasks.md §1.1, §2.1, §3.1 |

---

### Coverage Metrics

| Metric | Value |
|--------|-------|
| Total requirements | 7 (6 in transcript-persistence delta + 1 in structured-logging delta) |
| Total tasks | 9 |
| Requirements with ≥1 task | 7 (100%) |
| Tasks with mapped requirement | 4 (44%) — tasks 1.1, 2.1, 3.1, 4.1 (Dockerfile `TRANSCRIPT_DIR` default) |
| Duplications found | 0 |
| Ambiguities found | 2 (VL-1 wording contradiction, VL-3 undefined reason format) |
| Requirements with executable test requirements | 6 (86%) — 11 of 12 scenarios carry complete, genuine blocks; the path-separator block (VL-2) does not exercise its scenario's write outcome |

---

### Verified-consistent highlights (no findings)

- Capability wiring is correct: both listed capabilities have delta specs, the modified `structured-logging` base spec exists, and `openspec validate --strict` passes.
- All referenced code exists as described: `transcript_endpoint`, `chain_mod.default_chain.run`, `_listen_port()` (call-time env read pattern), `get_logger()`, `asyncio.to_thread` (app/chain.py L84), the five error codes in the failed-fetch scenario, `appuser` in the Dockerfile, log rotation `10m × 3`, and the README "zero state, no database" text.
- Test ID scheme is collision-free (`T-TRANSCRIPT-PERSISTENCE-001…010`, `T-STRUCTURED-LOGGING-010/011` vs base `001…009`), task-to-test names match the spec blocks exactly, and no task cross-reference is broken.
- Path safety for user-influenced titles is addressed by construction (all non-alphanumeric runs, including `/` and `.`, collapse to `_`) with a dedicated scenario.
- The trailing-newline convention is consistent: `clean_text` never emits a trailing newline, so writing `text + "\n"` yields exactly one.

### Verdict
Can proceed with caution. Consider resolving warnings AC-1 (widen the catch or justify it), AC-2 (scenario for the distinct-video overwrite clause), VL-1 (fix the contradictory derivation wording), and VL-2 (align the path-separator scenario with its test) before or during `/opsx-apply`.
