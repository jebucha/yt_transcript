# opsx-audit

Audit an existing change proposal for quality issues before implementation.

## Overview

`/opsx-audit` is the quality-gate step in the OpenSpec workflow. After `/opsx-propose` generates a change's artifacts (proposal, design, specs, tasks), the audit evaluates them for structural issues — inconsistencies between artifacts, missing requirements, non-testable language, design that doesn't match the codebase, and scope drift — before a single line of code is written. It produces a structured report with categorized findings, coverage metrics, and a verdict on whether the change is ready for implementation.

## Workflow Position

```
/opsx-propose  →  /opsx-audit  →  /opsx-apply-audit  →  /opsx-apply
   (create)        (review)         (fix artifacts)      (implement code)
```

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `/opsx-propose` | Generate change artifacts (proposal, design, specs, tasks) |
| **2** | **`/opsx-audit`** | **Review artifacts for quality issues (read-only)** |
| 3 | `/opsx-apply-audit` | Resolve errors and warnings found during audit |
| 4 | `/opsx-apply` | Implement the actual source code changes |

## Usage

```
/opsx-audit [change-name]
```

The change name is optional:
- If provided, audits that change directly.
- If omitted, the command infers the change from conversation context.
- If only one active change exists, it auto-selects it.
- If multiple changes exist and context is ambiguous, it prompts you to select.

Examples:
```
/opsx-audit                    # infer or prompt
/opsx-audit add-user-auth      # audit a specific change
```

## Prerequisites

- A change must exist with artifacts — run `/opsx-propose` first.
- The change must have at least a `proposal.md` or `tasks.md`. The audit works on whatever artifacts are present and flags absent ones.
- After reviewing findings, use `/opsx-apply-audit` to fix them before running `/opsx-apply`.

## What It Does

The audit evaluates artifacts across five categories. Each finding is assigned a stable ID prefixed by category.

### Accuracy (AC-)

Checks whether artifacts are internally consistent and consistent with the actual codebase.

- **Capability name consistency** — every capability listed in the proposal has a corresponding spec file
- **Referenced file existence** — source file paths mentioned in design and tasks actually exist. `File` paths in Test Requirement blocks and file references in a design.md `## Test Strategy` section are forward references created by `/opsx-apply` and are exempt
- **Spec contradictions** — requirements across multiple spec files don't define conflicting behavior
- **Duplication detection** — near-duplicate requirements and tasks that describe the same work
- **Terminology drift** — the same concept isn't named differently across artifacts (e.g., "user" in proposal, "account" in design, "member" in specs)

### Completeness (CM-)

Checks whether all required sections are present and content is fully covered.

- **Missing required artifacts** — flags artifacts that are entirely absent
- **Missing requirement scenarios** — every `### Requirement:` block must have at least one `#### Scenario:`
- **Task-to-spec coverage** — maps requirements to tasks; flags requirements with no associated task
- **Empty or placeholder sections** — detects `TBD`, `TODO`, `<!-- -->`, or headers with no content

### Validity (VL-)

Checks whether artifacts follow structural conventions and contain well-formed content.

- **Non-testable requirements** — flags vague qualifiers like "fast", "scalable", "secure", "intuitive" with no measurable criteria
- **Task dependency chains** — verifies cross-task references (e.g., "depends on 2.1") point to real tasks
- **Naming convention compliance** — capability names and change names should use kebab-case
- **Executable test requirement presence (step 6d)** — behavior-changing scenarios should carry a complete, genuine Test Requirement block (`ID` / `File` / `Command` / `Pass` under the scenario). Missing, incomplete, or malformed-ID blocks are Warnings; a fake block is a Warning ("not a runtime behavior assertion") — fake patterns: static-only command (linter, formatter, type checker, vet, compile check), existential pass criterion (asserts only that a file or test exists), or behavior-unrelated command (evidence: the scenario's outcome and the block's Command quoted side by side). A content assertion (grep/diff) that verifies the scenario's declared outcome IS a Test Requirement. A missing `## Test Strategy` section in design.md is a single Info finding

### Feasibility (FS-)

Checks whether the design is achievable given the actual codebase state.

- **Design-to-codebase compatibility** — verifies that functions, classes, and interfaces the design proposes to modify actually exist
- **Dependency and import feasibility** — checks whether referenced libraries are declared in the project's dependency manifest
- **Pattern consistency** — compares the design's proposed approach against established patterns in the codebase

