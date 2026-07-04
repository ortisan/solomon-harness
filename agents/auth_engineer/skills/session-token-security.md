# Session and Token Security

Purpose: a concrete standard for choosing, issuing, validating, and revoking session and bearer credentials. It covers JWT vs opaque tokens, JWT validation, refresh-token rotation with reuse detection, hardened cookies, and CSRF defense. Use it whenever you mint a credential a client will present back, set an authentication cookie, or accept one at an endpoint.

## Standards baseline

Pin to these documents; cite the RFC, not a blog, in design reviews and ADRs.

- RFC 7519 JWT, RFC 7515 JWS, RFC 7517 JWK / JWKS, RFC 7518 JWA.
- RFC 8725 JWT Best Current Practices (algorithm pinning, `none` rejection, confusion attacks). `draft-ietf-oauth-rfc8725bis` is in progress and tightens `alg` validation; track it but build to 8725 today.
- RFC 9700 Best Current Practice for OAuth 2.0 Security, published January 2025 (BCP 240). It finalizes the long-running OAuth Security BCP (`draft-ietf-oauth-security-topics`) and makes refresh-token rotation **or** sender-constraining mandatory for public clients. This is the authority for the refresh section below.
- RFC 7662 Token Introspection (opaque token validation), RFC 7009 Token Revocation, RFC 9449 DPoP (sender-constrained tokens).
- RFC 6265bis for `SameSite` and the `__Host-`/`__Secure-` cookie prefixes.
- OWASP CSRF Prevention Cheat Sheet and OWASP ASVS v5 chapters on session management and tokens.
- `draft-ietf-oauth-browser-based-apps` (Browser-Based Apps BCP): for SPAs, prefer the Backend-for-Frontend (BFF) pattern over storing tokens in JavaScript-reachable storage.

## JWT vs opaque tokens: choose deliberately

This is the first decision and it drives everything else. Default to opaque, stateful tokens for sessions; reach for JWT only when stateless cross-service validation earns its keep.

| Concern | Opaque token (random id + server store) | JWT (signed, self-contained) |
| --- | --- | --- |
| Validation | Lookup in DB/cache (Redis) | Verify signature locally, no I/O |
| Revocation | Immediate (delete the row) | Hard: valid until `exp` unless you run a denylist |
| Payload exposure | None (no data in token) | Claims are base64, readable by anyone holding it |
| Size | ~32 bytes | 500 bytes to several KB; can break the 4096-byte cookie limit |
| Best fit | First-party sessions, logout-now requirements | Service-to-service access tokens, short-lived, multiple verifiers |

Rules:

- Use opaque, server-side sessions for browser-facing first-party apps. You get instant revocation (logout, password change, admin kill) for free.
- Use JWT for access tokens that independent resource servers must validate without calling the issuer. Keep them short-lived (5 to 15 minutes) precisely because you cannot revoke them mid-life.
- Never put secrets, PII you would not log, or authorization decisions you cannot afford to have read in a JWT. The signature protects integrity, not confidentiality. Encrypt (JWE) only if you genuinely need confidential claims, and accept the added key-management cost.
- If you need JWT for performance but also need fast revocation, run a short-TTL access JWT plus a `jti` denylist checked on sensitive operations, or accept up-to-`exp` staleness as an explicit, documented risk.

## JWT validation

Most JWT CVEs are validation bugs, not crypto breaks. The two recurring classes are the `alg: none` bypass and algorithm confusion (signing an RS256-verifier with the public key treated as an HS256 secret). Both are defeated by pinning algorithms server-side and never trusting the token header.

Validation must, in order:

1. Pin `algorithms` to an explicit allowlist (for example `["RS256"]` or `["EdDSA"]`). Never read `alg` from the header to decide how to verify. Reject `none` unconditionally.
2. Resolve the key by `kid` from a cached JWKS endpoint. Do not fetch JWKS per request; cache with a TTL and refresh on unknown `kid`.
3. Verify the signature.
4. Verify `iss` equals your expected issuer and `aud` contains this resource server. A token minted for another audience must be rejected. Audience confusion is a real privilege-escalation path.
5. Verify `exp` (and `nbf`/`iat` if present) with at most 30 to 60 seconds of clock leeway. More leeway widens the replay window.
6. Require the claims you depend on (`sub`, `exp`, `aud`, `iss`); a missing claim is a rejection, not a default.
7. For tokens that can be confused with another JWT type, set and check `typ` (explicit typing, for example `at+jwt` for access tokens).

Python, PyJWT (require `>= 2.x`; 2.x makes `algorithms` mandatory when verifying a signature, which kills the `none` bypass by default). Use the `cryptography` extra for RS/ES/EdDSA.

