---
name: openspec-audit-change
description: Audit an existing change proposal for accuracy, completeness, validity, feasibility, and coherence before implementation. Use after opsx-propose to review generated artifacts.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: jebucha
  version: "1.3"
---

Audit an existing change proposal for quality issues before implementation.

I'll evaluate the change artifacts for:
- **Accuracy**: Are artifacts consistent with each other and the actual codebase?
- **Completeness**: Are all required sections present and covered?
- **Validity**: Do artifacts follow structural conventions and contain well-formed content?
- **Feasibility**: Is the design achievable given the actual codebase?
- **Coherence**: Do proposal, design, and tasks align in scope and intent?

---

**Input**: The argument after `/opsx-audit` is the change name (kebab-case). If omitted, check if it can be inferred from conversation context. If vague or ambiguous, prompt for available changes.

**Output Constraints**:
- Cap findings at **50 total**. If more are detected, include the top 50 by severity (Errors first, then Warnings, then Info) and add an overflow summary line: "N additional findings omitted (X warnings, Y info)."
- Assign each finding a **stable ID** prefixed by category: `AC-1` (Accuracy), `CM-1` (Completeness), `VL-1` (Validity), `FS-1` (Feasibility), `CO-1` (Coherence). These IDs are used by `/opsx-apply-audit` to reference specific findings.

**Steps**

1. **Select the change**

   If a name is provided, use it. Otherwise:
   - Infer from conversation context if the user mentioned a change
   - Auto-select if only one active change exists
   - If ambiguous, run `openspec list --json` to get available changes and use the **AskUserQuestion tool** to let the user select

   Always announce: "Auditing change: <name>" and how to override (e.g., `/opsx-audit <other>`).

2. **Check change status**
   ```bash
   openspec status --change "<name>" --json
   ```
   Parse the JSON to understand:
   - `schemaName`: The workflow being used (e.g., "spec-driven")
   - `artifacts`: Which artifacts exist and their status
   - `isComplete`: Whether all artifacts are created

   **If no artifacts exist yet:** Report that the change has no artifacts to audit. Suggest using `/opsx-propose` or `/opsx-apply` first.

3. **Read all available artifact files**

   Read every artifact file that exists for the change:
   - `openspec/changes/<name>/proposal.md`
   - `openspec/changes/<name>/design.md`
   - `openspec/changes/<name>/specs/**/*.md` (use glob to find all spec files)
   - `openspec/changes/<name>/tasks.md`

   Skip files that don't exist — their absence will be flagged during the audit.

4. **Run Accuracy Checks**

   Evaluate whether artifacts are consistent with each other and the actual codebase.

   **4a. Capability name consistency**
   - Parse the proposal's "New Capabilities" and "Modified Capabilities" sections
   - For each listed capability, verify a corresponding spec file exists at `openspec/changes/<name>/specs/<capability>/spec.md`
   - For modified capabilities, verify the base spec exists at `openspec/specs/<capability>/spec.md`

   **4b. Referenced file existence**
   - Scan the design.md and tasks.md for references to source code files (paths like `src/`, `lib/`, `tests/`, etc.)
   - For each referenced file, check if it exists in the workspace
   - Use glob to verify — do not assume file existence from memory
   - **Forward-reference exemption** — `File` paths inside Test Requirement blocks (in spec files) and file references in a design.md `## Test Strategy` section are created by `/opsx-apply` and are exempt from this existence check. Do not flag them as missing, even if the scan extends beyond design.md and tasks.md into spec files

   **4c. Spec contradictions**
   - If multiple spec files exist, check for requirements that define conflicting behavior
   - Look for requirements in different specs that address the same behavior with different rules
   - Compare requirement descriptions and scenarios for logical contradictions

   **4d. Duplication detection**
   - Compare requirements across spec files for near-duplicates — requirements that describe the same behavior in different words
   - Compare scenarios for functional overlap (different wording, same test)
   - Flag the lower-quality or less-specific phrasing for consolidation
   - Look for duplicated tasks in tasks.md that describe the same work

   **4e. Terminology drift**
   - Track key domain terms across all artifacts (proposal, design, specs, tasks)
   - Flag when the same concept is named differently across files (e.g., "user" in proposal, "account" in design, "member" in specs)
   - Flag when the same term is used with different meanings across artifacts
   - Note the first-used term as the canonical reference

   Report each finding with:
   - **Error**: Missing spec for listed capability, contradictory specs
   - **Warning**: Referenced source file does not exist, near-duplicate requirements
   - **Info**: Terminology drift, minor duplications

