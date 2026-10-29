---
description: Validate a completed change's implementation against its proposal, specs, and design
---

Validate a change's implementation against its proposal, specs, design, and audit findings.

Use the Skill tool to invoke `openspec-validate-change`.

**Input**: Optionally specify a change name after `/opsx-validate` (e.g., `/opsx-validate add-auth`). If omitted, check if it can be inferred from conversation context. If vague or ambiguous, prompt for available changes.

The validation examines the implementation across five dimensions:
- **Spec compliance**: Are spec requirements satisfied by the actual code?
- **Test coverage**: Do tests exist for new requirements and edge cases?
- **Task completion**: Are all tasks completed and reflected in the codebase?
- **Code quality**: Are there obvious issues in changed files?
- **Regression safety**: Do changes break existing functionality patterns?

Findings are categorized as:
- **Error**: Blocks readiness (e.g., unsatisfied requirement, missing tests)
- **Warning**: Should be addressed (e.g., partial coverage, edge cases missing)
- **Info**: Observations for awareness (e.g., new dependencies, minor gaps)

The verdict indicates readiness:
- **Pass**: No errors — implementation validated, ready for archive
- **Conditional**: Only warnings — proceed with caution
- **Fail**: Errors exist — cannot proceed, resolve errors first

After validation, offer to fix findings, re-validate with a different model, or proceed to archive.
