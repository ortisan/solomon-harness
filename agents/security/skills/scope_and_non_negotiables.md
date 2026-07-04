# Security Specialist Best Practices

Purpose: a concrete, checkable playbook for threat modeling, SAST, dependency and supply-chain security, secrets handling, secure Python development, and vulnerability remediation for the solomon-harness security specialist.

## Scope and non-negotiables

- When this applies: every design change; every code change that touches input handling, authentication, authorization, data storage, network calls, subprocesses, or dependencies; and a recurring cadence over the whole repository. Threat model before code exists; scan and verify before merge; track and remediate after release.
- TDD is mandatory: a security fix starts with a regression test that reproduces the vulnerability and fails before the fix (Red, Green, Refactor). Never patch a version and close without that test.
- Mock all external API calls and services in tests — scanners, secret managers, advisory databases, and the memory store — so tests run isolated and deterministic.
- STRIDE (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) is the required taxonomy for every threat model.
- Secure-by-default is the house convention: deny-by-default authorization, allowlist validation, parameterized queries, TLS verification on, secrets out of code.
- SOLID and modular design: keep security controls (validation, auth, crypto) behind clear contracts so they are testable and replaceable.
- Persist outcomes: threats, accepted risks, and findings go to project memory (`save_decision`, `log_issue`) and to PLAN.md. A risk decision that lives only in chat does not exist.