```python
import jwt
from jwt import PyJWKClient

# Cache this client; it caches JWKS keys internally.
_jwks = PyJWKClient("https://issuer.example.com/.well-known/jwks.json")

def verify_access_token(token: str) -> dict:
    signing_key = _jwks.get_signing_key_from_jwt(token).key
    return jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],                 # pin; never trust the header alg
        issuer="https://issuer.example.com",  # iss must match
        audience="api://orders",              # aud must contain this resource
        leeway=30,                            # clock skew, seconds; keep small
        options={
            "require": ["exp", "iat", "iss", "aud", "sub"],
            "verify_signature": True,
            "verify_exp": True,
            "verify_aud": True,
            "verify_iss": True,
        },
    )
```

Node, `jose` (panva). Prefer `jose` over `jsonwebtoken` for new work: it is actively maintained, Web Crypto based, runs on Node/Deno/Bun/edge, and supports EdDSA and RSA-PSS. `jsonwebtoken` is feature-frozen; if you must use it, require `>= 9.0.0` (older versions had the algorithm-confusion and key-type CVEs, e.g. CVE-2022-23529) and always pass `algorithms`.

```js
import { createRemoteJWKSet, jwtVerify } from 'jose'

const JWKS = createRemoteJWKSet(new URL('https://issuer.example.com/.well-known/jwks.json'))

export async function verifyAccessToken(token) {
  const { payload } = await jwtVerify(token, JWKS, {
    algorithms: ['RS256'],          // mandatory; omitting it reopens the 2015 bug
    issuer: 'https://issuer.example.com',
    audience: 'api://orders',
    clockTolerance: '30s',
    requiredClaims: ['sub', 'exp', 'iat'],
    maxTokenAge: '15m',             // reject stale tokens even if exp is generous
  })
  return payload
}
```

Other stacks: Go uses `golang-jwt/jwt/v5` (the `dgrijalva/jwt-go` package is abandoned; v5 rejects `none` by default when a key is set, and you should still pass `jwt.WithValidMethods([]string{"RS256"})` to pin the algorithm and close off confusion attacks). Java/Spring uses Nimbus JOSE+JWT via `NimbusJwtDecoder` with `JwtValidators` for issuer and audience. The pin-the-algorithm rule is identical everywhere.

HMAC (HS256) notes: only for single-party tokens where issuer and verifier share the secret. The secret must be at least 256 bits of CSPRNG output. Never use HS256 across a trust boundary, and never let an endpoint accept both RS256 and HS256 with the same key material; that is the classic confusion attack.

Pitfalls: verifying with `decode` instead of `verify`; logging full tokens (they are bearer credentials); trusting `exp` with hours of leeway; fetching JWKS without caching (self-inflicted DoS); accepting a token whose `aud` is some other service.

## Opaque tokens and introspection

For opaque access tokens issued by an authorization server you do not control, validate via RFC 7662 introspection (`POST /introspect` with the token). Cache the positive result only up to the token's `exp`, and treat `active: false` as an immediate reject. For your own first-party sessions, "introspection" is just a keyed lookup in Redis or your session table; key by a hash of the token, not the raw value, so a store dump does not leak live credentials.

## Refresh-token rotation with reuse detection

Per RFC 9700, every public client must use refresh-token rotation or sender-constrained tokens. Rotation turns the refresh token into a single-use credential and gives you a theft tripwire.

Model:

- Each login starts a token **family** (a `family_id`). Every refresh issues a new access token and a new refresh token in the same family, and marks the presented refresh token as used.
- A refresh token is single-use. Presenting a token already marked used means either replay or theft; you cannot tell which, so assume the worst: revoke the entire family and force re-authentication. This is the reuse detection that breaks an attacker's persistence and emits a security event.
- Store only a hash of the refresh token (SHA-256 is fine here; it is high-entropy, not a password). Compare with a constant-time check.
- Set both a sliding idle expiry and an absolute family lifetime. Typical: refresh idle 8 to 24 hours, absolute cap 7 to 30 days; access token 5 to 15 minutes.

```python
import hashlib, secrets

def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()

def rotate_refresh(presented_raw: str) -> tuple[str, str]:
    row = db.get_refresh_by_hash(_hash(presented_raw))
    if row is None or row.revoked or row.expires_at < now():
        raise Unauthorized()
    if row.used:                              # already exchanged once
        db.revoke_family(row.family_id)       # reuse detected: revoke the whole chain
        audit.alert("refresh_reuse", user_id=row.user_id, family_id=row.family_id)
        raise Unauthorized()
    db.mark_used(row.id)
    new_raw = secrets.token_urlsafe(32)       # >= 256 bits of entropy
    db.insert_refresh(
        family_id=row.family_id, user_id=row.user_id,
        token_hash=_hash(new_raw), prev_id=row.id,
        expires_at=now() + idle_ttl(),
    )
    return mint_access_token(row.user_id), new_raw
```

