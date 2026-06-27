# Auth Engineer Best Practices

Purpose: a concrete, checkable playbook for the secure identity layer end to end. It covers authentication, authorization, sessions and tokens, MFA, credential security, and the threat model, with the values and rules the auth_engineer applies on every identity-touching change.

## When this applies

Run this skill on any change that touches login, logout, session or token handling, an authorization decision, a password or MFA flow, an OAuth/OIDC/SAML integration, or a policy rule. Threat-model the flow before code exists; enforce the controls below in implementation; verify them before merge. Hand off security-sensitive changes to the `security` specialist and persist the design decision to project memory via `save_decision`.

## Core principles

- Deny by default. Every endpoint, service call, and data read starts from "no" and grants access only on an explicit, evaluated decision. The UI hiding a button is not authorization.
- Enforce on the server, at every layer. The gateway, the service, and the data layer each check; service-to-service and data-layer calls do not trust each other implicitly.
- Least privilege and short lifetimes. Grant the narrowest scope and the shortest validity that still works, then rotate.
- Phishing-resistant by preference. Where a phishing-resistant factor is available (WebAuthn/passkeys), prefer it over OTP.
- Fail closed and fail quiet. On any verification error, deny. Return a generic message to the caller; keep the detail in internal logs, never with secrets or tokens.
- Separate identity from authorization data. The ID token says who logged in; it is for the client. The access token says what is permitted; it is for the API. Never authorize an API call from an ID token.

## Authentication (OAuth 2.0 / OIDC)

Build on OAuth 2.0 and OpenID Connect with the Authorization Code grant plus PKCE for every client type, public and confidential. PKCE is mandatory in OAuth 2.1 and the current IETF Best Current Practice (RFC 9700); use `code_challenge_method=S256` only, never `plain`.

- Use the `state` parameter on every request and verify it on the callback (CSRF and request binding). Use the OIDC `nonce` and verify it in the ID token to bind the token to the session.
- Deprecate and reject the Implicit grant and the Resource Owner Password Credentials grant. They leak tokens and carry credentials through the app. Authorization Code with PKCE replaces both.
- Register exact, fully-qualified redirect URIs. No wildcards, no open patterns. Validate the redirect against the allowlist on both the authorization request and the response to close open-redirect and code-injection paths.
- Validate the ID token before trusting it: signature, `iss`, `aud` (must equal your `client_id`), `exp`, `nbf`, and `nonce`. Pin the expected signing algorithm and fetch keys from the provider JWKS.
- Social login (Google, GitHub, Apple, Microsoft): treat each as an OIDC/OAuth provider behind the same code path; verify the provider's `email_verified` claim before linking an account, and never trust an unverified email to match an existing local account.
- Enterprise SSO over SAML and OIDC: your app is the service provider / relying party. Delegate the actual authentication to the identity provider, require it to enforce a strong factor at its own origin (ideally phishing-resistant WebAuthn) with user verification, and consume the assurance it asserts (`acr`/`amr`, or the SAML `AuthnContext` / AAL) rather than re-implementing the factor yourself. For SAML, validate the assertion signature, `Conditions` (NotBefore/NotOnOrAfter), `Audience`, and `Recipient`, and protect against assertion replay and XML signature wrapping.
- Transport: TLS 1.2 is the floor, 1.3 preferred. Never disable certificate verification.

## Authorization (RBAC/ABAC and OPA/Rego)

Model access explicitly. Use RBAC for coarse role-to-permission mapping and ABAC for context-sensitive rules (owner, tenant, time, resource attributes). State the model in the design; do not scatter ad hoc `if user.is_admin` checks through the code.

- Policy as code with Open Policy Agent and Rego. Keep the policy decision (PDP) decoupled from enforcement (PEP). The service asks "may this subject do this action on this resource in this context?" and the policy answers.
- Deny by default in every policy: the default decision is `false`, and an allow requires an explicit matching rule.
- Enforce the decision at every endpoint and on every data access, not only the UI and not only the gateway.
- Sign and version policy bundles; turn on OPA decision logs so every allow/deny is auditable. Test policies with Rego unit tests, including the negative cases (the requests that must be denied).
- Check object-level authorization on every resource fetch (the OWASP "broken object level authorization" / IDOR class). A valid token is not permission to read an arbitrary id.

## Sessions and tokens

Keep access tokens short-lived and refreshable, and protect the refresh path against replay.

