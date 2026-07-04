# Security Definition of Done

The evidence gate for security work: what must be demonstrably true across STRIDE modeling, scanning, dependency pinning, secrets hygiene, and regression tests before a change merges. Every item is checked by artifact or tool output, never by assertion.

## Common pitfalls

- STRIDE applied to only part of the data flow diagram — a skipped data store or trust boundary means the six-category walk never completed, and the model gives false assurance.
- A threat mitigated in the design but never recorded in PLAN.md or memory via `save_decision`, so the accepted risk has no owner or expiry when it resurfaces.
- SAST declared clean because bandit passed while semgrep never ran, or a new HIGH finding suppressed without an inline justification.
- `pip-audit` green taken as full dependency coverage without the second scanner (`trivy`/`grype`), leaving container and OS-layer CVEs unchecked.
- SBOM generation skipped because "dependencies did not change" — the pinned-with-hashes claim then cannot be audited against what actually ships.
- A vulnerability closed with the CVE noted but no CVSS vector and no regression test, so the severity SLA cannot be applied and the fix cannot be proven.
- The secret scan run only against the diff, missing credentials already sitting in history that a full-history gitleaks pass would surface.

## Definition of done


- [ ] Data flow diagram and trust boundaries documented; every element threat-modeled across all six STRIDE categories.
- [ ] Each identified threat has a mitigation (or signed accepted-risk with expiry) and is recorded in PLAN.md and project memory.
- [ ] SAST (bandit + semgrep) passes with zero new HIGH findings; all suppressions justified inline.
- [ ] `pip-audit`/`safety` and a second scanner (`trivy`/`grype`) pass; no unremediated finding above its severity SLA.
- [ ] Dependencies pinned with hashes; SBOM (CycloneDX/SPDX) generated; licenses checked against the allowlist.
- [ ] Secret scan (gitleaks/trufflehog/detect-secrets) is clean; no credentials in code, history, or logs.
- [ ] Input validated against a schema, queries parameterized, output encoded, no unsafe sinks, errors stripped for external callers.
- [ ] Each vulnerability tracked with CVE, CVSS vector, fix, and a regression test that failed before the fix.
- [ ] Tests mock all external services and pass; the fix is re-verified to confirm the vector is closed.