5. **Run Completeness Checks**

   Evaluate whether required sections are present and content is fully covered.

   **5a. Missing required artifacts**
   - Based on the schema, determine which artifacts are required (e.g., spec-driven requires proposal, design, specs, tasks)
   - If a required artifact is entirely absent, flag as Error
   - Distinguish between "file doesn't exist" (Error) and "file exists but has gaps" (Warning)

   **5b. Missing requirement scenarios**
   - For each `### Requirement:` block in spec files, check that at least one `#### Scenario:` follows before the next `### Requirement:` or `##` header
   - Flag requirements with no scenarios

   **5c. Task-to-spec coverage**
   - Parse all requirements from spec files (build a requirements inventory)
   - Parse all tasks from tasks.md (lines matching `- [ ]` or `- [x]`)
   - Map each task to one or more requirements by keyword match, explicit reference, or semantic alignment
   - Map each requirement to its covering task(s)
   - Flag requirements with zero associated tasks
   - Flag tasks with no mapped requirement (may be implementation detail — use Info)

   **5d. Empty or placeholder sections**
   - Check each artifact for sections that are present but contain only:
     - Empty content (header with no body text before next header)
     - Placeholder text like `<!-- ... -->`, `TBD`, `TODO`, `TKTK`, `???`, `<placeholder>`
   - Flag incomplete sections

   Report each finding with:
   - **Error**: Missing required artifact entirely
   - **Warning**: Missing scenarios, empty sections, requirements with zero task coverage
   - **Info**: Tasks without clear spec coverage

6. **Run Validity Checks**

   Evaluate whether artifacts follow structural conventions and contain well-formed content.

   **6a. Non-testable requirements (ambiguity detection)**
   - Review each requirement for testability
   - A requirement is non-testable if it cannot be verified by observable behavior
   - Flag vague qualifiers lacking measurable criteria: "fast", "scalable", "secure", "intuitive", "robust", "efficient", "clean", "simple", "user-friendly", "performant"
   - Flag requirements with verbs but missing object or measurable outcome (e.g., "the system should handle errors" — which errors? what constitutes handling?)
   - Flag unresolved placeholders: `TODO`, `TBD`, `TKTK`, `???`, `<placeholder>`

   **6b. Task dependency chains**
   - If tasks reference other tasks by number (e.g., "depends on 2.1"), verify the referenced task exists
   - Flag broken cross-references

   **6c. Naming convention compliance**
   - Verify capability names use kebab-case (e.g., `user-auth`, not `userAuth` or `user_auth`)
   - Verify change name uses kebab-case
   - Flag violations with suggested corrections

   **6d. Executable test requirement presence**

   A **Test Requirement** block is a bullet list directly under a `#### Scenario:` with four fields: `ID` (format `T-<CAPABILITY-UPPERCASE>-<NNN>`), `File` (test file path and test ID joined by `::`, e.g. `tests/foo.test.ts::test_name`), `Command` (exact runnable invocation from the project root), and `Pass` (machine-checkable criterion). Blocks reference the change's `## Test Strategy` section rather than repeating runner or environment details.

   For each scenario in the change's spec files, apply this decision table:

   ```
   behavior-changing? (exempt: docs, config, contract-preserving refactor)
    ├─ exempt ────────────────────────────────→ no finding
    ├─ no block ──────────────────────────────→ Warning (VL-n) "missing test requirement"
    └─ block present:
         complete (4 fields)?  no ────────────→ Warning (VL-n) "incomplete block", naming the missing field(s)
         ID format valid?      no ────────────→ Warning (VL-n) "malformed ID", stating the expected format
         genuine?              no ────────────→ Warning (VL-n) "not a runtime behavior assertion"
   design.md has ## Test Strategy?  no ───────→ single Info finding (one per change, not per block)
   ```

   Fake-block patterns — a block is not a genuine runtime-behavior assertion if:
   - **Static-only command** — the Command is a linter, formatter, type checker, vet, or compile check
   - **Existential pass criterion** — the Pass criterion asserts only that a file or test exists
   - **Behavior-unrelated command** — the Command does not plausibly exercise the scenario's declared outcome. Evidence rule: quote the scenario's outcome and the block's Command side by side

   **Boundary rule** — a content assertion (e.g., grep, diff) that verifies the scenario's declared outcome IS a Test Requirement.

   All 6d findings are Warning or Info, never Error.

   Feed the Coverage Metrics row "Requirements with executable test requirements | X (Y%)": X counts requirements where every behavior-changing scenario carries a complete, genuine block; Y counts requirements with at least one behavior-changing scenario. A scenario with a fake block keeps its requirement out of X.

   Report each finding with:
   - **Error**: Broken task dependencies
   - **Warning**: Non-testable requirements, vague qualifiers, unresolved placeholders, missing/incomplete/malformed/fake test requirement blocks (6d)
   - **Info**: Naming convention violations, missing `## Test Strategy` section (6d)

