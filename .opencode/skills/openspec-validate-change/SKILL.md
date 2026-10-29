---
name: openspec-validate-change
description: Validate a completed change's implementation against its proposal, specs, design, and audit findings. Use after opsx-apply to verify the implementation is correct and complete before archiving.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: jebucha
  version: "1.1"
---

Validate a change's implementation against its proposal, specs, design, and audit findings.

After `/opsx-apply` implements a change, this skill independently verifies that the implementation is correct, complete, and ready for archive. It examines the actual code changes against the spec requirements, checks test coverage, verifies task completion, and detects regressions.

---

**Output Constraints:**
- Cap findings at **50 total**. If more are detected, include the top 50 by severity (Errors first, then Warnings, then Info) and add an overflow summary line: "N additional findings omitted (X warnings, Y info)."
- Assign each finding a **stable ID** prefixed with `VD-` (Validation). Number sequentially: `VD-1`, `VD-2`, etc. Same input should produce same IDs on re-run.

**Steps**

1. **Select the change**

   If a name is provided, use it. Otherwise:
   - Infer from conversation context if the user mentioned a change
   - Auto-select if only one active change exists
   - If ambiguous, run `openspec list --json` to get available changes and use the **AskUserQuestion tool** to let the user select

   Always announce: "Validating change: <name>" and how to override (e.g., `/opsx-validate <other>`).

2. **Check change status**
   ```bash
   openspec status --change "<name>" --json
   ```
   Parse the JSON to understand:
   - `schemaName`: The workflow being used (e.g., "spec-driven")
   - `artifacts`: Which artifacts exist and their status
   - `isComplete`: Whether all artifacts are created

   **If no artifacts exist:** Report that the change has no artifacts to validate. Suggest using `/opsx-propose` first.

3. **Read all change artifact files**

   Read every artifact file that exists for the change:
   - `openspec/changes/<name>/proposal.md`
   - `openspec/changes/<name>/design.md`
   - `openspec/changes/<name>/specs/**/*.md` (use glob to find all spec files)
   - `openspec/changes/<name>/tasks.md`

   Skip files that don't exist — note missing artifacts as Info findings.

4. **Determine the scope of code to validate**

   Identify which source files were modified or created by this change:
   - Scan the design.md and tasks.md for referenced file paths
   - Run `git diff --name-only` (or `git status --porcelain`) to find changed files
   - Cross-reference: files mentioned in tasks AND files actually changed
   - If no git changes exist (change not yet implemented), flag as Error and skip to step 9

   Read the changed source files to understand what was implemented.

5. **Run Spec Compliance Checks**

   For each spec requirement (from spec files):
   - Determine what behavior the requirement specifies
   - Search the changed code for evidence of that behavior
   - Classify each requirement as:
     - **Satisfied**: Code clearly implements the required behavior
     - **Partially satisfied**: Code addresses the requirement but with gaps (Warning)
     - **Not satisfied**: No evidence the requirement is implemented (Error)

   For each finding, include:
   - The requirement text
   - Evidence: file path, function/class name, or description of what's missing

   **Evidence-based:** Every finding must cite specific code (or absence thereof). Don't speculate.