- Access tokens: 5 to 15 minutes. JWTs signed with an asymmetric algorithm (RS256, ES256, or EdDSA). Validate on every request: signature, `iss`, `aud`, `exp`, `nbf`, and reject `alg: none` and any algorithm other than the one you pinned. Never accept an unsigned or HMAC-when-you-expected-RSA token.
- Refresh tokens: either sender-constrained (DPoP or mTLS certificate-bound) or one-time-use with rotation on every exchange. With rotation, detect reuse: if an already-redeemed refresh token is presented again, revoke the entire token family and force re-authentication. Give refresh tokens an absolute expiry and an idle timeout; even with sliding expiry, force full re-authentication at a fixed ceiling (hours to weeks per the app's risk).
- Make tokens revocable. Maintain server-side revocation (token family / session store) so logout, password change, and reuse detection take effect immediately rather than waiting for `exp`.
- Browser-facing sessions: store the session or refresh token in a cookie set `HttpOnly`, `Secure`, `SameSite=Lax` (or `Strict` for high-value actions), `Path=/`, and prefer the `__Host-` prefix. Do not put tokens in `localStorage`, where XSS reads them.
- CSRF: for cookie-based sessions, pair `SameSite` with a per-session CSRF token (or the double-submit pattern) on every state-changing request.
- Regenerate the session identifier on privilege change (login, step-up, role change) to defeat session fixation. Invalidate the session server-side on logout.

## MFA

Offer and, for privileged or sensitive flows, require multi-factor authentication. Target AAL2 (NIST SP 800-63B) at minimum and prefer phishing-resistant factors.

- WebAuthn / passkeys first. FIDO2/WebAuthn is origin-bound public-key authentication, phishing-resistant by design and the recommended strong factor. Use synced passkeys for the general workforce and device-bound passkeys or hardware security keys for privileged and admin access (AAL3).
- TOTP (RFC 6238, 30-second step) is an acceptable second factor; allow a small clock-skew window (one step) and rate-limit verification attempts.
- SMS and voice OTP are restricted authenticators: transitional fallback only, never the primary factor for sensitive accounts.
- Provide step-up authentication for high-risk actions (changing email, MFA enrollment, payment, admin operations) rather than a single login-time check.
- Recovery is part of the threat model. Generate one-time, hashed-at-rest recovery codes; never let account recovery silently downgrade to a weaker factor than the account's enrolled MFA.

## Credential security

Follow NIST SP 800-63B for passwords and protect the credential store and the login surface.

- Hashing: Argon2id is the default (for example memory 19 MiB or higher, iterations 2 or higher, parallelism 1, tuned to your hardware), or bcrypt with a work factor of 10 to 12 (pre-hash with SHA-256 and base64-encode for inputs over 72 bytes to avoid silent truncation). Never MD5, SHA-1, or an unsalted/fast hash. Use a unique per-password salt (the library handles this) and consider a server-side pepper held outside the database.
- Password policy: minimum length 8, allow at least 64 characters and the full Unicode/printable set, no composition rules, and no forced periodic rotation. Reject passwords found in a breach corpus using a k-anonymity range check (Have I Been Pwned style) so the plaintext never leaves the server.
- Throttle and lock out: rate-limit authentication per account and per source, apply exponential backoff, and lock or challenge after repeated failures to blunt credential stuffing and brute force. Keep responses uniform so they do not reveal whether the username exists (no account enumeration).
- Store nothing in the clear: no plaintext passwords, no plaintext MFA secrets, no tokens in logs. Credentials and keys come from the environment or a secrets manager, never from source.

## Threat model

Threat-model the identity layer with the `security` specialist using STRIDE, and check the implementation against OWASP ASVS. Enumerate and mitigate at least:

- Account takeover: weak or reused passwords, missing MFA, insecure recovery. Mitigate with breached-password checks, MFA, and recovery that cannot downgrade assurance.
- Token theft and replay: tokens in `localStorage` or URLs, long-lived tokens, no binding. Mitigate with short access-token lifetimes, `HttpOnly`/`Secure` cookies, sender-constraining or rotation, and reuse detection.
- CSRF: state-changing requests trusting an ambient cookie. Mitigate with `SameSite`, CSRF tokens, and the OAuth `state` parameter.
- Open redirect and code injection: loose redirect URIs. Mitigate with exact-match redirect allowlists and PKCE.
- Privilege escalation and IDOR: missing object-level checks, authorization only at the UI/gateway. Mitigate with deny-by-default policy enforced at every layer and per-object authorization.
- Algorithm and signature attacks: `alg: none`, key confusion, unverified `aud`/`iss`. Mitigate by pinning the algorithm and validating all claims and the signature against the expected JWKS.

Record each threat and its mitigation in PLAN.md and project memory; a threat with no mitigation and no signed accepted-risk blocks the design.

## Mandatory duties (the role, with concrete values)

These carry the role's Core Duties into checkable terms:

- Authentication on OAuth 2.0 / OIDC, Authorization Code with PKCE (`S256`), `state` + `nonce` verified; social and enterprise login (SAML/OIDC) integrated through the same validated path.
- Authorization with explicit RBAC/ABAC and OPA/Rego policy-as-code: deny-by-default, least privilege, PDP/PEP decoupled, enforced at every endpoint and data access.
- Sessions and tokens: access tokens 5 to 15 minutes; refresh-token rotation with reuse detection (or sender-constrained); JWTs validated for `iss`, `aud`, `exp`, `nbf`, and signature; cookies `HttpOnly`, `Secure`, `SameSite`.
- Credential security: Argon2id (or bcrypt cost 10 to 12), breached-password checks, lockout and rate limiting, MFA with TOTP and WebAuthn/passkeys (AAL2 minimum, phishing-resistant preferred).
- Threat model against account takeover, token theft and replay, CSRF, open redirects, and privilege escalation; align with the `security` specialist on STRIDE and OWASP ASVS.
- Persist auth design decisions to project memory and hand off security-sensitive changes for review.

Project competencies still apply: TDD is mandatory (write the failing test first, including the negative authorization and rejected-token cases), mock external identity providers and the memory store so tests run isolated and deterministic, and keep auth, crypto, and policy behind clear contracts (SOLID) so they are testable and replaceable.

## Per-technology skills in this folder

This overview sets the rules; the per-technology skills carry the implementation detail. Read the relevant one before acting:

- `oauth_oidc.md` — OAuth 2.0 / OIDC flows, PKCE, token and claim validation.
- `saml_sso.md` — enterprise SSO over SAML: assertion validation and replay protection.
- `social_login.md` — Google, GitHub, Apple, and Microsoft provider integration.
- `jwt_and_sessions.md` — JWT signing and validation, refresh-token rotation, cookie and session hardening.
- `webauthn_mfa.md` — WebAuthn/passkeys, TOTP, step-up, and recovery.
- `password_and_credentials.md` — Argon2id/bcrypt hashing, breached-password checks, lockout and rate limiting.
- `opa_rego.md` — RBAC/ABAC modeling and OPA/Rego policy-as-code with deny-by-default and policy tests.

## Common pitfalls

- Authorizing an API call from the ID token instead of the access token.
- Storing tokens in `localStorage` or passing them in URLs, where XSS and logs capture them.
- Accepting `alg: none` or failing to pin the JWT algorithm, opening key-confusion attacks.
- Validating the signature but not `aud`/`iss`, so a token minted for another service is accepted.
- Wildcard or loosely matched redirect URIs, enabling open redirect and code injection.
- Authorization only at the UI or gateway while services and the data layer trust each other.
- Refresh tokens that never rotate and never expire, with no reuse detection.
- Forced periodic password rotation and composition rules instead of breached-password checks.
- SMS OTP treated as a strong factor for sensitive accounts.
- Account-recovery flows that silently downgrade below the account's enrolled MFA.

## Definition of done

- [ ] Auth flow threat-modeled with STRIDE and checked against OWASP ASVS; each threat has a mitigation (or signed accepted-risk with expiry) recorded in PLAN.md and project memory.
- [ ] Authentication uses Authorization Code + PKCE (`S256`); Implicit and password grants are not used; `state` and OIDC `nonce` are verified.
- [ ] Redirect URIs are exact-match allowlisted; social and enterprise (SAML/OIDC) logins validate signatures, audience, and verified email before account linking.
- [ ] Authorization is deny-by-default RBAC/ABAC via OPA/Rego, decoupled PDP/PEP, enforced at every endpoint and per-object data access; policies have unit tests covering the denied cases.
- [ ] Access tokens are 5 to 15 minutes; JWTs validate signature, `iss`, `aud`, `exp`, `nbf`, with a pinned algorithm and `alg: none` rejected.
- [ ] Refresh tokens are rotated with reuse detection (or sender-constrained), revocable, and bounded by an absolute expiry; session id regenerates on privilege change.
- [ ] Browser sessions use `HttpOnly`, `Secure`, `SameSite` cookies (`__Host-` prefix where applicable); state-changing requests are CSRF-protected.
- [ ] Passwords hashed with Argon2id (or bcrypt cost 10 to 12), checked against a breach corpus via k-anonymity; lockout and rate limiting active; responses do not enumerate accounts.
- [ ] MFA available and required for sensitive/privileged flows at AAL2 minimum, with WebAuthn/passkeys preferred and recovery codes hashed at rest.
- [ ] No secrets, tokens, or credentials in source, history, or logs; all read from env or a secrets manager.
- [ ] Tests written first (TDD), cover the rejected-token and denied-authorization paths, mock external IdPs and the memory store, and pass; the change is handed off to the `security` specialist for review.