Strengthen further with sender-constraining (RFC 9449 DPoP, or mTLS-bound tokens) so a stolen refresh token is useless without the client's proof-of-possession key. This is the recommended upgrade for high-value APIs.

Pitfalls: rotating the access token but not the refresh token (no tripwire); revoking only the presented token instead of the family (the attacker keeps the next one in the chain); a race where two near-simultaneous legitimate refreshes both look like reuse (allow a small grace window, e.g. accept the immediate predecessor for a few seconds, but still log it); storing refresh tokens in plaintext.

## Secure cookies

When the credential lives in a cookie, the cookie attributes are the security boundary.

- `HttpOnly`: mandatory on any cookie holding a session id or token. It keeps XSS from reading the credential. The only cookie that is legitimately not `HttpOnly` is a CSRF token the client script must echo back.
- `Secure`: mandatory. Without it the cookie travels over plain HTTP and is trivially sniffed.
- `SameSite`: defaults to `Lax` in Chromium since Chrome 80 (Feb 2020), but set it explicitly. Use `Lax` for the primary session cookie (lets a user follow a link from email into a logged-in session while blocking cross-site POST). Use `Strict` for refresh-token or step-up cookies that never need to ride a top-level navigation. `None` requires `Secure` and is only for genuine third-party/cross-site contexts; it provides no CSRF protection by itself.
- `__Host-` prefix: the strongest binding. A `__Host-` cookie must be `Secure`, must have `Path=/`, and must have no `Domain`, so it is host-only and cannot be overwritten by a sibling subdomain. Use it for the session cookie. Because it forces `Path=/`, you cannot path-scope it; for a path-scoped refresh cookie use the `__Secure-` prefix with an explicit `Path`.
- Keep total cookie size under 4096 bytes. A fat JWT in a cookie that silently exceeds the limit gets dropped and produces baffling logout loops.

Session cookie and a path-scoped refresh cookie:

```
Set-Cookie: __Host-session=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=3600
Set-Cookie: __Secure-rt=<token>; Path=/auth/refresh; Secure; HttpOnly; SameSite=Strict; Max-Age=2592000
```

Framework config:

```js
// Express
res.cookie('__Host-session', sid, {
  httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge: 3_600_000,
})
```

```python
# Flask
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
```

```python
# Django settings.py
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_NAME = "__Host-sessionid"   # ok: Django defaults to Path=/ and no Domain
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
```

Browser token storage: do not put access or refresh tokens in `localStorage` or `sessionStorage`; any XSS reads them and there is no `HttpOnly` equivalent. For SPAs, the BFF pattern from the Browser-Based Apps BCP keeps tokens server-side and hands the browser only an `HttpOnly` session cookie.

## CSRF defense

CSRF matters precisely when the browser sends the credential automatically, which is exactly the cookie case above. Token-in-header auth (`Authorization: Bearer`) read from JS is not CSRF-exploitable but trades the risk for XSS token theft. Pick one model and defend it.

Layered defense for cookie-based sessions:

1. Primary token. Stateful apps use the synchronizer token pattern (a per-session, random token stored server-side, rendered into forms, checked on every state-changing request). Stateless apps use the **signed** double-submit cookie: the token is `HMAC(secret, session_id + random)`, sent both as a cookie and echoed in a header/field; the server recomputes the HMAC and verifies it binds to the current session. Plain (unsigned) double-submit is weaker because an attacker who can set a cookie on a subdomain can forge it; binding to the session id closes that.
2. SameSite as defense-in-depth only. `SameSite=Lax/Strict` reduces exposure but does not replace the token; it must co-exist with it.
3. For JSON APIs, require a custom request header (for example `X-CSRF-Token`). A cross-site attacker cannot set custom headers without a CORS preflight you control, so this alone is a strong defense for non-simple requests.
4. Never make state-changing operations available over `GET`. Never reflect an arbitrary `Origin` with `Access-Control-Allow-Credentials: true`.

Signed double-submit token, generation and constant-time verification:

