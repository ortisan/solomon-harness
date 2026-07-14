---
name: oauth2-oidc
description: Governs OAuth 2.0 and OpenID Connect flow selection, token handling, and endpoint hardening, with authorization-code-plus-PKCE as the only flow shipped. Use when designing or reviewing login flows, token exchanges, or any integration with an identity provider.
---

# OAuth 2.0 and OpenID Connect

Purpose: a concrete, checkable playbook for implementing browser, mobile, and service authentication with OAuth 2.0 and OpenID Connect (OIDC). Scope: Authorization Code with PKCE as the only flow you ship, token validation, scope and audience design, and why implicit and password (ROPC) grants are off the table.

## When this applies

Apply this on any feature that signs a user in, calls a protected API on a user's behalf, integrates a social or enterprise IdP (Google, GitHub, Apple, Microsoft Entra ID, Okta, Keycloak), or validates an incoming bearer token. Threat-model the flow before code, validate every token claim before trust, and hand security-sensitive token-handling changes to the security specialist for review.

## Standards and versions you build against

OAuth 2.0 is authorization (delegated access to APIs). OIDC is the identity layer on top of it (who the user is, returned as an `id_token`). They are different jobs; an access token is not proof of authentication. Use OIDC when you need to know who the user is.

- RFC 6749 / RFC 6750 — OAuth 2.0 core and bearer token usage. Still the base, but read it through the lens of the BCP below, which overrides several of its original allowances.
- RFC 9700 (January 2025) — OAuth 2.0 Security Best Current Practice. This is the document to follow. It is the RFC form of the long-running OAuth security-topics work and supersedes RFC 6819's threat-model advice: PKCE for all clients, exact redirect-URI matching, no implicit, no ROPC, sender-constrained tokens, narrow scopes and audiences.
- RFC 7636 — PKCE. RFC 8252 — OAuth for Native Apps (system browser, not an embedded WebView). RFC 9068 — JWT profile for access tokens. RFC 7662 — token introspection (opaque tokens). RFC 9126 — Pushed Authorization Requests (PAR). RFC 9101 — JWT-Secured Authorization Request (JAR). RFC 8707 — Resource Indicators. RFC 9449 — DPoP. RFC 8705 — mTLS / certificate-bound tokens.
- OpenID Connect Core 1.0 — the `id_token`, `nonce`, `at_hash`, discovery, and claim rules.
- OAuth 2.1 (`draft-ietf-oauth-v2-1`) — still an IETF draft in early 2026, not a ratified RFC. Do not cite it as a finished standard. Its substance is already actionable because it consolidates RFC 9700: Authorization Code + PKCE as the single grant, implicit and ROPC removed. Okta, Auth0, Microsoft Entra ID, and Spring Security 6 already enforce these defaults. Build to it now.

## Authorization Code with PKCE: the only flow you ship

PKCE (RFC 7636) binds the authorization code to the client that started the flow, so a code intercepted on the redirect (mobile custom-scheme hijack, browser history, proxy log) is useless without the verifier. RFC 9700 requires PKCE for every client type, public and confidential. A confidential client still uses PKCE; the client secret and PKCE protect against different attacks (client authentication vs. code interception), so you need both.

Generate the verifier and challenge with a CSPRNG. Verifier is 43-128 chars from the unreserved set `[A-Za-z0-9-._~]`; 32 random bytes base64url-encoded gives the right length and entropy. Only ever use `S256`; never the `plain` method.

```python
import secrets, hashlib, base64

def pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge
# /authorize carries code_challenge + code_challenge_method=S256
# keep the verifier server-side, bound to the state/session; send it on /token
```

The flow:

1. Client builds `/authorize` with `response_type=code`, `client_id`, exact `redirect_uri`, `scope` (include `openid` for OIDC), `state` (CSRF binding, single-use, high entropy), `nonce` (OIDC replay binding, single-use), `code_challenge`, `code_challenge_method=S256`. Redirect the user's browser there.
2. Optional hardening: send these parameters through PAR (RFC 9126) so they never appear in the front-channel URL; the AS returns a `request_uri` you reference. JAR (RFC 9101) signs the request object. FAPI 2.0 deployments require PAR.
3. User authenticates and consents at the IdP. IdP redirects back to `redirect_uri` with `code` and the echoed `state`.
4. Client verifies `state` matches the stored value, then POSTs to `/token` with `grant_type=authorization_code`, `code`, `redirect_uri`, `client_id`, `code_verifier`, and client authentication if confidential.
5. AS verifies the verifier hashes to the stored challenge and returns `access_token`, `id_token` (OIDC), and usually a `refresh_token`. Validate the `id_token` before trusting anything (next section).

Non-negotiables on the flow:

