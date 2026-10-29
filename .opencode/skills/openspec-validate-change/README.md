# opsx-validate

Validate a completed change's implementation against its proposal, specs, and design.

## Overview

`/opsx-validate` is the quality-gate step after implementation in the OpenSpec workflow. After `/opsx-apply` implements a change's tasks, the validation independently examines the actual code changes against the spec requirements, checks test coverage, verifies task completion, and detects regressions — producing a structured report with categorized findings, coverage metrics, and a verdict on whether the change is ready for archive.

## Workflow Position

```
/opsx-propose  →  /opsx-audit  →  /opsx-apply-audit  →  /opsx-apply  →  /opsx-validate  →  /opsx-archive
   (create)        (review)         (fix artifacts)       (implement)       (verify)           (archive)
```

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `/opsx-propose` | Generate change artifacts (proposal, design, specs, tasks) |
| 2 | `/opsx-audit` | Review artifacts for quality issues (read-only) |
| 3 | `/opsx-apply-audit` | Resolve errors and warnings found during audit |
| 4 | `/opsx-apply` | Implement the actual source code changes |
| **5** | **`/opsx-validate`** | **Verify implementation matches specs, has tests, no regressions** |
| 6 | `/opsx-archive` | Archive the completed change |

## Usage

```
/opsx-validate [change-name]
```

The change name is optional:
- If provided, validates that change directly.
- If omitted, the command infers the change from conversation context.
- If only one active change exists, it auto-selects it.
- If multiple changes exist and context is ambiguous, it prompts you to select.

Examples:
```
/opsx-validate                    # infer or prompt
/opsx-validate add-user-auth      # validate a specific change
```

## Prerequisites

- A change must exist with artifacts and implementation — run `/opsx-propose` and `/opsx-apply` first.
- The change should have at least a `proposal.md` and `tasks.md`. The validation works on whatever artifacts are present and flags absent ones.
- For best results, run with a different model than the one that implemented the change.

## What It Does

The validation examines the implementation across five dimensions. Each finding is assigned a stable ID prefixed with `VD-`.

### Spec Compliance

Checks whether each spec requirement is satisfied by the implemented code.

- **Requirement satisfied** — code clearly implements the required behavior
- **Partially satisfied** — code addresses the requirement but with gaps (Warning)
- **Not satisfied** — no evidence the requirement is implemented (Error)

### Test Coverage

Two checks: scenarios with a Test Requirement block are verified by execution (step 6b); scenarios without one keep the structural check (step 6a), unchanged.

**Structural (6a)** — checks whether tests exist for new requirements and cover edge cases.

- **Covered** — tests exist and cover happy path + edge cases
- **Partially covered** — tests exist but miss edge cases (Warning)
- **Not covered** — no tests found for the requirement (Error)

**Executable (6b)** — runs the declared Test Requirement blocks (Category "Executable: tests", normal VD- sequence):

- **Satisfied** — command exits 0 with no skipped tests; no finding
- **Failed command** — non-zero exit (Error; evidence: exit code + last 20 lines of output)
- **Skipped test** — any skipped/xfail test (Error — a skipped test asserts nothing)
- **Missing file or test ID** — reported distinctly from a test failure (Error)
- **Prerequisite unmet** — reported distinctly from a test failure (Error)
- **Zero-block change** — structural validation as before, plus one Info finding

**The convention** — a Test Requirement block is a bullet list directly under a spec scenario with four fields: `ID` (`T-<CAPABILITY-UPPERCASE>-<NNN>`), `File` (test file path and test ID joined by `::`), `Command` (exact runnable invocation from the project root), and `Pass` (machine-checkable criterion). The change's design.md `## Test Strategy` section declares once per change the runner, the full-suite command, and typed prerequisites (`env: <VAR>`, `file: <path>`, `cmd: <probe>`); blocks reference it instead of repeating environment details.

### Task Completion

Checks whether all tasks from tasks.md are completed and reflected in the codebase.

- **All complete** — all tasks marked `- [x]` with corresponding code changes
- **Incomplete tasks** — tasks still marked `- [ ]` (Error)
- **False completion** — task marked `- [x]` but no code changes exist (Error)

### Code Quality (best-effort)

Basic checks for obvious issues in changed files.

- Unused imports, dead code, obvious type mismatches
- Inconsistent patterns with surrounding code
- Info-level findings — not blocking

### Regression Safety (best-effort)

Checks whether changes introduce potential regressions.

- Public interface changes that may break callers
- Existing tests modified or removed
- Warning-level findings — flag potential issues

## Severity Levels

Each finding is assigned one of three severity levels:

| Severity | Meaning | Workflow implication |
|----------|---------|----------------------|
| **Error** | Implementation gap that makes the change incomplete | Not ready for archive. Must be resolved. |
| **Warning** | Quality issue that should be addressed | Proceed with caution. Review before archiving. |
| **Info** | Observation or minor deviation | Ready for archive. Fix at your discretion. |

**Verdict rules:**
- 0 errors, 0 warnings → **Pass**: "Implementation validated. Ready for archive."
- 0 errors, ≥1 warning → **Conditional**: "Proceed with caution. Review warnings before archiving."
- ≥1 error → **Fail**: "Cannot proceed. Resolve errors before archiving."

## Output Format

The validation produces a structured report displayed in chat and saved to disk.

### Findings Table

Each finding includes a stable ID, category, severity, description, and evidence:

```
| ID   | Category        | Severity | Description                          | Evidence                                         |
|------|-----------------|----------|--------------------------------------|--------------------------------------------------|
| VD-1 | Spec compliance | Error    | Requirement not implemented          | No pagination logic in `src/export.ts`           |
| VD-2 | Test coverage   | Warning  | Edge case not tested                 | `tests/export.test.ts` — missing empty scenario  |
| VD-3 | Task completion | Info     | Task is documentation-only           | Task 2.3 — README update, no code change         |
```