7. **Run Feasibility Checks**

   Evaluate whether the design is achievable given the actual codebase state.

   **7a. Design-to-codebase compatibility**
   - Identify source files the design proposes to modify (look for "modify", "update", "extend", "refactor" language paired with file paths or module names)
   - For each target file, read it and verify:
     - The file exists
     - Functions/classes/interfaces mentioned in the design actually exist in that file
     - The proposed modification approach is compatible with the current code structure (e.g., design says "add a method to UserService" — does UserService exist? Is it a class that can accept methods?)
   - Flag mismatches between what the design assumes and what actually exists

   **7b. Dependency and import feasibility**
   - If the design references libraries, packages, or modules, verify they are available:
     - Check package.json, requirements.txt, Cargo.toml, go.mod, etc. for declared dependencies
     - If a new dependency is proposed, note it (Info) — not an error, but worth flagging
   - If the design references internal modules/imports, verify those modules exist

   **7c. Pattern consistency**
   - Read 2-3 existing files in the same area of the codebase that the change targets
   - Compare the design's proposed approach against established patterns:
     - Does the codebase use classes or functions? Does the design match?
     - Does the codebase use a specific framework pattern (MVC, repository, etc.)? Does the design follow it?
     - Does the codebase use specific error handling patterns? Does the design account for them?
   - Flag significant deviations from established patterns

   Report each finding with:
   - **Error**: Design references functions/classes that don't exist and aren't being created by this change
   - **Warning**: Design proposes patterns inconsistent with existing codebase conventions
   - **Info**: New dependencies introduced, minor pattern deviations

8. **Run Coherence Checks**

   Evaluate whether proposal, design, and tasks align in scope and intent.

   **8a. Proposal-to-design scope alignment**
   - Parse the proposal's stated scope (goals, non-goals, capabilities)
   - Review the design for components, systems, or behaviors not mentioned in the proposal
   - Flag design elements that exceed proposal scope (scope creep)
   - Flag proposal goals that have no corresponding design coverage (gaps)

   **8b. Spec-to-design consistency**
   - For each spec requirement, determine if the design describes a mechanism that would satisfy it
   - Flag requirements that have no plausible design support
   - Flag design components that serve no spec requirement and aren't infrastructure

   **8c. Task ordering and buildability**
   - Parse tasks in order and build a mental dependency graph:
     - Does task N use/import/call something that task N+M creates?
     - Are foundational tasks (creating files, interfaces, types) ordered before tasks that depend on them?
   - Flag ordering issues where a task depends on output from a later task
   - Flag tasks that are too coarse to be actionable (e.g., "implement the entire authentication system" as a single task)
   - Flag tasks that are trivially fine-grained to the point of noise (e.g., "add a blank line")

   **8d. Security surface awareness** (apply only when the change touches auth, data handling, external I/O, or user input)
   - Does the design address input validation for new entry points?
   - Are there tasks for error handling on new failure modes?
   - If new external communication is introduced, is TLS/encryption mentioned?
   - If new credentials or secrets are involved, does the design reference a secrets manager?
   - Flag omissions as Warnings — don't block, but ensure awareness

   Report each finding with:
   - **Error**: Design exceeds proposal scope significantly, task ordering makes implementation impossible
   - **Warning**: Spec requirements with no design support, security surface omissions, overly coarse tasks
   - **Info**: Minor scope observations, trivially fine-grained tasks