- Exact redirect-URI matching, character for character, including scheme, host, port, path, and query. No wildcards, no substring or prefix matching, no open path segments. Open-redirect and mismatched-URI bugs are the most common way codes and tokens leak.
- `state` and `nonce` are independent and both required: `state` defends the callback against CSRF; `nonce` binds the `id_token` to this specific authorization request and defends against token replay.
- Authorization code is single-use and short-lived. RFC 6749 caps it at 10 minutes; keep it under 60 seconds and reject any reuse. A second redemption of a code must revoke the tokens already issued for it.
- Mitigate the PKCE downgrade attack: the AS must accept a `code_verifier` on `/token` only if a `code_challenge` was present on `/authorize`. This is the IdP's job, but verify your IdP enforces it before trusting its PKCE support.

### Native and mobile apps (RFC 8252)

Use the system browser (ASWebAuthenticationSession on iOS, Custom Tabs on Android) through AppAuth-iOS / AppAuth-Android, never an embedded WebView, which can read the user's IdP credentials and breaks SSO. Public clients have no secret, so PKCE is the entire protection on the code exchange. Prefer claimed HTTPS redirects (universal links / App Links) over custom schemes, which other apps can register and hijack.

### Browser SPAs: stop putting tokens in JavaScript

A token reachable from JavaScript is reachable from any XSS on the page; `localStorage` is the worst place for it. Preferred pattern is Backend-for-Frontend (BFF): a server-side confidential client runs the Authorization Code + PKCE flow, keeps the tokens server-side, and hands the browser only a hardened session cookie (`HttpOnly`, `Secure`, `SameSite=Lax` or `Strict`). The SPA calls its own backend, which attaches the access token. If you must hold tokens in the SPA, keep access-token lifetime in minutes, never store a refresh token in the browser without rotation, and treat any XSS as a full token compromise.

## Token validation: never trust an unvalidated token

A bearer token is a claim, not a fact, until you verify it. There are two shapes:

- JWT access tokens (RFC 9068) and OIDC `id_token`s — self-contained, signed; validate locally against the issuer's JWKS.
- Opaque access tokens — validate by calling the IdP's introspection endpoint (RFC 7662, returns `active: true/false` plus claims). Opaque tokens give the IdP central revocation at the cost of a network call; cache the result for a few seconds at most.

### Validating an OIDC id_token (OIDC Core 3.1.3.7)

Check all of these; a library that does not do them by default should be replaced:

