---
name: openspec-apply-audit
description: Apply audit findings to an OpenSpec change's artifacts. Use after opsx-audit to resolve errors, warnings, and recommendations before implementation.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: jebucha
  version: "1.1"
---

Apply audit findings and recommendations to an OpenSpec change's artifacts.

After `/opsx-audit` identifies issues in a change's artifacts (proposal, design, specs, tasks), this skill resolves them — creating missing specs, adding scenarios, fixing references, and ensuring artifacts are consistent and complete before implementation begins.

---

**Store selection:** If the user names a store (a store is a standalone OpenSpec repo registered on this machine) or the work lives in one, run `openspec store list --json` to discover registered store ids, then pass `--store <id>` on the commands that read or write specs and changes (`new change`, `status`, `instructions`, `list`, `show`, `validate`, `archive`, `doctor`, `context`). Other commands do not take the flag. Hints printed by commands already carry the flag; keep it on follow-ups. Without a store, commands act on the nearest local `openspec/` root.

**Input**: Optionally specify a change name. If omitted, check if it can be inferred from conversation context. If vague or ambiguous you MUST prompt for available changes.

**Steps**

1. **Select the change**

   If a name is provided, use it. Otherwise:
   - Infer from conversation context if the user mentioned a change
   - Auto-select if only one active change exists
   - If ambiguous, run `openspec list --json` to get available changes and use the **AskUserQuestion tool** to let the user select

   Always announce: "Applying audit findings to change: <name>" and how to override (e.g., `/opsx-apply-audit <other>`).

2. **Check change status**
   ```bash
   openspec status --change "<name>" --json
   ```
   Parse the JSON to understand:
   - `schemaName`: The workflow being used (e.g., "spec-driven")
   - `artifacts`: Which artifacts exist and their status
   - `changeRoot`: Path to the change directory

   **If no artifacts exist yet:** Report that the change has no artifacts to fix. Suggest using `/opsx-propose` first.

3. **Locate the audit report**

    Look for audit results in the following order of priority:

    **3a. Check for persisted audit files**
    - Look in `openspec/changes/<name>/audits/` for saved audit reports
    - Use glob to find all `.md` files in the directory
     - **Derive state for each audit file:**
       - **Pending**: No `## Resolved` header at the start of the file
       - **Resolved**: Has a `## Resolved` header at the start
       - Legacy audit files without any lifecycle headers are treated as **Pending**
     - **Prefer Pending audits.** If a Pending audit exists, select it automatically.
     - If no Pending audit exists but Resolved audits exist, inform the user: "No pending audits found. All existing audits are resolved." Offer to run a new audit: "Want me to run `/opsx-audit <name>` to generate a fresh audit?"
    - If multiple Pending audits exist, list them with timestamp, model, and summary (errors/warnings count from each), then use the **AskUserQuestion tool** to let the user select
    - If exactly one audit exists and it is Pending, use it automatically

    **3b. Fall back to session context**
    - If no persisted audits exist, check conversation context for a prior `/opsx-audit` run in this session
    - If no audit is available anywhere, inform the user and suggest:
      "No audit report found. Want me to run `/opsx-audit <name>` first?"

    **If the selected audit verdict is clean** (0 errors, 0 warnings): Report that no fixes are needed. Suggest proceeding with `/opsx-apply`.

    Parse the audit report to extract:
    - Error findings (must fix)
    - Warning findings (should fix)
    - Info findings (optional)

    Announce which audit is being used: "Using audit: `<filename>`" (or "Using audit from current session" if from context).

4. **Read all change artifact files**

   Read every artifact file that exists for the change:
   - `openspec/changes/<name>/proposal.md`
   - `openspec/changes/<name>/design.md`
   - `openspec/changes/<name>/specs/**/*.md` (use glob to find all spec files)
   - `openspec/changes/<name>/tasks.md`

   These are the files that will be modified to resolve findings.

