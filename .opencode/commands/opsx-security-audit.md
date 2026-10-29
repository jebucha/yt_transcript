---
description: Run a security audit on a target codebase using the security-audit skill
---

Run a comprehensive security audit on a target codebase.

Use the Skill tool to invoke `security-audit`.

**Input**: Optionally specify a target codebase path after `/opsx-security-audit` (e.g., `/opsx-security-audit /path/to/project`). If omitted, use the current working directory from conversation context. If the target is unclear, prompt the user to specify.

The security audit guides the agent through reconnaissance, threat hunting, validation, reporting, structured output, and independent verification of the target codebase.

After the audit, review the findings and offer next steps such as remediation planning or further investigation.