1. Signature against the issuer's JWKS key selected by `kid` from `jwks_uri` (discovered via `/.well-known/openid-configuration`).
2. `alg` is the one you expect (the IdP's registered `id_token_signed_response_alg`, normally `RS256` or `ES256`). Pin it explicitly.
3. `iss` exactly equals the issuer string from discovery.
4. `aud` contains your `client_id`. If `aud` has multiple values or an `azp` is present, `azp` must equal your `client_id`. Reject tokens minted for another audience.
5. `exp` is in the future and `iat`/`nbf` are sane, allowing at most 60 seconds of clock skew.
6. `nonce` equals the value you sent on `/authorize`.
7. `at_hash` matches the access token when present: hash the ASCII `access_token` with the hash tied to the `id_token`'s signing alg (SHA-256 for `RS256`/`ES256`), take the left-most half (128 bits for SHA-256), base64url-encode, compare. Validate `c_hash` the same way against the code in flows that return it. Check `auth_time`, `acr`, `amr` when you requested a specific authentication strength.

### The signature attacks you must close

These are the high-severity failures; the fix for all of them is the same one line of config: pin the algorithm allowlist and verify the key type matches.

- `alg: none` — attacker strips the signature and sets `alg` to `none`. Any verifier that honors that header accepts a forged token. Never accept `none`.
- RS256 -> HS256 confusion — attacker takes the server's public RSA key (it is public), signs a forged token with HMAC-SHA256 using that public key as the HMAC secret, and sets `alg: HS256`. A verifier with one code path that feeds the same key material to both asymmetric verify and symmetric verify accepts it. Pin `algorithms=["RS256"]` (or your real asymmetric alg) so an HS256 token is rejected before any key is loaded. Never read the algorithm from the token header to decide how to verify.

PyJWT 2.x (current 2.10.x) with JWKS — pin the alg, set the audience and issuer explicitly (PyJWT silently skips the `aud` check if you omit `audience`), require the critical claims:

```python
import jwt
from jwt import PyJWKClient

# PyJWKClient caches keys; lifespan is seconds (default 300).
jwks = PyJWKClient("https://issuer.example.com/.well-known/jwks.json", lifespan=300)
signing_key = jwks.get_signing_key_from_jwt(token)

claims = jwt.decode(
    token,
    signing_key.key,
    algorithms=["RS256"],                 # pin: never derive from the header
    audience="my-api",                    # required; omission disables the aud check
    issuer="https://issuer.example.com",
    leeway=60,                            # max clock skew, seconds
    options={"require": ["exp", "iat", "iss", "aud"]},
)
```

Authlib 1.6.x is the fuller option in Python: its OIDC client integration runs `id_token` validation (`nonce`, `at_hash`, `iss`, `aud`) for you, and `authlib.jose` handles JWKS. Prefer the framework client over hand-rolling the front-channel.

Node — `jose` (panva, v5+) for raw JWT validation; `openid-client` (v6, ESM-only, rebuilt on `oauth4webapi`) for the full OIDC client with discovery, PKCE, `state`, `nonce`, and `id_token` validation built in. Pin algorithms here too:

```js
import * as jose from 'jose'

const JWKS = jose.createRemoteJWKSet(
  new URL('https://issuer.example.com/.well-known/jwks.json')
)

const { payload } = await jose.jwtVerify(token, JWKS, {
  issuer: 'https://issuer.example.com',
  audience: 'my-api',
  algorithms: ['RS256'],        // reject none and HS* downgrade
  clockTolerance: 60,
})
```

Spring Security 6 (`spring-boot-starter-oauth2-resource-server`) validates issuer, signature, and expiry from `issuer-uri` config out of the box; audience is not checked by default, so add a custom `OAuth2TokenValidator` for it. It dropped implicit and ROPC support, matching OAuth 2.1.

Operational rules for validation: cache JWKS but honor `kid` rotation (refetch on an unknown `kid`, with a rate limit so a bogus `kid` cannot become a DoS against the JWKS endpoint); do not pin a single key; treat a missing or unexpected `kid` as a validation failure, not a fallback to "try all keys."

## Scopes and audience: least privilege for tokens

A scope is the permission a token carries; the audience (`aud`) is the API the token is for. Design both narrow.

- Default to deny. Request only the scopes a feature needs, not a broad superset "to be safe." OIDC base scopes: `openid` (required to get an `id_token`), `profile`, `email`, `address`, `phone`; each maps to a defined claim set.
- Make custom API scopes resource-specific and verb-specific (`orders:read`, `orders:write`) rather than coarse (`api`, `full_access`). Enforce the scope at the resource server on every endpoint; never assume the presence of a token implies authorization for the action.
- Use Resource Indicators (RFC 8707, `resource` parameter) so the AS mints an access token whose `aud` is the specific API. An access token for API A must be rejected by API B. This is the defense against a token leaked from one service being replayed against another.
- Scopes are coarse authorization, not your authorization model. Keep RBAC/ABAC decisions in policy (OPA/Rego, deny-by-default) and use scopes to bound what a client may ask for. Do not encode fine-grained per-record permissions as scopes.

## Token lifetimes, refresh rotation, and sender-constraining

- Access tokens: short-lived. Aim for 5-15 minutes. The shorter the window, the less a stolen token is worth. Do not stretch lifetime to avoid refreshes; rotate instead.
- Refresh tokens: rotate on every use with reuse detection. When a refresh token is presented twice, the AS revokes the entire token family and forces re-authentication; a replayed (stolen) refresh token then locks the thief and the victim out, surfacing the theft. Public clients must use rotation, sender-constraining, or both.
- Sender-constrained access tokens (RFC 9700 recommendation) bind the token to a key the client must prove it holds, so a leaked bearer token alone is useless:
  - DPoP (RFC 9449): the client signs a per-request proof JWT with its private key in the `DPoP` header; the access token carries `cnf.jkt` (the JWK thumbprint). Lightweight, no PKI, good fit for SPAs and mobile.
  - mTLS (RFC 8705): the token is bound to the client's TLS client certificate via `cnf.x5t#S256`. Strong for service-to-service where you already run a PKI.
- Always offer revocation (RFC 7009) and call it on logout and on credential change. For `id_token`-driven sessions, support OIDC back-channel logout so IdP-side session termination propagates.

## The dangers of implicit and password grants

Both are removed in OAuth 2.1 and called out against in RFC 9700. Do not implement either; if an existing integration uses one, migrate it to Authorization Code + PKCE.

Implicit grant (`response_type=token`): the AS returns the access token directly in the URL fragment after the redirect. That token lands in browser history, the `Referer` header on the next navigation, server and proxy access logs, and is readable by any script on the page. There is no code exchange, so there is no place to apply PKCE, no client authentication, and no clean way to deliver a refresh token. It existed as a workaround for browsers without CORS; that constraint is gone. Authorization Code + PKCE replaces it for SPAs with no downside.

Resource Owner Password Credentials (ROPC, `grant_type=password`): the application collects the user's IdP username and password directly and sends them to the token endpoint. This trains users to type their credentials into non-IdP surfaces (the exact habit phishing exploits), it cannot do MFA, federated/social login, or step-up, the client necessarily handles plaintext credentials, and it defeats the entire reason OAuth delegates authentication to the IdP. The only narrow, legacy excuse was a first-party app against your own IdP, and even that is now replaced by Authorization Code + PKCE in a system browser. Treat any ROPC use as a finding.

## Tooling and IdPs

- Identity providers / authorization servers: Keycloak (self-hosted, full OIDC + RFC 9700 features, supports PAR/DPoP), Auth0, Okta, Microsoft Entra ID, Google. All support Authorization Code + PKCE and discovery; confirm your provider enforces PKCE-downgrade protection and exact redirect matching.
- Python clients/validators: Authlib 1.6.x (full OIDC client and JOSE), PyJWT 2.x (JWT/JWKS validation). Avoid `python-jose`, which has had algorithm-handling CVEs and is less actively maintained.
- Node: `openid-client` v6 (full client), `jose` v5+ (validation). On legacy code using `jsonwebtoken` + `jwks-rsa`, audit that `algorithms` is pinned.
- JVM: Spring Security 6.x resource server and client; Nimbus JOSE + JWT for raw validation.
- Mobile: AppAuth-iOS / AppAuth-Android (RFC 8252, system browser, PKCE built in).

## Common pitfalls

- Skipping the `aud` check because the library makes it optional, so any valid token from the issuer is accepted regardless of which API it was minted for.
- Reading `alg` from the token header to choose the verification path, leaving `alg: none` and RS256->HS256 confusion open.
- Wildcard or prefix redirect-URI matching, or registering a broad `redirect_uri`, opening code/token exfiltration via open redirect.
- Treating an access token as proof of who the user is (it is not) instead of validating an `id_token`, or trusting `id_token` claims for API authorization (it is for authentication, not for calling APIs).
- Validating `state` but not `nonce` (or vice versa), leaving CSRF or `id_token` replay open.
- Storing access or refresh tokens in browser `localStorage`/`sessionStorage` where XSS reads them, instead of a BFF session cookie.
- Long-lived access tokens (hours) "to reduce refresh traffic," widening the stolen-token window, with no rotation or revocation.
- Refresh tokens without rotation and reuse detection, so a stolen refresh token mints tokens indefinitely and silently.
- Pinning the JWKS to a single static key, breaking on key rotation; or refetching JWKS on every request and creating a DoS dependency on the IdP.
- Embedded WebView login in mobile apps, which can scrape IdP credentials and breaks SSO.
- Reusing one coarse scope (`api`, `full_access`) everywhere instead of resource- and verb-scoped permissions enforced at the endpoint.

## Definition of done

- [ ] Authorization Code with PKCE (`S256`) is the only flow; no implicit, no ROPC anywhere in the codebase.
- [ ] PKCE verifier is 32 CSPRNG bytes (43-128 chars), the challenge is `S256`, and the verifier is bound server-side to the request; `plain` is never used.
- [ ] `state` and `nonce` are both generated, single-use, high-entropy, and checked on callback.
- [ ] Redirect URIs are pre-registered and matched exactly (scheme, host, port, path, query); no wildcards.
- [ ] Authorization code is single-use and under 60 seconds; reuse revokes issued tokens; the IdP enforces PKCE-downgrade protection.
- [ ] Every `id_token` is validated for signature (JWKS by `kid`), pinned `alg`, `iss`, `aud`/`azp`, `exp`/`iat` with <=60s skew, `nonce`, and `at_hash`/`c_hash` when present.
- [ ] Access tokens are validated against the JWKS (JWT) or introspection (opaque); `algorithms` is pinned so `alg: none` and HS256 downgrade are rejected; `aud` is checked against this resource server.
- [ ] Scopes are narrow and verb/resource-specific, enforced at every endpoint; access-token `aud` is scoped per API via resource indicators; authorization decisions live in policy, not in scope presence.
- [ ] Access tokens are 5-15 minutes; refresh tokens rotate with reuse detection that revokes the family; revocation and logout are wired.
- [ ] SPAs use a BFF with `HttpOnly`/`Secure`/`SameSite` cookies, or sender-constrained short-lived tokens; no tokens in `localStorage`. Native apps use the system browser via AppAuth.
- [ ] Sender-constraining (DPoP or mTLS) is applied where token theft risk warrants it.
- [ ] Token-validation logic has unit tests covering tampered signature, `alg: none`, wrong `aud`, wrong `iss`, expired token, and bad `nonce`; all external IdP/JWKS calls are mocked.
- [ ] Flow design and token-lifetime decisions are recorded in PLAN.md and project memory, and security-sensitive changes are handed to the security specialist for review.
