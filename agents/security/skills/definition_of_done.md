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