6. **Run Test Coverage Checks**

   **6a. Structural Test Coverage**

   For each spec requirement, apply the structural check to its scenarios that carry no Test Requirement block (scenarios verified by 6b are excluded). Classify coverage per requirement from its unblocked scenarios:
   - Search for test files that test the new functionality
   - Look for test files in common locations: `tests/`, `__tests__/`, `*.test.*`, `*.spec.*`
   - Check that tests cover:
     - Happy path (basic functionality)
     - Edge cases described in spec scenarios
   - Classify coverage as:
     - **Covered**: Tests exist and cover happy path + edge cases
     - **Partially covered**: Tests exist but miss edge cases (Warning)
     - **Not covered**: No tests found for the requirement (Error)

   For each finding, include:
   - The requirement text
   - Evidence: test file path, test names, or description of what's missing

   **6b. Run Executable Test Requirements**

   A spec scenario that carries a **Test Requirement** block is verified by execution, not structural inspection — the structural check (6a) does not apply to it. A block is a bullet list directly under the `#### Scenario:` with four fields: `ID` (format `T-<CAPABILITY-UPPERCASE>-<NNN>`), `File` (test file path and test ID joined by `::`, e.g. `tests/foo.test.ts::test_name`), `Command` (exact runnable invocation from the project root), and `Pass` (machine-checkable criterion).

   - **Parse**: collect every Test Requirement block from the change's spec files, in spec order, and read the `## Test Strategy` section from design.md (runner, full-suite command, prerequisites)
   - **Zero-block change**: if the change's spec files contain no blocks, skip execution, validate structurally (6a) as before, and add one Info finding: "No executable test requirements declared"
   - **Check typed prerequisites**: each Test Strategy prerequisite is a typed, machine-checkable entry — `env: <VAR>` (the variable is set), `file: <path>` (the file exists), or `cmd: <probe>` (the probe command exits 0). Any unmet prerequisite → **Error** "prerequisite unmet", reported distinctly from a test failure; do not run the block. Untyped prose prerequisites → an Info note ("not machine-checkable") and proceed to execution
   - **Verify existence**: the block's `File` must exist and the named test ID must exist in it. Missing → **Error** "missing file or test ID", reported distinctly from a test failure
   - **Execute**: run the block's `Command` verbatim from the project root — declared-only; never synthesized, broadened (e.g., to a full-suite run), or edited. Hard 120-second timeout per command: terminate and record an **Error** with partial output. At most 25 commands per execution, prioritized by spec order; summarize the remainder in the report
   - **Classify** by the declared `Pass` criterion, evaluated against the full captured output. The default criterion ("exit code 0, no skipped tests") is evaluated with per-runner-family skip markers: pytest (`skipped`, `deselected`), jest (`skipped`), go (`--- SKIP`), cargo (`ignored`). Unrecognized runner → exit code only, noted in evidence:
     - Exit 0 and no skipped/xfail tests → **Satisfied**, no finding
     - Non-zero exit → **Error**, citing the requirement ID and the exit code
     - Any skipped or xfail test → **Error** — a skipped test asserts nothing, so the requirement is not satisfied
   - **Findings**: use Category "Executable: tests" with the normal VD- sequence. Evidence: exit code + last 20 lines of output (plus the runner or timeout note where applicable)

   A scenario without a block falls back to the structural check (6a) unchanged.

7. **Run Task Completion Checks**

   Parse tasks.md for task status:
   - Count `- [x]` (complete) vs `- [ ]` (incomplete)
   - **If incomplete tasks exist:** Raise Error listing each incomplete task
   - **For each completed task:** Verify the expected code changes exist in the codebase
     - Cross-reference the task description with actual file changes
     - If a task is marked complete but no corresponding code changes exist, raise Error

   For each finding, include:
   - The task description
   - Evidence: task number, checkbox state, and whether code changes are present

8. **Run Code Quality Checks (best-effort)**

   For changed source files, check for obvious issues:
   - Unused imports
   - Dead code (commented-out blocks, unreachable code)
   - Obvious type mismatches or syntax errors
   - Inconsistent patterns with surrounding code

   These are Info-level findings — not blocking, but worth noting.

   **Scope:** Only check files touched by this change. Don't audit the entire codebase.

9. **Run Regression Safety Checks (best-effort)**

   For changed files, check:
   - Do modifications to existing functions preserve their public interface?
   - Are existing callers still compatible with the changes?
   - Were existing tests modified or removed?

   These are Warning-level findings — flag potential regressions without being alarmist.

   **Scope:** Only check files touched by this change and their immediate callers.