### Coherence (CO-)

Checks whether proposal, design, and tasks align in scope and intent.

- **Proposal-to-design scope alignment** — flags design elements not mentioned in the proposal (scope creep) and proposal goals with no design coverage
- **Spec-to-design consistency** — flags requirements that have no plausible design support
- **Task ordering and buildability** — flags tasks that depend on output from a later task, or tasks too coarse to be actionable
- **Security surface awareness** — when the change touches auth, user input, data handling, or external I/O, checks that input validation, error handling, TLS, and secrets management are addressed

## Severity Levels

Each finding is assigned one of three severity levels:

| Severity | Meaning | Workflow implication |
|----------|---------|----------------------|
| **Error** | Structural problem that makes implementation unreliable or impossible | Blocks `/opsx-apply`. Must be resolved first. |
| **Warning** | Quality issue that should be addressed | Can proceed with caution. `/opsx-apply-audit` is recommended. |
| **Info** | Observation or minor deviation | Ready for implementation. Fix at your discretion. |

**Verdict rules:**
- One or more Errors → "Cannot proceed to implementation. Resolve errors first."
- Warnings only → "Can proceed with caution. Consider addressing warnings."
- Info only or clean → "Ready for implementation."

## Output Format

The audit produces a structured report displayed in chat and saved to disk.

### Findings Table

Each finding includes a stable ID, category, severity, description, and evidence:

```
| ID   | Category     | Severity | Description                            | Evidence                                              |
|------|--------------|----------|----------------------------------------|-------------------------------------------------------|
| AC-1 | Accuracy     | Error    | Missing spec for listed capability     | `pdf-export` in proposal but no specs/pdf-export/...  |
| CM-1 | Completeness | Warning  | Requirement has no scenarios           | "User can filter exports" in specs/csv-export/spec.md |
| VL-1 | Validity     | Warning  | Vague qualifier in requirement         | "Export should be fast" — no measurable criteria      |
| CO-1 | Coherence    | Info     | Task has no direct spec requirement    | Task 3.2 — may be an implementation detail            |
```

Finding IDs are stable — the same input produces the same IDs on re-run, so `/opsx-apply-audit` can reference them by ID.

Findings are capped at **50 total**, prioritized by severity (Errors → Warnings → Info). If more are detected, an overflow summary line is appended: `"N additional findings omitted (X warnings, Y info)."`

### Coverage Metrics

```
| Metric                          | Value        |
|---------------------------------|--------------|
| Total requirements              | 8            |
| Total tasks                     | 12           |
| Requirements with ≥1 task       | 6 (75%)      |
| Tasks with mapped requirement   | 10 (83%)     |
| Duplications found              | 1            |
| Ambiguities found               | 1            |
| Requirements with executable test requirements | 3 (50%) |
```

## Persisted Audit File

After displaying the report, the audit saves it to:

```
openspec/changes/<name>/audits/<timestamp>-<model>.md
```

- Timestamp format: `YYYY-MM-DDTHH-MM` (e.g., `2026-07-09T15-42`)
- Model: short identifier of the model that ran the audit (e.g., `claude-sonnet`, `gpt-4o`)
- Example: `openspec/changes/add-user-auth/audits/2026-07-09T15-42-claude-sonnet.md`

The persisted file enables:
- **Multi-model comparison** — run `/opsx-audit` with different models and compare the saved reports
- **Historical tracking** — compare findings before and after applying fixes
- **Session-decoupled workflow** — `/opsx-apply-audit` loads the saved file, so it doesn't need to run in the same session as the audit

## Guardrails

- **Read-only** — The audit never modifies artifacts. It only reports. Use `/opsx-apply-audit` to fix findings.
- **Evidence required** — Every finding must cite specific evidence: a file path, line reference, or quoted text. No finding without proof.
- **50-finding cap** — Capped at 50 findings, prioritized Errors → Warnings → Info. Overflow findings are summarized, not silently dropped.
- **Feasibility checks are best-effort** — Checks the specific files and symbols referenced in artifacts; does not audit the entire codebase.
- **Security checks are contextual** — Security surface checks (section 8d) only apply when the change touches auth, user input, data storage, external communication, or secrets. Purely cosmetic or refactoring changes are not flagged.
- **Duplication requires semantic overlap** — Requirements are only flagged as duplicates if they describe functionally overlapping behavior, not just shared words.
- **Terminology drift is cross-file only** — Term variations within a single artifact are not flagged; only when different artifacts use different terms for the same concept.
- **Missing artifacts are noted, not fatal** — The audit continues on whatever artifacts exist, flagging absent ones as Errors.

