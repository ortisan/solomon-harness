# Security Best Practices

Purpose: a concrete, checkable playbook for threat modeling, SAST, dependency and vulnerability management, secure Python development, and secrets handling for the solomon-harness security specialist.

## When this applies

Run this skill on every design change, every code change that touches input handling, authentication, authorization, data storage, network calls, or dependencies, and on a recurring cadence for the whole repository. Threat model before code exists; scan and verify before merge; track and remediate after release.

## Threat modeling with STRIDE

Build a data flow diagram first. Mark trust boundaries (process boundaries, network hops, the boundary between user input and the application, the boundary between the app and the SurrealDB/SQLite memory store). Enumerate threats per element using the six STRIDE categories, then assign a mitigation and an owner to each.

1. Spoofing — attacker poses as another user or service. Mitigate with strong authentication, signed and short-lived session tokens, and cryptographic service identity (mTLS, signed JWTs with verified `aud`/`iss`).
2. Tampering — unauthorized modification of data, config, or binaries. Mitigate with MACs/digital signatures, strict filesystem permissions, integrity checks on the memory store, and parameterized writes.
3. Repudiation — a user denies an action because nothing recorded it. Mitigate with immutable, append-only audit logs, signed transactions, and tamper-evident log forwarding.
4. Information Disclosure — sensitive data reaches someone unauthorized. Mitigate with encryption at rest and in transit (TLS 1.2 minimum, 1.3 preferred), access checks at every read, field-level masking, and logs that never carry secrets or PII.
5. Denial of Service — resource exhaustion makes the service unavailable. Mitigate with rate limiting, request and execution timeouts, payload size caps, and bounded retries with backoff.
6. Elevation of Privilege — attacker gains rights above their level. Mitigate with least privilege, RBAC enforced at every endpoint (not only the UI), no dynamic privilege grants, and deny-by-default authorization.

Prioritize each identified threat with a CVSS-style severity (or DREAD if no CVSS vector exists, knowing DREAD scoring is subjective). Document every threat and its mitigation in the design/PLAN.md and persist the decision to project memory via `save_decision`. A threat with no mitigation and no accepted-risk sign-off blocks the design.

## SAST

Static analysis runs in CI and as a pre-commit hook. For this Python codebase:

- `bandit` for Python security anti-patterns. Fail the build on any HIGH severity / HIGH confidence finding. Triage MEDIUM. Suppress only with an inline `# nosec` plus a comment stating why; a bare `# nosec` is not allowed.
- `semgrep` with the `p/python`, `p/security-audit`, `p/secrets`, and `p/owasp-top-ten` rulesets for taint and pattern analysis across input-to-sink flows.
- `pip-audit` and `safety` already cover dependency CVEs (see below); keep them distinct from code SAST so signal stays clear.
- Optional deeper pass: CodeQL for dataflow/taint queries on the main branch.

Rules for SAST: zero new HIGH findings merge. Every suppression is justified in code and reviewed. Re-baseline findings per PR so reviewers see only what the change introduced, not the whole backlog.

## Dependency and supply-chain security

- Pin every dependency to an exact version and verify integrity with hashes (`pip install --require-hashes`, or a locked `uv.lock`/`requirements.txt` with hashes). Unpinned ranges are a supply-chain hole.
- Scan continuously: `pip-audit` (no account required, queries the PyPA advisory DB and OSV) as the baseline, optionally `safety` (current versions need a registered account for the full DB); add `trivy fs` or `grype` as a second source and for container images if any.
- Generate and publish an SBOM in CycloneDX or SPDX format per release so consumers can audit what shipped.
- Automate update PRs with Dependabot or Renovate, but never auto-merge without the full scan and test suite passing.
- License compliance: block copyleft licenses (GPL/AGPL) that conflict with the project license, and any unknown/unlicensed package. Keep an allowlist.
- Guard against typosquatting and dependency confusion: review new transitive packages, prefer a known index, and verify package names against the intended source.

## Vulnerability mitigation and remediation SLAs

Score every finding with CVSS. v4.0 is the current standard (published 2023); v3.1 is still what NVD and most tooling emit, so accept either vector. The qualitative severity bands are the same across both. Remediate by severity:

