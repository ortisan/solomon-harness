## Security: STRIDE during design


Walk the STRIDE categories while planning any feature that touches input, auth, data, or external boundaries, and note mitigations in `PLAN.md`:

- Spoofing: authenticate identities, verify session tokens.
- Tampering: integrity checks, signatures, least-privilege filesystem permissions.
- Repudiation: immutable audit logs for security-relevant actions.
- Information Disclosure: encrypt in transit and at rest, mask sensitive fields, keep them out of logs.
- Denial of Service: rate limits, timeouts, payload size caps.
- Elevation of Privilege: least privilege and RBAC checks at every endpoint.
