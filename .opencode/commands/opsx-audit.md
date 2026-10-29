---
description: Audit an existing change proposal for accuracy, completeness, and validity
---

Audit an existing change proposal for quality issues before implementation.

Use the Skill tool to invoke `openspec-audit-change`.

**Input**: Optionally specify a change name after `/opsx-audit` (e.g., `/opsx-audit add-auth`). If omitted, check if it can be inferred from conversation context. If vague or ambiguous, prompt for available changes.

The audit evaluates change artifacts for:
- **Accuracy**: Are artifacts consistent with each other and the actual codebase?
- **Completeness**: Are all required sections present and covered?
- **Validity**: Do artifacts follow structural conventions and contain well-formed content?

Findings are categorized as:
- **Error**: Blocks implementation (e.g., missing required artifact, contradictory specs)
- **Warning**: Should be addressed (e.g., vague requirement, uncovered task)
- **Info**: Observations for awareness (e.g., unconventional naming, large task scope)

After the audit, offer to help fix findings, start implementation with `/opsx-apply`, or discuss with `/opsx-explore`.