10. **Detect regressions from prior validations**

    Before producing the final report, check if any prior validations in `openspec/changes/<name>/validations/` have resolved findings.

    **10a. Parse resolved findings from prior validations**
    - Look in `openspec/changes/<name>/validations/` for validation files with a `## Resolved` header
    - From each, extract finding IDs listed under `### Resolved` (e.g., `- VD-3: ...`)
    - Build a set of resolved finding IDs mapped to their source validation filename

    **10b. Compare against new findings**
    - For each finding in the new validation, check if its ID (e.g., `VD-3`) appears in the resolved set
    - A match indicates a regression — the issue was fixed but reappeared

    **10c. Generate Regressions section**
    - If regressions are found, insert a `### Regressions` section between `### Findings` and `### Coverage Metrics`
    - Format as a table:

    ```
    ### Regressions

    | ID | Description | Source Validation |
    |----|-------------|-------------------|
    | VD-3 | Missing tests for X | `2026-07-15T10-30-model.md` — was resolved, reappeared |
    ```

    - Classify each regression as a **Warning** severity
    - Include regressions in the overall warning count
    - If no regressions, skip the section

    **10d. No prior validations**
    - If no validation files exist, skip regression detection

11. **Produce structured report**

    Display the validation results:

    ```
    ## Validation Report: <change-name>

    **Schema:** <schema-name>
    **Model:** <model that performed the validation>
    **Artifacts checked:** <list of artifacts that were read>

    ### Summary
    - Errors: <count>
    - Warnings: <count>
    - Info: <count>

    ---

    ### Findings

    | ID | Category | Severity | Description | Evidence |
    |----|----------|----------|-------------|----------|
    | VD-1 | Spec compliance | Error | Requirement "User can export" not implemented | No code at `src/export.ts` matching spec requirement |
    | VD-2 | Test coverage | Warning | Edge case not tested | `tests/export.test.ts` — missing invalid input scenario |
    | ... | ... | ... | ... | ... |

    ### Coverage Metrics

    | Metric | Value |
    |--------|-------|
    | Total requirements | <count> |
    | Requirements satisfied | <count> (<percent>%) |
    | Requirements with tests | <count> (<percent>%) |
    | Executable tests passed | <count>/<total> (<percent>%) |
    | Tasks complete | <count>/<total> (<percent>%) |
    | Changed files examined | <count> |

    ---

    ### Verdict
    ```

    **Verdict rules:**
    - 0 errors → **Pass**: "Implementation validated. Ready for archive."
    - 0 errors, ≥1 warning → **Conditional**: "Proceed with caution. Review warnings before archiving."
    - ≥1 error → **Fail**: "Cannot proceed. Resolve errors before archiving."

12. **Persist the validation report**

    Save the structured output to a file:

    ```
    openspec/changes/<name>/validations/<timestamp>-<model>.md
    ```

    - Create the `validations/` directory if it doesn't exist
    - Timestamp format: `YYYY-MM-DDTHH-MM` (e.g., `2026-07-15T10-30`)
    - Model: short identifier (e.g., `claude-opus`, `gpt-4o`, `gemini-pro`)
    - Example: `openspec/changes/add-user-auth/validations/2026-07-15T10-30-claude-opus.md`

    Announce: "Validation saved to `<path>`"

13. **Offer follow-up actions**

    After displaying the report, frame this as a checkpoint — the user decides — and offer, in order:
    - "Fix the findings (continuing the implementation), then re-run `/opsx-validate` in a fresh session with a model that did not write the code."
    - "Run `/opsx-validate` again in a fresh session with a different model for a second opinion."
    - "Run `/opsx-archive` to archive (if Pass or Conditional verdict)."

**Output Examples**

**Pass verdict:**
```
## Validation Report: add-user-auth

**Schema:** spec-driven
**Model:** claude-sonnet
**Artifacts checked:** proposal.md, design.md, specs/user-auth/spec.md, tasks.md

### Summary
- Errors: 0
- Warnings: 1
- Info: 3

### Findings

| ID | Category | Severity | Description | Evidence |
|----|----------|----------|-------------|----------|
| VD-1 | Test coverage | Warning | Edge case not tested | `tests/auth.test.ts` — missing token expiry scenario |
| VD-2 | Code quality | Info | New dependency | `bcrypt` not in package.json |
| VD-3 | Task completion | Info | Task has no direct code change | Task 2.3 — documentation update |
| VD-4 | Executable: tests | Info | No executable test requirements declared | No Test Requirement blocks in spec files |

### Coverage Metrics

| Metric | Value |
|--------|-------|
| Total requirements | 5 |
| Requirements satisfied | 5 (100%) |
| Requirements with tests | 5 (100%) |
| Executable tests passed | 0/0 |
| Tasks complete | 7/7 (100%) |
| Changed files examined | 4 |

### Verdict
**Conditional** — Proceed with caution. Review warnings before archiving.
```