## Iterative Use

The audit and apply-audit commands are designed to be run in cycles:

```
/opsx-audit                # finds 3 errors, 2 warnings
/opsx-apply-audit          # fixes errors; pauses on 1 ambiguous warning
                           # user provides guidance
/opsx-apply-audit          # fixes remaining warning
/opsx-audit                # clean: 0 errors, 0 warnings, 2 info
/opsx-apply                # begin implementation
```

You can run `/opsx-audit` again after `/opsx-apply-audit` to confirm all findings were resolved. Multiple audits accumulate in the `audits/` directory with distinct timestamps.


## Example Output

### Clean Audit

```
## Audit Report: add-user-auth

**Schema:** spec-driven
**Model:** claude-sonnet
**Artifacts checked:** proposal.md, design.md, specs/user-auth/spec.md, tasks.md

### Summary
- Errors: 0
- Warnings: 0
- Info: 2

---

### Findings

| ID   | Category   | Severity | Description                         | Evidence                                 |
|------|------------|----------|-------------------------------------|------------------------------------------|
| CO-1 | Coherence  | Info     | Task has no direct spec requirement | Task 3.2 — may be implementation detail  |
| FS-1 | Feasibility| Info     | New dependency introduced           | `argon2` not in current package.json     |

### Coverage Metrics

| Metric                          | Value       |
|---------------------------------|-------------|
| Total requirements              | 5           |
| Total tasks                     | 7           |
| Requirements with ≥1 task       | 5 (100%)    |
| Tasks with mapped requirement   | 6 (86%)     |
| Duplications found              | 0           |
| Ambiguities found               | 0           |
| Requirements with executable test requirements | 5 (100%) |

---

### Verdict
Ready for implementation.
```

### Audit with Errors

```
## Audit Report: add-data-export

**Schema:** spec-driven
**Model:** claude-sonnet
**Artifacts checked:** proposal.md, design.md, specs/csv-export/spec.md, tasks.md

### Summary
- Errors: 5
- Warnings: 4
- Info: 2

---

### Findings

| ID   | Category     | Severity | Description                                | Evidence                                                       |
|------|--------------|----------|--------------------------------------------|----------------------------------------------------------------|
| AC-1 | Accuracy     | Error    | Missing spec for listed capability         | `pdf-export` in proposal but no `specs/pdf-export/spec.md`     |
| AC-2 | Accuracy     | Warning  | Near-duplicate requirements                | "Export data as CSV" (spec L12) ≈ "Generate CSV file" (spec L34) |
| AC-3 | Accuracy     | Info     | Terminology drift                          | "export job" (design) vs "export task" (proposal)              |
| CM-1 | Completeness | Error    | Requirement has no scenarios               | "User can filter exports" in `specs/csv-export/spec.md`        |
| CM-2 | Completeness | Warning  | Requirement has zero task coverage         | "Export supports pagination" — no associated task              |
| CM-3 | Completeness | Warning  | Empty section                              | "Goals / Non-Goals" in design.md has no content                |
| VL-1 | Validity     | Warning  | Vague qualifier in requirement             | "Export should be fast" — no measurable criteria               |
| FS-1 | Feasibility  | Error    | Design references non-existent symbol      | `ExportService.generatePdf()` not found in ExportService.ts    |
| FS-2 | Feasibility  | Info     | New dependency introduced                  | `puppeteer` not in package.json                                |
| CO-1 | Coherence    | Error    | Task ordering violation                    | Task 2 uses `src/templates/base.ts` created in Task 5          |
| CO-2 | Coherence    | Error    | Design exceeds proposal scope              | "notification system" in design but not in proposal            |

### Coverage Metrics

| Metric                          | Value       |
|---------------------------------|-------------|
| Total requirements              | 8           |
| Total tasks                     | 12          |
| Requirements with ≥1 task       | 6 (75%)     |
| Tasks with mapped requirement   | 10 (83%)    |
| Duplications found              | 1           |
| Ambiguities found               | 1           |
| Requirements with executable test requirements | 3 (50%) |

---

### Verdict
Cannot proceed to implementation. Resolve errors first.
```

Audit saved to `openspec/changes/add-data-export/audits/2026-07-09T15-42-claude-sonnet.md`