5. **Plan remediation from audit findings**

   Parse findings by their stable IDs (AC-1, CM-1, etc.) from the audit report.

   For each audit finding, determine the appropriate fix:

   **Errors (must fix):**

   *Accuracy:*
   - Missing spec for listed capability → Create the spec file with proper structure (requirements + scenarios) derived from the proposal description
   - Contradictory specs → Resolve the conflict by aligning to proposal intent; if ambiguous, ask user

   *Completeness:*
   - Missing required artifact → Create the artifact with appropriate content derived from existing artifacts
   - Missing requirement scenarios → Add scenarios that validate the requirement behavior

   *Validity:*
   - Broken task dependencies → Fix cross-references to valid task numbers

   *Feasibility:*
   - Design references non-existent functions/classes → Update design to reference actual codebase symbols, or add a task to create the missing symbol first
   - Design assumes wrong file structure → Correct file paths and module references in design

   *Coherence:*
   - Design exceeds proposal scope → Remove out-of-scope elements from design, or ask user if proposal should be expanded
   - Task ordering makes implementation impossible → Reorder tasks so dependencies are satisfied before dependents
   - Overly coarse tasks → Break into smaller actionable sub-tasks

   **Warnings (should fix):**

   *Accuracy:*
   - Referenced source file does not exist → Update path references in design/tasks or remove stale references
   - Near-duplicate requirements → Consolidate into a single requirement, keeping the more precise phrasing; update references in tasks

   *Completeness:*
   - Empty or placeholder sections → Fill in content derived from proposal and design context
   - Missing scenarios → Add meaningful scenarios covering happy path and edge cases
   - Requirements with zero task coverage → Add a task that addresses the requirement, placed in buildable order

   *Validity:*
   - Non-testable requirements / vague qualifiers → Rewrite with measurable/observable criteria while preserving intent (e.g., "fast" → "responds within 200ms under normal load")
   - Unresolved placeholders → Replace with concrete content derived from context, or ask user if unclear
   - Test requirement findings (6d):
     - "missing test requirement" → Generate a complete Test Requirement block under the scenario from its WHEN/THEN: derive `File` (test file path + test ID) and `Command` (runnable invocation from the project root) from the Test Strategy's runner and naming conventions; `Pass` is a machine-checkable criterion (default: "exit code 0"). If design.md has no `## Test Strategy` section, create it first (runner, full-suite command, typed prerequisites) before generating any block
     - "incomplete block" / "malformed ID" → Fill in the missing fields from the scenario and the Test Strategy; correct a malformed ID to `T-<CAPABILITY-UPPERCASE>-<NNN>`, keeping the existing capability prefix and number where possible
     - "not a runtime behavior assertion" (fake block) → Dual branch: if the scenario has runtime behavior, replace the block with a genuine assertion that verifies the scenario's declared outcome; if the scenario is actually exempt (docs, config, contract-preserving refactor), delete the block and note the exemption

   *Feasibility:*
   - Design proposes patterns inconsistent with codebase → Update design to follow established patterns, noting the convention observed

   *Coherence:*
   - Spec requirements with no design support → Add design mechanism to satisfy the requirement
   - Security surface omissions → Add appropriate tasks (input validation, error handling, encryption) for new attack surface
   - Scope creep in design (minor) → Flag and trim, or ask user

   **Info (optional, apply if straightforward):**
   - Naming convention violations → Rename to kebab-case, update all references
   - Tasks without spec coverage → Add a note linking to relevant requirement, or flag as implementation detail
   - New dependencies introduced → No fix needed, but note in tasks if installation step is missing
   - Trivially fine-grained tasks → Merge into parent task
   - Terminology drift → Standardize on the canonical term (first-used or most precise) across all artifacts
   - Minor duplications → Consolidate if straightforward; leave if they serve different contexts

   Present the full remediation plan to the user before applying any changes.

6. **Apply fixes (loop through findings)**

   For each finding being remediated:
   - Show which finding is being fixed
   - Make the artifact change
   - Keep changes minimal, consistent with existing artifact style and formatting
   - Announce completion of each fix

   **Pause if:**
   - A fix is ambiguous (multiple valid resolutions) → ask user to choose
   - A fix would significantly alter the design intent → confirm with user before proceeding
   - Fixing one issue would create a new inconsistency → flag it and propose resolution
   - User interrupts

   **When creating new spec files:**
   - Follow the structure of existing spec files in the change
   - Include `## Capability: <name>` header
   - Add `### Requirement:` blocks with `#### Scenario:` sub-blocks
   - Derive content from the proposal's capability description

   **When adding scenarios:**
   - Use Given/When/Then format if existing specs use it
   - Include at least one happy-path scenario and one edge case
   - Keep scenarios focused and testable

   **When populating empty sections:**
   - Derive content from related artifacts (proposal informs design, design informs tasks)
   - Keep content concise and consistent with the overall change scope

7. **Re-validate after fixes**

   After all fixes are applied, perform a quick consistency check:
   - Verify capability names still align between proposal and spec files
   - Verify task references are intact (no broken cross-references)
   - Verify no new empty sections were introduced
   - Verify new spec files follow naming conventions

   If new issues are found, report them and offer to fix immediately.

8. **Show summary and next steps**

    Display:
    - Findings resolved this session (with brief description of each fix)
    - Any remaining warnings or info items not addressed
    - Validation result (pass/new issues)
    - Suggest next action, framed as a checkpoint — the user decides — in order:
      - "Run `/opsx-audit` in a fresh session with a different model (Model C) to re-audit the fixed artifacts."
      - "Run `/opsx-apply` to start implementing."