**Fail verdict:**
```
## Validation Report: add-data-export

**Schema:** spec-driven
**Model:** gpt-4o
**Artifacts checked:** proposal.md, design.md, specs/csv-export/spec.md, tasks.md

### Summary
- Errors: 4
- Warnings: 2
- Info: 1

### Findings

| ID | Category | Severity | Description | Evidence |
|----|----------|----------|-------------|----------|
| VD-1 | Spec compliance | Error | "Export supports pagination" not implemented | No pagination logic in `src/export.ts` |
| VD-2 | Test coverage | Error | No tests for CSV export | No test files found for `src/export.ts` |
| VD-3 | Task completion | Error | Task 3.2 incomplete | `tasks.md` line 15 — `- [ ]` still unchecked |
| VD-4 | Test coverage | Warning | Edge case not tested | `tests/utils.test.ts` — missing empty dataset scenario |
| VD-5 | Regression safety | Warning | Existing `formatDate` signature changed | `src/utils.ts:45` — added required `locale` param |
| VD-6 | Executable: tests | Error | Test command failed | `T-CSV-EXPORT-001` — exit 1; last 20 lines end with "1 failed, 4 passed" |

### Coverage Metrics

| Metric | Value |
|--------|-------|
| Total requirements | 8 |
| Requirements satisfied | 6 (75%) |
| Requirements with tests | 4 (50%) |
| Executable tests passed | 3/4 (75%) |
| Tasks complete | 10/12 (83%) |
| Changed files examined | 5 |

### Verdict
**Fail** — Cannot proceed. Resolve errors before archiving.
```

**Guardrails**

- **Read-only** — Never modify code during validation. Flag issues; don't fix them.
- **Evidence-based** — Every finding must include specific evidence (file path, line reference, quoted text)
- **Stable IDs** — Finding IDs must be deterministic. Same input should produce same IDs on re-run.
- **Capped output** — Maximum 50 findings. Prioritize by severity. Summarize overflow.
- **Scope to change** — Only examine files touched by the change and their immediate dependencies. Don't audit the entire codebase.
- **Don't be prescriptive** — Focus on structural issues and spec gaps. Use Info level for subjective observations.
- **Handle missing artifacts gracefully** — If an artifact doesn't exist, note it but continue validating what's available.
- **Code quality is best-effort** — Basic checks only. Don't replace linters or type checkers.
- **Regression safety is best-effort** — Check public interfaces and callers. Don't perform exhaustive impact analysis.
- **Declared-only execution** — Step 6b runs the `Command` verbatim from the Test Requirement block. Never synthesize, broaden (e.g., to a full-suite run), or edit a declared command.
- **Read-only with respect to the codebase** — Running a block must never require installing a dependency or editing config or environment state; report the unmet prerequisite instead of changing anything.
- **Bounded execution** — Hard 120-second timeout per command (terminate; record an Error with partial output). At most 25 commands per execution, prioritized by spec order; summarize the remainder.
- **Exit-code evidence** — Executable test findings cite the exit code and the last 20 lines of output; skip detection uses the declared Pass criterion with per-runner-family skip markers.
- **Stable IDs for executable findings** — Executable test findings use Category "Executable: tests" with the normal VD- sequence so regression detection continues to work.
- **Backward compatible** — Validation files without lifecycle headers function normally.
- **Header parsing is position-sensitive** — Only parse `## Resolved` headers at the very start of the file.

**Fluid Workflow Integration**

This skill supports the "actions on a change" model:

- **Can be invoked anytime** after implementation has begun
- **Pairs with `/opsx-apply`**: implement changes, then validate
- **Iterative**: Can be run multiple times as implementation progresses
- **Gates `/opsx-archive`**: Advises whether change is ready for archive
- **Non-destructive**: Read-only analysis — the validator itself never modifies code or artifacts. Step 6b runs the author's declared commands verbatim (declared-only execution: no installs, no config or environment edits by the validator); any side effects of a declared command are the author's, not the validator's
