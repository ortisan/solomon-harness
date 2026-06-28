## Mandatory project competencies


These are non-negotiable and carry into security work:

- TDD is mandatory: write the failing test first, then the fix (Red, Green, Refactor). Security fixes get a regression test that reproduces the vulnerability and fails before the fix.
- Mock all external API calls and services in tests so they run isolated and deterministic — including scanners, secret managers, and the memory store.
- STRIDE categories (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) are the required taxonomy for every threat model.
- SOLID and modular design: keep security controls (validation, auth, crypto) behind clear contracts so they are testable and replaceable.