```python
import hmac, hashlib, secrets

def issue_csrf(session_id: str, secret: bytes) -> str:
    rand = secrets.token_urlsafe(16)
    msg = f"{session_id}!{rand}".encode()
    sig = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    return f"{rand}.{sig}"            # set as a readable cookie AND echoed in a header

def valid_csrf(token: str, session_id: str, secret: bytes) -> bool:
    try:
        rand, sig = token.split(".", 1)
    except ValueError:
        return False
    expected = hmac.new(secret, f"{session_id}!{rand}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)   # constant-time
```

Pitfalls: comparing tokens with `==` (timing leak; use `compare_digest`); a global static CSRF token reused across users; protecting only the HTML form route but leaving a JSON twin unprotected; relying on `Referer` checks alone (often stripped); assuming `SameSite` is enough on its own.

## Common pitfalls

- Reading `alg` from the JWT header to pick the verifier. This is the algorithm-confusion attack: an RS256 public key gets treated as an HS256 secret and the attacker signs their own tokens. Pin `algorithms` server-side, always.
- Accepting `alg: none` because the library default allows unverified decode, or calling `decode` where `verify` was meant. The token parses, claims load, and no signature was ever checked.
- Skipping the `aud` check. A token minted for another service verifies fine cryptographically; audience confusion is a privilege-escalation path, not a formality.
- Hours of `exp` leeway "for clock skew". Anything beyond 60 seconds is a replay window, not skew tolerance.
- Fetching JWKS on every request (self-inflicted DoS on the issuer and your own latency) or never refreshing it (key rotation becomes an outage). Cache with a TTL, refetch on unknown `kid`.
- Choosing JWT for first-party browser sessions and then discovering logout, password change, and admin kill cannot revoke anything until `exp`. Opaque server-side sessions are the default for a reason.
- Rotating the access token but reusing the refresh token, which removes the theft tripwire; or revoking only the presented refresh token on reuse instead of the whole family, which leaves the attacker holding the next link in the chain.
- Treating two near-simultaneous legitimate refreshes as theft with no grace window, logging users out at random under network retries.
- Storing refresh tokens or session ids in plaintext, so a database dump is a credential dump. Store hashes; compare in constant time.
- Access or refresh tokens in `localStorage`/`sessionStorage`. One XSS reads them all; there is no `HttpOnly` for web storage. Use the BFF pattern with an `HttpOnly` cookie.
- A fat JWT pushed into a cookie past the 4096-byte limit: the browser silently drops it and users report unexplainable logout loops.
- Session cookie without the `__Host-` prefix, so a compromised sibling subdomain can overwrite it (session fixation by cookie tossing).
- Relying on `SameSite=Lax` as the only CSRF defense, or shipping the synchronizer token on the form route while the JSON twin endpoint stays unprotected.
- Logging full bearer tokens in access logs or error traces. A token in a log is a live credential with your retention policy as its TTL.

## Definition of done

- [ ] Token type chosen deliberately: opaque/stateful for first-party sessions, short-lived JWT only where stateless multi-verifier validation is needed; rationale recorded in memory or an ADR.
- [ ] JWT verification pins `algorithms` to an explicit allowlist, rejects `none`, and never reads `alg` from the header to select the verifier.
- [ ] JWT validation checks signature, `iss`, `aud`, `exp`/`nbf`, requires the claims relied upon, and uses <= 60s clock leeway.
- [ ] JWKS is cached with a TTL and refreshed on unknown `kid`; no per-request fetch.
- [ ] Access tokens are short-lived (5 to 15 minutes); refresh tokens have both idle and absolute expiry.
- [ ] Refresh tokens rotate on every use, are stored only as hashes, and reuse of a used token revokes the entire family and emits a security event.
- [ ] Sender-constraining (DPoP or mTLS) applied where the API value justifies it.
- [ ] Session/token cookies set `HttpOnly`, `Secure`, an explicit `SameSite`, and use `__Host-`/`__Secure-` prefixes; size stays under 4096 bytes.
- [ ] No access or refresh tokens in `localStorage`/`sessionStorage`; SPAs use the BFF pattern.
- [ ] Cookie-based sessions carry a CSRF token (synchronizer or signed double-submit) plus `SameSite`; JSON APIs require a custom header; verification is constant-time; no state change over `GET`.
- [ ] Tokens are never logged; introspection/denylist paths exist for revocation and logout.
- [ ] Unit and integration tests cover the negative cases: `alg:none`, wrong `aud`, expired token, tampered signature, refresh reuse triggering family revocation, and a forged/missing CSRF token. External issuers and stores are mocked.
- [ ] Library versions verified: PyJWT `>= 2.x`, `jose` (current major) or `jsonwebtoken >= 9.0.0`, `golang-jwt/jwt/v5`; pinned, not floating to `latest`.