9. **Persist resolution header to audit file**

    If the audit being applied is a persisted file (not from session context), prepend a resolution header to the audit file. This creates a lifecycle record inline with the audit report.

    **9a. Generate the resolution header**

    Construct a header block with the following fields:

    ```
    ## Resolved: <timestamp>
    ## Resolver: opsx-apply-audit
    ## Model: <model that performed the apply>
    ## Status: <Fully Resolved | Partially Resolved (N/M findings addressed)>

    ### Resolved
    - <finding-ID>: <brief description of fix applied>
    - ...

    ### Deferred
    - <finding-ID> [<severity>]: <brief description — why not addressed>
    - ...

    ---

    ```

    - Timestamp format: `YYYY-MM-DDTHH-MM` (e.g., `2026-07-09T16-30`)
    - Include only findings that were actually fixed or explicitly deferred in the "Resolved" and "Deferred" sections
    - If all findings from the audit were addressed, status is "Fully Resolved"
    - If some findings were skipped or not addressed, status is "Partially Resolved (N/M findings addressed)"

    **9b. Prepend to the audit file**

    Read the audit file, prepend the resolution header, and write it back. The original audit report content must remain unchanged below the `---` separator.

    **Important:** Parse lifecycle headers only at the very start of the file. The resolution header is prepended before any existing content. This preserves the full lifecycle chain.

    Announce: "Resolution header written to `<path>`"

**Output During Remediation**

```
## Applying Audit Fixes: <change-name>

### Remediation Plan
- [Error] Missing spec for `pdf-export` → Will create specs/pdf-export/spec.md
- [Error] Requirement "User can filter exports" has no scenarios → Will add scenarios
- [Warning] Section "Goals / Non-Goals" in design.md is empty → Will populate

Proceed? (y/n)

Fixing 1/3: Creating specs/pdf-export/spec.md...
✓ Spec created with 2 requirements and 4 scenarios

Fixing 2/3: Adding scenarios to "User can filter exports"...
✓ 2 scenarios added (happy path + invalid filter edge case)

Fixing 3/3: Populating "Goals / Non-Goals" in design.md...
✓ Section populated based on proposal scope
```

**Output On Completion**

```
## Audit Fixes Applied: <change-name>

**Schema:** <schema-name>
**Findings resolved:** 3/3

### Fixed This Session
- ✓ [Error] Created missing spec: specs/pdf-export/spec.md
- ✓ [Error] Added 2 scenarios to "User can filter exports"
- ✓ [Warning] Populated "Goals / Non-Goals" section

### Remaining (not addressed)
- [Info] Task 3.2 has no direct spec requirement (implementation detail — no fix needed)

### Quick Validation
✓ Capability names consistent between proposal and specs
✓ Task references intact
✓ No new empty sections introduced

### Resolution Header
✓ Resolution header written to audits/2026-07-09T15-42-claude-opus.md

Artifacts are clean. Checkpoint — the user decides: re-audit in a fresh session with a different model (Model C) via `/opsx-audit`, or proceed to `/opsx-apply` to start implementing.
```

**Output On Pause (Ambiguous Fix)**

```
## Remediation Paused: <change-name>

**Progress:** 2/3 findings fixed

### Ambiguous Finding
**[Error]** Contradictory specs: `user-auth/spec.md` says sessions expire in 30m, `admin-panel/spec.md` says sessions expire in 8h.

**Options:**
1. Align both to 30m (stricter security posture)
2. Use 30m for users, 8h for admins (role-based differentiation)
3. Defer — what's the intended behavior?

What would you like to do?
```

**Guardrails**
- Always present the remediation plan before making changes — get user confirmation
- Never alter design intent — fixes should align artifacts to stated goals, not rewrite goals
- Keep changes minimal and scoped to each finding
- If a fix is ambiguous, pause and ask — don't guess at intent
- Maintain existing artifact style and formatting conventions
- Do not introduce new capabilities or requirements not present in the proposal
- After fixing, validate that fixes don't create new inconsistencies
- Only address findings from the audit — don't expand scope to unrelated improvements
- Preserve all existing content that isn't directly related to a finding
- Use existing spec files as style reference when creating new ones
- **Audit state is derived, not stored** — determine Pending/Resolved from headers, never from explicit status fields
- **Backward compatible** — audit files without lifecycle headers are always treated as Pending
- **Header parsing is position-sensitive** — only parse `## Resolved` headers at the very start of the file; do not match these patterns in the body of the audit report
- **Prepend-only mutations** — when writing a resolution header, always prepend to the file; never modify or delete existing content

**Fluid Workflow Integration**

This skill supports the "actions on a change" model:

- **Can be invoked anytime** after an audit has been run
- **Pairs with `/opsx-audit`**: audit identifies issues, apply-audit resolves them
- **Iterative**: Can be run multiple times if new issues surface after fixes
- **Gates `/opsx-apply`**: Ensures artifacts are clean before implementation begins
- **Non-destructive intent**: Fixes artifacts to match stated goals — never changes the goals themselves