9. **Produce Structured Output**

   Display the audit results in a structured format:

   ```
   ## Audit Report: <change-name>

   **Schema:** <schema-name>
   **Model:** <model that performed the audit>
   **Artifacts checked:** <list of artifacts that were read>

   ### Summary
   - Errors: <count>
   - Warnings: <count>
   - Info: <count>

   ---

   ### Findings

   | ID | Category | Severity | Description | Evidence |
   |----|----------|----------|-------------|----------|
   | AC-1 | Accuracy | Error | Missing spec for `pdf-export` | Listed in proposal "New Capabilities" but no file at `specs/pdf-export/spec.md` |
   | CM-1 | Completeness | Error | Requirement has no scenarios | `specs/csv-export/spec.md` → "User can filter exports" |
   | ... | ... | ... | ... | ... |

   ### Coverage Metrics

   | Metric | Value |
   |--------|-------|
   | Total requirements | <count> |
   | Total tasks | <count> |
   | Requirements with ≥1 task | <count> (<percent>%) |
   | Tasks with mapped requirement | <count> (<percent>%) |
   | Duplications found | <count> |
   | Ambiguities found | <count> |
   | Requirements with executable test requirements | <count> (<percent>%) |

   ---

   ### Verdict
   ```

   **Verdict based on findings:**
   - If errors exist: "Cannot proceed to implementation. Resolve errors first."
   - If only warnings: "Can proceed with caution. Consider addressing warnings."
   - If only info or clean: "Ready for implementation."
   - If no artifacts found: "No artifacts to audit. Create the change first."

10. **Detect regressions from prior resolved audits**

    Before persisting the new audit report, check if any prior audits in `openspec/changes/<name>/audits/` have been resolved. If so, compare the new findings against previously resolved findings to detect regressions.

    **10a. Parse resolved findings from prior audits**
    - Look in `openspec/changes/<name>/audits/` for audit files that have a `## Resolved` header
    - From each resolved audit, extract the finding IDs listed under the `### Resolved` section (e.g., `- AC-1: ...`)
    - Build a set of resolved finding IDs mapped to their source audit filename

    **10b. Compare against new findings**
    - For each finding in the new audit report, check if its stable ID (e.g., `AC-1`) appears in the resolved findings set
    - A match indicates a regression — the same issue was fixed but has reappeared

    **10c. Generate Regressions section**
    - If any regressions are found, insert a `### Regressions` section in the audit report output, between `### Findings` and `### Coverage Metrics`
    - Format as a table:

    ```
    ### Regressions

    | ID | Description | Source Audit |
    |----|-------------|--------------|
    | AC-1 | Missing spec for `pdf-export` | `2026-07-09T15-42-claude-opus.md` — was resolved, reappeared. Artifacts may have been edited outside the workflow. |
    ```

    - Classify each regression as a **Warning** severity — not an Error. The user may have intentionally reverted a fix.
    - Include regressions in the overall warning count in the `### Summary` section
    - If no regressions are found, skip the section entirely

    **10d. No prior resolved audits**
    - If no audits with `## Resolved` headers exist, skip regression detection entirely

11. **Persist the audit report**

    Save the structured output to a file within the change directory:

    ```
    openspec/changes/<name>/audits/<timestamp>-<model>.md
    ```

    - Create the `audits/` directory if it doesn't exist
    - Timestamp format: `YYYY-MM-DDTHH-MM` (e.g., `2026-07-09T15-42`)
    - Model: short identifier of the model that performed the audit (e.g., `claude-opus`, `gemini-pro`, `gpt-4o`)
    - Example: `openspec/changes/add-user-auth/audits/2026-07-09T15-42-claude-opus.md`

    The persisted file contains the full structured report exactly as displayed, enabling:
    - Multiple audits with different LLMs for comparison
    - Historical tracking across audit iterations (pre-fix, post-fix)
    - Decoupled workflow — `/opsx-apply-audit` can load from file without needing same session

    Announce: "Audit saved to `<path>`"

12. **Offer follow-up actions**

    After displaying the report, frame this as a checkpoint — the user decides — and offer, in order:
    - "Run `/opsx-apply-audit` in a fresh session (any model) to apply fixes to the artifacts."
    - "Run `/opsx-audit` again in a fresh session with a different model (Model C) for a second opinion."
    - "Run `/opsx-apply` to start implementing (if no blocking errors)."
    - "Run `/opsx-explore` to discuss the findings."

**Output Examples**

**Clean audit:**
```
## Audit Report: add-user-auth

**Schema:** spec-driven
**Model:** claude-opus
**Artifacts checked:** proposal.md, design.md, specs/user-auth/spec.md, tasks.md

### Summary
- Errors: 0
- Warnings: 0
- Info: 2

### Findings

| ID | Category | Severity | Description | Evidence |
|----|----------|----------|-------------|----------|
| CO-1 | Coherence | Info | Task has no direct spec requirement | Task 3.2 — may be implementation detail |
| FS-1 | Feasibility | Info | New dependency introduced | `argon2` not in current package.json |

### Coverage Metrics

| Metric | Value |
|--------|-------|
| Total requirements | 5 |
| Total tasks | 7 |
| Requirements with ≥1 task | 5 (100%) |
| Tasks with mapped requirement | 6 (86%) |
| Duplications found | 0 |
| Ambiguities found | 0 |
| Requirements with executable test requirements | 5 (100%) |

### Verdict
Ready for implementation.
```

