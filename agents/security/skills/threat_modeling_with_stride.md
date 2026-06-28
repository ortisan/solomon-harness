## Threat modeling with STRIDE


Build a data flow diagram first. Mark trust boundaries (process boundaries, network hops, the boundary between user input and the application, the boundary between the app and the SurrealDB/SQLite memory store). Enumerate threats per element using the six STRIDE categories, then assign a mitigation and an owner to each.

1. Spoofing — attacker poses as another user or service. Mitigate with strong authentication, signed and short-lived session tokens, and cryptographic service identity (mTLS, signed JWTs with verified `aud`/`iss`).
2. Tampering — unauthorized modification of data, config, or binaries. Mitigate with MACs/digital signatures, strict filesystem permissions, integrity checks on the memory store, and parameterized writes.
3. Repudiation — a user denies an action because nothing recorded it. Mitigate with immutable, append-only audit logs, signed transactions, and tamper-evident log forwarding.
4. Information Disclosure — sensitive data reaches someone unauthorized. Mitigate with encryption at rest and in transit (TLS 1.2 minimum, 1.3 preferred), access checks at every read, field-level masking, and logs that never carry secrets or PII.
5. Denial of Service — resource exhaustion makes the service unavailable. Mitigate with rate limiting, request and execution timeouts, payload size caps, and bounded retries with backoff.
6. Elevation of Privilege — attacker gains rights above their level. Mitigate with least privilege, RBAC enforced at every endpoint (not only the UI), no dynamic privilege grants, and deny-by-default authorization.

Prioritize each identified threat with a CVSS-style severity (or DREAD if no CVSS vector exists, knowing DREAD scoring is subjective). Document every threat and its mitigation in the design/PLAN.md and persist the decision to project memory via `save_decision`. A threat with no mitigation and no accepted-risk sign-off blocks the design.