Finding IDs are stable — the same input produces the same IDs on re-run, so subsequent validations can detect regressions.

Findings are capped at **50 total**, prioritized by severity (Errors → Warnings → Info).

### Coverage Metrics

```
| Metric                       | Value       |
|------------------------------|-------------|
| Total requirements           | 8           |
| Requirements satisfied       | 7 (87.5%)   |
| Requirements with tests      | 8 (100%)    |
| Executable tests passed      | 4/4 (100%)  |
| Tasks complete               | 12/12 (100%)|
| Changed files examined       | 5           |
```

## Persisted Validation File

After displaying the report, the validation saves it to:

```
openspec/changes/<name>/validations/<timestamp>-<model>.md
```

- Timestamp format: `YYYY-MM-DDTHH-MM` (e.g., `2026-07-15T10-30`)
- Model: short identifier (e.g., `claude-sonnet`, `gpt-4o`)
- Example: `openspec/changes/add-user-auth/validations/2026-07-15T10-30-claude-sonnet.md`

The persisted file enables:
- **Multi-model comparison** — run `/opsx-validate` with different models and compare
- **Historical tracking** — compare findings before and after fixes
- **Regression detection** — subsequent validations compare against resolved findings
- **Lifecycle management** — older validations are auto-superseded by newer ones

## Guardrails

- **Read-only** — The validation never modifies code. It only reports.
- **Evidence required** — Every finding must cite specific evidence: a file path, line reference, or quoted text.
- **50-finding cap** — Capped at 50 findings, prioritized Errors → Warnings → Info.
- **Scope to change** — Only examines files touched by the change and immediate dependencies.
- **Best-effort quality checks** — Code quality and regression checks are advisory, not exhaustive.
- **Declared-only execution** — Step 6b runs the block's `Command` verbatim; never synthesized, broadened (e.g., to a full-suite run), or edited.
- **Read-only with respect to the codebase** — Running a block never installs dependencies or edits config or environment state; unmet prerequisites are reported instead.
- **Bounded execution** — Hard 120-second timeout per command (Error with partial output); at most 25 commands per execution, prioritized by spec order, remainder summarized.
- **Exit-code evidence** — Executable test findings cite the exit code and the last 20 lines of output; skip detection uses the declared Pass criterion with per-runner-family skip markers.
- **Stable IDs for executable findings** — Category "Executable: tests" with the normal VD- sequence, so regression detection continues to work.
- **Backward compatible** — Validation files without lifecycle headers function normally.

## Iterative Use

The validation can be run multiple times as implementation progresses:

```
/opsx-apply                # implement tasks
/opsx-validate             # finds 2 errors, 1 warning
/opsx-apply                # fix remaining issues
/opsx-validate             # clean: 0 errors, 1 warning → Conditional
/opsx-archive              # proceed with archive
```

Multiple validations accumulate in the `validations/` directory with distinct timestamps. Older validations are automatically superseded by newer ones.



## Example Output

### Pass Verdict

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

| ID   | Category        | Severity | Description                              | Evidence                                         |
|------|-----------------|----------|------------------------------------------|--------------------------------------------------|
| VD-1 | Test coverage   | Warning  | Edge case not tested                     | `tests/auth.test.ts` — missing token expiry      |
| VD-2 | Code quality    | Info     | New dependency                           | `bcrypt` not in package.json                     |
| VD-3 | Task completion | Info     | Task is documentation-only               | Task 2.3 — README update                         |
| VD-4 | Executable: tests | Info  | No executable test requirements declared | No Test Requirement blocks in spec files         |

### Coverage Metrics

| Metric                       | Value       |
|------------------------------|-------------|
| Total requirements           | 5           |
| Requirements satisfied       | 5 (100%)    |
| Requirements with tests      | 5 (100%)    |
| Executable tests passed      | 0/0         |
| Tasks complete               | 7/7 (100%)  |
| Changed files examined       | 4           |

### Verdict
**Conditional** — Proceed with caution. Review warnings before archiving.
```

### Fail Verdict

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

| ID   | Category        | Severity | Description                          | Evidence                                         |
|------|-----------------|----------|--------------------------------------|--------------------------------------------------|
| VD-1 | Spec compliance | Error    | "Pagination" not implemented         | No pagination logic in `src/export.ts`           |
| VD-2 | Test coverage   | Error    | No tests for CSV export              | No test files for `src/export.ts`                |
| VD-3 | Task completion | Error    | Task 3.2 incomplete                  | `tasks.md` line 15 — `- [ ]` still unchecked     |
| VD-4 | Test coverage   | Warning  | Edge case not tested                 | `tests/utils.test.ts` — missing empty dataset    |
| VD-5 | Regression      | Warning  | Public interface changed             | `src/utils.ts:45` — added required `locale` param|
| VD-6 | Executable: tests | Error | Test command failed                | `T-CSV-EXPORT-001` — exit 1; last 20 lines end with "1 failed, 4 passed" |

### Coverage Metrics

| Metric                       | Value       |
|------------------------------|-------------|
| Total requirements           | 8           |
| Requirements satisfied       | 6 (75%)     |
| Requirements with tests      | 4 (50%)     |
| Executable tests passed      | 3/4 (75%)   |
| Tasks complete               | 10/12 (83%) |
| Changed files examined       | 5           |

### Verdict
**Fail** — Cannot proceed. Resolve errors before archiving.
```

Validation saved to `openspec/changes/add-data-export/validations/2026-07-15T10-30-gpt-4o.md`
