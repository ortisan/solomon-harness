# Security: STRIDE During Implementation

This skill governs how an implementer turns the six STRIDE threat categories into concrete code and configuration while building a feature, not just while drawing a diagram. The stance: walk Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, and Elevation of privilege against every feature that touches input, identity, data, or an external boundary; record the chosen mitigation in `PLAN.md`; and implement each as a specific, testable control. Security is a build-time activity, secure-by-default, not a review-time afterthought.

## The six categories and their default mitigations

STRIDE maps one-to-one onto the property each threat violates, which is what makes it useful at implementation time: each category points at a concrete control.

- Spoofing (violates authentication): authenticate every identity at the boundary and verify session tokens before any authorized action. Never infer identity from a client-supplied field like `user_id` in the body; derive it from the verified session or token.
- Tampering (violates integrity): use integrity checks and signatures on data that crosses a trust boundary, set least-privilege filesystem permissions, and validate every input against a strict schema so a payload cannot mutate state in unintended ways.
- Repudiation (violates non-repudiation): write immutable, append-only audit logs for security-relevant actions (login, permission change, money movement) with actor, action, target, and timestamp, so an action cannot later be denied.
- Information disclosure (violates confidentiality): encrypt in transit (TLS) and at rest, mask sensitive fields, and keep secrets and PII out of logs and out of error messages returned to callers.
- Denial of service (violates availability): apply rate limits, request timeouts, and payload size caps; bound every loop, allocation, and query so one caller cannot exhaust the service.
- Elevation of privilege (violates authorization): enforce least privilege and an explicit authorization check at every endpoint, including object-level checks (does this user own this resource?), never just route-level role checks.

The non-negotiable trio that recurs in almost every feature: parameterized queries (never build SQL by string concatenation with input), input validation at the boundary, and secrets in environment variables or a secret manager (never hardcoded or committed).

## Worked example: one threat to one mitigation

Take a real endpoint: `GET /accounts/{account_id}/statements`, which returns a customer's bank statements. Walk STRIDE and the threats fall out, but focus on one, Elevation of privilege via Insecure Direct Object Reference (IDOR): an authenticated user changes `account_id` in the URL to another customer's account and reads their statements. The route is authenticated, so Spoofing is handled; the failure is purely authorization. The mitigation is an object-level ownership check, not a role check.

```python
# VULNERABLE: route-level auth only. Any logged-in user reads any account.
@app.get("/accounts/{account_id}/statements")
def statements(account_id: int, session: Session = Depends(auth)):
    return db.query(
        "SELECT * FROM statements WHERE account_id = %s", (account_id,)
    )  # parameterized (Tampering/SQLi closed) but ownership never checked
```

```python
# MITIGATED: object-level authorization scoped to the verified identity.
@app.get("/accounts/{account_id}/statements")
def statements(account_id: int, session: Session = Depends(auth)):
    account = db.query_one(
        "SELECT owner_id FROM accounts WHERE id = %s", (account_id,)
    )
    if account is None or account.owner_id != session.user_id:
        audit.log("statement_access_denied",            # Repudiation: record it
                  actor=session.user_id, target=account_id)
        raise HTTPException(404)        # 404 not 403: do not confirm existence
                                        # (Information disclosure)
    return db.query(
        "SELECT * FROM statements WHERE account_id = %s LIMIT 100", (account_id,)
    )  # LIMIT caps the response (Denial of service)
```

That single handler now answers five of the six categories: Spoofing (the `auth` dependency verifies the session), Tampering and the SQLi path (parameterized queries), Information disclosure (404 instead of 403 so an attacker cannot enumerate which account ids exist), Denial of service (`LIMIT 100` bounds the result), and Elevation of privilege (the `owner_id != session.user_id` check). The Repudiation control is the audit line on the deny path. Note the identity comes from `session.user_id`, never from the request, and the authorization compares the requested object's owner against that verified identity.

## Turning the walk into the plan

In `PLAN.md`, list each STRIDE category for the feature with one line: the threat and the concrete control that closes it, or "not applicable" with a reason. This is a checklist the reviewer can verify against the diff. For anything involving credentials, tokens, or cryptography, defer to the auth and security agents' skills rather than improvising; this skill is about systematically reaching for the right control during implementation, not reinventing the primitives.

## Common pitfalls

- Treating STRIDE as a design-phase diagram exercise and never mapping a category to a line of code, so the threat model and the implementation drift apart.
- Trusting a client-supplied identity field (`user_id` in the body or query) instead of the verified session, which makes Spoofing and Elevation of privilege trivial.
- Checking role at the route but not ownership at the object (IDOR): role-level authorization passes while one user reads another's data.
- Returning 403 (or a distinct error) for a forbidden-but-existing resource, letting an attacker enumerate which ids exist; return the same 404 for absent and unauthorized.
- Building SQL by concatenating input even once "because it is just an internal field": the one unparameterized query is the injection point.
- Logging the sensitive value you are protecting (token, PII, full request body) while trying to add an audit trail, converting a Repudiation control into an Information disclosure leak.
- Adding rate limits and timeouts at the gateway but leaving an unbounded internal loop, query, or allocation that a single valid request can blow up (Denial of service).
- Hardcoding a secret "temporarily" for local testing and committing it; rotate and move to a secret manager instead.

## Definition of done

- [ ] `PLAN.md` lists all six STRIDE categories for the feature, each with a concrete mitigation or a justified "not applicable".
- [ ] Identity is derived from a verified session or token at the boundary, never from a client-supplied field (Spoofing).
- [ ] All database access uses parameterized queries; no string-concatenated SQL with input (Tampering).
- [ ] Security-relevant actions, including authorization denials, write to an immutable audit log with actor, action, target, timestamp (Repudiation).
- [ ] Sensitive data is encrypted in transit and at rest, masked in logs, and absent from errors returned to callers; forbidden-vs-absent responses are indistinguishable (Information disclosure).
- [ ] Rate limits, timeouts, payload size caps, and result `LIMIT`s bound every externally reachable path, including internal loops and queries (Denial of service).
- [ ] Every endpoint enforces an explicit authorization check including object-level ownership, not just route-level roles (Elevation of privilege).
- [ ] Secrets live in environment variables or a secret manager; none are hardcoded or committed.
- [ ] Negative tests exist for the key threats: unauthenticated access, cross-tenant/IDOR access, injection payloads, and oversized requests.