- Critical (9.0–10.0): patch or mitigate within 24–48 hours.
- High (7.0–8.9): within 7 days.
- Medium (4.0–6.9): within 30 days.
- Low (0.1–3.9): within 90 days.

For each vulnerability record the CVE/advisory ID, affected component and version, CVSS vector, the fix or compensating control, and a verification step. Log it with `log_issue` so it is tracked to closure. If a fix is not yet available, apply a compensating control (input filtering, feature flag off, network restriction) and document the accepted risk with an expiry date. Re-test after patching to confirm the vector is closed; do not close on the patch landing alone.

## Secure Python development

- Input validation: never trust input from clients, network, env, files, or the database. Validate against a strict schema (pydantic, jsonschema, or marshmallow) before use. Reject by default; allowlist over denylist.
- Parameterized queries only. Never build SQL/SurrealQL by string concatenation with user input. Use bound parameters or prepared statements.
- Output encoding: contextually encode/escape data written to HTML, shell, SQL, or logs. Strip markup before rendering to web clients.
- No dangerous sinks: avoid `eval`, `exec`, `pickle.loads` on untrusted data, and `subprocess(..., shell=True)`. Use `subprocess` with an argument list and `shell=False`.
- Safe parsers: `yaml.safe_load` (never `yaml.load` with the default loader); `defusedxml` for XML to block XXE and billion-laughs.
- Crypto and randomness: use the `secrets` module for tokens and the `argon2-cffi` (argon2id) or `bcrypt` libraries for password hashing. Never MD5/SHA-1 for security; never the `random` module for anything secret.
- Transport: keep TLS verification on (`verify=True` for `requests`); never disable certificate checks. Enforce TLS 1.2 as the floor, 1.3 where the stack supports it.
- SSRF and path traversal: validate and canonicalize URLs and file paths; restrict outbound destinations; resolve and confine paths under an allowed root.
- Safe defaults: `debug=False` in production frameworks; framework `SECRET_KEY` and all credentials come from the environment, never the code.
- Error handling: strip stack traces, hostnames, and schema details from responses to external callers. Return a generic message externally; keep full detail in internal logs only.

## Secrets handling

- Never hardcode credentials, API keys, or database passwords in source or commit them to git history. The harness reads credentials from `.agent/config.json` and env (`SURREAL_URL`, `SURREAL_USER`, `SURREAL_PASS`) — keep it that way.
- Store secrets in environment variables or a dedicated manager (HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager). Keep keys isolated from application logic.
- Scan for leaked secrets with `gitleaks`, `trufflehog`, or `detect-secrets` as a pre-commit hook and in CI on every push.
- On a leaked secret: rotate it immediately and treat it as compromised. Removing it from git history is necessary but not sufficient — assume it was captured.
- Rotate keys on a fixed schedule and after any suspected exposure. Keep `.env`, key files, and credential dumps out of version control via `.gitignore`.

## Mandatory project competencies

These are non-negotiable and carry into security work:

- TDD is mandatory: write the failing test first, then the fix (Red, Green, Refactor). Security fixes get a regression test that reproduces the vulnerability and fails before the fix.
- Mock all external API calls and services in tests so they run isolated and deterministic — including scanners, secret managers, and the memory store.
- STRIDE categories (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) are the required taxonomy for every threat model.
- SOLID and modular design: keep security controls (validation, auth, crypto) behind clear contracts so they are testable and replaceable.

## Common pitfalls

- Treating the UI/API gateway as the only authorization point while service-to-service and data-layer calls trust each other implicitly.
- Suppressing SAST findings with a bare `# nosec` and no justification.
- Pinning direct dependencies but ignoring transitive ones, or pinning versions without hashes.
- Logging request bodies, tokens, or PII at INFO/DEBUG and shipping them off-box.
- Catching a vulnerability and patching the version without a regression test, so it silently returns.
- Deleting a leaked secret from the latest commit but not rotating it.
- Validating input shape but not its semantics (size, range, encoding), leaving DoS and injection open.

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