**Audit with errors:**
```
## Audit Report: add-data-export

**Schema:** spec-driven
**Model:** claude-opus
**Artifacts checked:** proposal.md, design.md, specs/csv-export/spec.md, tasks.md

### Summary
- Errors: 5
- Warnings: 4
- Info: 2

### Findings

| ID | Category | Severity | Description | Evidence |
|----|----------|----------|-------------|----------|
| AC-1 | Accuracy | Error | Missing spec for listed capability | `pdf-export` in proposal but no `specs/pdf-export/spec.md` |
| AC-2 | Accuracy | Warning | Near-duplicate requirements | "Export data as CSV" (spec L12) ≈ "Generate CSV file from data" (spec L34) |
| AC-3 | Accuracy | Info | Terminology drift | "export job" (design) vs "export task" (proposal) vs "export operation" (spec) |
| CM-1 | Completeness | Error | Requirement has no scenarios | "User can filter exports" in `specs/csv-export/spec.md` |
| CM-2 | Completeness | Warning | Requirement has zero task coverage | "Export supports pagination" has no associated task |
| CM-3 | Completeness | Warning | Empty section | "Goals / Non-Goals" in design.md |
| VL-1 | Validity | Warning | Vague qualifier in requirement | "Export should be fast" — no measurable criteria |
| FS-1 | Feasibility | Error | Design references non-existent symbol | `ExportService.generatePdf()` — file exists but only has `exportData()` |
| FS-2 | Feasibility | Info | New dependency | `puppeteer` not in package.json |
| CO-1 | Coherence | Error | Task ordering violation | Task 2 uses `src/templates/base.ts` created in Task 5 |
| CO-2 | Coherence | Error | Design exceeds proposal scope | "notification system" not in proposal |

### Coverage Metrics

| Metric | Value |
|--------|-------|
| Total requirements | 8 |
| Total tasks | 12 |
| Requirements with ≥1 task | 6 (75%) |
| Tasks with mapped requirement | 10 (83%) |
| Duplications found | 1 |
| Ambiguities found | 1 |
| Requirements with executable test requirements | 3 (50%) |

### Verdict
Cannot proceed to implementation. Resolve errors first.
```

**Guardrails**

- **Read-only** — Never modify artifacts during audit. Flag issues; don't fix them.
- **Evidence-based** — Every finding must include specific evidence (file path, line reference, quoted text)
- **Stable IDs** — Finding IDs must be deterministic. Same input should produce same IDs on re-run.
- **Capped output** — Maximum 50 findings. Prioritize by severity. Summarize overflow.
- **Scope to referenced files** — When checking file existence, only check files explicitly mentioned in artifacts, not the entire codebase
- **Don't be prescriptive** — Focus on structural issues and inconsistencies. Use Info level for subjective observations
- **Handle missing artifacts gracefully** — If an artifact doesn't exist, note it but continue auditing what's available
- **Use path-aware tools** — Use glob for finding spec files, not hardcoded paths with forward slashes
- **Be thorough but efficient** — Check all artifacts that exist, but don't spend excessive time on large codebases
- **Feasibility checks are best-effort** — Reading source files to verify design claims is valuable but not exhaustive. Check the specific files and symbols referenced; don't audit the entire codebase.
- **Security checks are contextual** — Only apply security surface checks (8d) when the change touches auth, user input, data storage, external communication, or secrets. Don't flag security on purely cosmetic or refactoring changes.
- **Pattern checks require evidence** — When flagging pattern inconsistency, cite the existing files you read and the specific pattern observed. Don't assert conventions without checking.
- **Duplication requires semantic overlap** — Don't flag requirements as duplicates just because they share a few words. They must describe functionally overlapping behavior.
- **Terminology drift is cross-file only** — Don't flag term variations within a single file. Only flag when different artifacts use different terms for the same concept.
- **Regression detection is best-effort** — Parse resolved findings from prior audits by matching stable IDs. If a prior audit's resolution header is malformed or missing, skip regression detection for that file rather than failing.
- **Header parsing is position-sensitive** — When reading `## Resolved` headers from audit files, only check at the very start of the file. Do not match these patterns in the body of the audit report.
- **Backward compatible** — Audit files without lifecycle headers function normally. Regression detection gracefully handles legacy files.
