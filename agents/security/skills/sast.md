## SAST


Static analysis runs in CI and as a pre-commit hook. For this Python codebase:

- `bandit` for Python security anti-patterns. Fail the build on any HIGH severity / HIGH confidence finding. Triage MEDIUM. Suppress only with an inline `# nosec` plus a comment stating why; a bare `# nosec` is not allowed.
- `semgrep` with the `p/python`, `p/security-audit`, `p/secrets`, and `p/owasp-top-ten` rulesets for taint and pattern analysis across input-to-sink flows.
- `pip-audit` and `safety` already cover dependency CVEs (see below); keep them distinct from code SAST so signal stays clear.
- Optional deeper pass: CodeQL for dataflow/taint queries on the main branch.

Rules for SAST: zero new HIGH findings merge. Every suppression is justified in code and reviewed. Re-baseline findings per PR so reviewers see only what the change introduced, not the whole backlog.
