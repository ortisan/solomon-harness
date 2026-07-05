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

## Common pitfalls

- A design change that crosses a trust boundary implemented before any threat model exists — the scope requires modeling before code, and a STRIDE pass after merge finds flaws when the design is expensive to change.
- A vulnerability "fixed" by bumping a version with no failing regression test written first — it violates the TDD rule and leaves the vector unproven.
- Tests that call a live scanner, advisory database, or secret manager — nondeterministic runs that break the mock-all-external-services rule.
- A query built by string interpolation because the value is "internal" — parameterized queries are the secure-by-default convention, and internal values become external the day a call site changes.
- TLS verification disabled or an allowlist widened "temporarily" with no recorded decision — deny-by-default is the house convention, and undocumented exceptions become permanent.
- A risk acceptance discussed in chat but never persisted with `save_decision` or `log_issue` — per this scope, a risk decision that lives only in chat does not exist.
- Validation, auth, or crypto logic inlined across call sites instead of behind a clear contract, so the control can be neither tested nor replaced.

## Definition of done

- [ ] The change was classified against the scope triggers (input handling, authentication, authorization, storage, network calls, subprocesses, dependencies), and each applicable trigger got a STRIDE pass before implementation.
- [ ] Every security fix started from a regression test that reproduced the vulnerability and failed before the fix (Red, Green, Refactor).
- [ ] All tests mock scanners, secret managers, advisory databases, and the memory store; the suite runs deterministic and offline.
- [ ] Secure-by-default holds in the diff: deny-by-default authorization, allowlist validation, parameterized queries, TLS verification on, secrets out of code.
- [ ] Security controls added or changed sit behind clear contracts with their own tests, keeping them replaceable.
- [ ] Threats, accepted risks, and findings are persisted to PLAN.md and project memory via `save_decision` and `log_issue`.
