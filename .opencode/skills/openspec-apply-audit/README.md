# opsx-apply-audit

Apply audit findings and recommendations to an OpenSpec change's artifacts.

## Overview

`/opsx-apply-audit` is the remediation step in the OpenSpec workflow. After `/opsx-audit` identifies structural issues in a change's artifacts (proposal, design, specs, tasks), this command resolves them — creating missing specs, adding scenarios, fixing references, and ensuring artifacts are consistent and complete before implementation begins.

## Workflow Position

```
/opsx-propose  →  /opsx-audit  →  /opsx-apply-audit  →  /opsx-apply
   (create)        (review)         (fix artifacts)      (implement code)
```

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `/opsx-propose` | Generate change artifacts (proposal, design, specs, tasks) |
| 2 | `/opsx-audit` | Review artifacts for accuracy, completeness, and validity (read-only) |
| 3 | `/opsx-apply-audit` | Resolve errors and warnings found during audit |
| 4 | `/opsx-apply` | Implement the actual source code changes described in the artifacts |

## Usage

```
/opsx-apply-audit [change-name]
```

If the change name is omitted, the command will:
- Infer from conversation context
- Auto-select if only one active change exists
- Prompt for selection if ambiguous

## Prerequisites

- A change must exist with artifacts (run `/opsx-propose` first)
- An audit must exist — either as a persisted report in `openspec/changes/<name>/audits/` or, failing that, in the current session's context (run `/opsx-audit` first)
- The command checks `openspec/changes/<name>/audits/` for saved reports, derives each file's state from its `## Resolved` lifecycle header (Pending vs Resolved), and prefers Pending audits; it falls back to session context only when no persisted file exists
- If no audit is found anywhere, the command will suggest running one

## What It Does

### 1. Locates the Audit Report

Checks `openspec/changes/<name>/audits/` for persisted audit reports first. Each file's state is derived from its `## Resolved` lifecycle header — **Pending** (no header at the start of the file; legacy files without lifecycle headers count as Pending) or **Resolved** (header present). Pending audits are preferred: a single Pending audit is used automatically, and when multiple exist they are listed (timestamp, model, findings count) for you to pick from. If no Pending audit exists but Resolved ones do, the command tells you all existing audits are resolved and offers to run a fresh `/opsx-audit`. If no persisted audit exists, the command falls back to a prior `/opsx-audit` run in the current session. If there is no audit anywhere, it suggests running one.

The selected report's findings are then parsed by severity:
- **Errors** — must fix before implementation
- **Warnings** — should fix for quality
- **Info** — optional, applied if straightforward

### 2. Plans Remediation

For each finding, determines the appropriate fix:

| Finding Type | Resolution |
|---|---|
| Missing spec for listed capability | Creates spec file with requirements + scenarios |
| Contradictory specs | Resolves conflict aligned to proposal intent |
| Missing requirement scenarios | Adds Given/When/Then scenarios |
| Broken task dependencies | Fixes cross-references |
| Non-testable requirements | Rewrites with measurable criteria |
| Empty/placeholder sections | Populates from proposal/design context |
| Naming convention violations | Renames to kebab-case |
| Stale file references | Updates or removes invalid paths |
| Missing test requirement (6d) | Generates a Test Requirement block from the scenario's WHEN/THEN; `File` and `Command` derived from the Test Strategy; the `## Test Strategy` section is created first when absent |
| Incomplete / malformed test requirement block (6d) | Fills in the missing fields; corrects the ID to `T-<CAPABILITY-UPPERCASE>-<NNN>` |
| Fake test requirement block (6d) | Replaces the block with a genuine assertion, or deletes it (noting the exemption) when the scenario is actually exempt |

The full plan is presented to the user for confirmation before any changes are made.

### 3. Applies Fixes

Iterates through findings, making targeted changes to the affected artifact files:
- `openspec/changes/<name>/proposal.md`
- `openspec/changes/<name>/design.md`
- `openspec/changes/<name>/specs/**/*.md`
- `openspec/changes/<name>/tasks.md`

### 4. Re-validates

After fixes are applied, runs a quick consistency check:
- Capability names align between proposal and specs
- Task references are intact
- No new empty sections introduced
- New spec files follow conventions

### 5. Reports Results

Shows what was fixed, what remains, and suggests next steps. Framed as a checkpoint — the user decides — the next-action suggestion offers first a Model C re-audit of the fixed artifacts in a fresh session (`/opsx-audit`), then proceeding to implementation (`/opsx-apply`) as the alternative.

## Behavior on Ambiguity

The command pauses and asks the user when:
- Multiple valid resolutions exist for a finding
- A fix would alter design intent
- Fixing one issue would create a new inconsistency

It will never guess at intent or silently change the goals of a change.

## Guardrails

- **Confirmation required** — Always presents the remediation plan before making changes
- **Intent preservation** — Fixes align artifacts to stated goals; never rewrites the goals
- **Minimal changes** — Each fix is scoped to its finding only
- **Style preservation** — Maintains existing artifact formatting and conventions
- **No scope expansion** — Only addresses audit findings; doesn't improve unrelated content
- **Post-fix validation** — Catches cascading issues introduced by fixes

## Iterative Use

The command can be run multiple times:

```
/opsx-audit        → finds 3 errors, 2 warnings
/opsx-apply-audit  → fixes errors, 1 warning ambiguous (paused)
                     user provides guidance
/opsx-apply-audit  → fixes remaining warning
/opsx-audit        → clean (0 errors, 0 warnings)
/opsx-apply        → begin implementation
```


## Example Output

### Clean Run

```
## Audit Fixes Applied: add-data-export

**Schema:** spec-driven
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

Artifacts are clean. Run `/opsx-apply` to start implementing.
```

### Paused (User Input Needed)

```
## Remediation Paused: add-user-auth

**Progress:** 2/3 findings fixed

### Ambiguous Finding
**[Error]** Contradictory specs: `user-auth/spec.md` says sessions expire in 30m,
`admin-panel/spec.md` says sessions expire in 8h.

**Options:**
1. Align both to 30m (stricter security posture)
2. Use 30m for users, 8h for admins (role-based differentiation)
3. Defer — what's the intended behavior?

What would you like to do?
```
