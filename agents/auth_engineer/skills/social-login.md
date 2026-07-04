# Social login over OIDC

Scope: federated sign-in with Google, GitHub, Apple, Microsoft (Entra ID), and Facebook (Meta). Goal is one canonical user identity, safe account linking, and correct email-verification handling. Every flow is Authorization Code + PKCE; implicit and hybrid flows are out.

This skill assumes the role's baseline: Authorization Code with PKCE (S256), short-lived access tokens, `iss`/`aud`/`exp`/signature checks on every JWT, and `HttpOnly`/`Secure`/`SameSite` cookies.

## Ground rules for every provider

These are non-negotiable regardless of library:

- Use Authorization Code flow with PKCE `code_challenge_method=S256`. PKCE is mandatory in OAuth 2.1 and is now required by several providers for public clients. Generate a fresh verifier per request.
- Send and verify `state` (CSRF) and `nonce` (replay) on every request. `nonce` goes into the auth request and must equal the `nonce` claim in the returned `id_token`.
- Validate the `id_token` against the provider JWKS: signature, `iss` exact match, `aud` equals your client_id, `exp`/`iat`/`nbf` within skew (allow <= 60s clock skew, reject otherwise). Cache JWKS with the provider's `Cache-Control`; refetch on unknown `kid`.
- `redirect_uri` is an exact, pre-registered, absolute HTTPS URL. No wildcards, no path-relative redirects, no user-controlled `returnTo` echoed into `redirect_uri`. Validate any post-login `returnTo` against an allowlist to avoid open redirect.
- Identity key is `(provider, provider_subject)`, never the email. `provider_subject` is `sub` for Google/Apple/Facebook-OIDC, `oid` (+`tid`) for Microsoft, and the numeric `id` for GitHub. Emails are mutable and reusable; do not key accounts on them.
- Gate account creation/linking on a verified email. Each provider asserts verification differently (matrix below). Treat "unknown" as "unverified".

## Identity model and account linking

Minimum schema (two tables, one unique constraint that does the real work):

```sql
CREATE TABLE users (
  id            uuid PRIMARY KEY,
  email         citext,                 -- display/contact only, not an identity key
  email_verified boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE accounts (
  id                  uuid PRIMARY KEY,
  user_id             uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider            text NOT NULL,    -- 'google' | 'github' | 'apple' | 'microsoft' | 'facebook'
  provider_account_id text NOT NULL,    -- sub / oid / github id
  UNIQUE (provider, provider_account_id)
);
```

Linking decision on each social sign-in:

1. Look up `accounts` by `(provider, provider_account_id)`. Hit means returning user, sign in. Done.
2. No account row. Read the provider email and its verification flag.
3. If the provider-verified email matches an existing `users.email` that is itself verified, and the provider is one you trust to verify email (Google, Apple, Microsoft work/school with verified-domain claim), auto-link by inserting a new `accounts` row for the existing `user_id`.
4. Otherwise create a new user, or require an explicit, authenticated linking step (user signs into the existing account first, then connects the new provider). Never auto-link on an unverified or absent email.

The dangerous default to understand: Auth.js exposes `allowDangerousEmailAccountLinking: true`, which links any new provider to an existing user that shares the same email, with no proof the new provider verified it. Enable it only per-provider and only for providers you trust to verify email (Google, Apple). Leave it off for GitHub and Facebook, where an attacker can register an account with your victim's email and silently take over. The named risk is "pre-account-takeover" / email-collision linking.

## Google

OIDC-compliant. Discovery at `https://accounts.google.com/.well-known/openid-configuration`. `id_token` carries `sub`, `email`, `email_verified`, and `hd` (Workspace hosted domain).

Pitfalls:
- `email_verified` is reliable; gate on it. For a normal Gmail/Workspace user it is `true`. Reject sign-in when it is `false`.
- Domain restriction: if you allow only a Workspace domain, check the signed `hd` claim, not the `email` suffix. `hd` is in the `id_token`; an email suffix can be spoofed by a self-hosted IdP if you ever accept one. Pass `hd=yourdomain.com` in the auth request to pre-filter the account chooser, but still verify the claim server-side.
- Refresh tokens are returned only when you send `access_type=offline` and `prompt=consent`; without `prompt=consent` a second consent returns no refresh token. Only request offline access if you actually call Google APIs later; pure login does not need it.
- Add `prompt=select_account` so users on shared machines do not get silently logged in as the wrong account.
- Key on `sub`. It is stable per Google account; `email` can change.

## GitHub

Not an OIDC provider for user login. OAuth 2.0 only, no `id_token`, no `nonce`. You get an opaque access token and call the REST API. Security rests on `state` plus the token exchange.

Pitfalls:
- `GET /user` returns `email: null` for the many users who keep their email private, even with the `user:email` scope. Do not assume `/user.email` is present and do not mark it verified. This breaks sign-in for valid users and, worse, leads to linking on an unverified address.
- Always call `GET /user/emails` and pick the entry with `primary: true` and `verified: true`. If none is verified, refuse to create or link an account.

```python
emails = (await client.get("https://api.github.com/user/emails")).json()
primary = next((e for e in emails if e["primary"] and e["verified"]), None)
if primary is None:
    raise PermissionError("GitHub account has no verified primary email")
email = primary["email"]
```

- Request `scope=read:user user:email`. GitHub Apps (as opposed to classic OAuth Apps) use the account-level "Email addresses" permission rather than this scope; pick the app type whose email access you can actually grant.
- Org SAML SSO can block API access with an authorized token until the user authorizes the token for that org. Handle the `403` and surface a clear message.
- Key on the numeric `id`, never the `login` (username), which users can rename and which can be recycled.

## Microsoft (Entra ID, formerly Azure AD)

OIDC-compliant. Use the v2.0 endpoints. Discovery is per-authority: `https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration`, where `{tenant}` is a tenant GUID, `organizations`, `consumers`, or `common`.

Pitfalls:
- The `common`/`organizations` authority accepts users from any Entra tenant. If you do not validate the tenant, anyone with any Microsoft work account signs into your app. For a single-org app, use the tenant GUID authority. For multi-tenant, validate `tid` against an allowlist and validate `iss` matches `https://login.microsoftonline.com/{tid}/v2.0` for that specific `tid` (the discovery `issuer` for `common` is templated and will not match a static string).
- `sub` is pairwise: unique per (app, tenant, user) and differs between your apps. Do not use it as a portable user key. Use `oid` (object id, stable for the user in a tenant) combined with `tid`. Store `oid+tid`.
- There is no general `email_verified` claim for work/school accounts. `email` is present only if the user has a mailbox attribute set, and `preferred_username` is often a UPN that may not be a real or verified mailbox (especially for guests/B2B). Matching accounts on the `email`/`preferred_username` claim is exactly the nOAuth attack class: an attacker sets an unverified email on their own tenant to your victim's address and takes over the cross-tenant account. Key on `oid+tid` and require the optional claim `xms_edov` ("email domain owner verified", a boolean signaling the tenant owns the email domain) to be `true` before trusting any org email for linking. Note the Azure portal token-configuration UI may not list `xms_edov`; set it via Graph if needed.
- Request the v2.0 token version. v1.0 tokens use different claim names (`upn`, no `email` by default) and will surprise you.

## Apple (Sign in with Apple)

OIDC-ish. `id_token` is a real OIDC token (`sub`, `email`, `email_verified`, `is_private_email`), but several behaviors are Apple-specific and cause most production incidents.

Pitfalls:
- Name and email are returned only on the user's first authorization, and the name arrives in a one-time `user` form field, not in the `id_token`. Persist `email`/`name` on that first callback. Later sign-ins omit them. To re-trigger first-auth, the user must remove the app at appleid.apple.com.
- Because you request `name email` scope, Apple uses `response_mode=form_post`: the callback is a top-level cross-site `POST`. A `state` cookie set `SameSite=Lax` or `Strict` is not sent on that POST and the flow fails intermittently across browsers. Set the state cookie `SameSite=None; Secure` for the Apple callback (Auth.js handles this for you; raw Authlib does not).
- `client_secret` is a JWT you sign with your `.p8` key using ES256. Apple rejects any `exp` more than 6 months out (`15777000s`). Use ~180 days, generate at boot, cache it, and refresh before expiry. Claims: `iss`=Team ID, `sub`=Services ID (your client_id), `aud`=`https://appleid.apple.com`, `iat`, `exp`, header `kid`=key id, `alg`=ES256.

```ts
import { SignJWT, importPKCS8 } from "jose"

export async function appleClientSecret() {
  const key = await importPKCS8(process.env.APPLE_PRIVATE_KEY!, "ES256")
  return new SignJWT({})
    .setProtectedHeader({ alg: "ES256", kid: process.env.APPLE_KEY_ID! })
    .setIssuer(process.env.APPLE_TEAM_ID!)        // Team ID
    .setSubject(process.env.APPLE_CLIENT_ID!)     // Services ID (web) — NOT the bundle id
    .setAudience("https://appleid.apple.com")
    .setIssuedAt()
    .setExpirationTime("180d")                    // <= 6 months or Apple rejects it
    .sign(key)
}
```

- Private relay: with Hide My Email the address is `*@privaterelay.appleid.com` and `is_private_email` is `true`. Outbound mail to it bounces unless the sending domain/address is registered in Apple's private email relay service. Register your sender, or relay-addressed users never get your email.
- Token `iss` is `https://appleid.apple.com` regardless of the discovery host. Validate against that value, fetch the discovery/JWKS dynamically, and do not hardcode endpoint hosts.
- Two real 2025 incidents make Apple a single point of failure you must design around. In May 2025 Apple silently issued new `sub` values to a large share of users (reports put it near a third) and returned `null` for `email`, detaching returning users from their accounts; the original values came back only after Apple quietly reverted, roughly three months later. In June 2025 Apple briefly redirected its discovery endpoint to a host declaring a different issuer (`account.apple.com`) while tokens kept `iss=https://appleid.apple.com`, so strictly-compliant validators rejected valid tokens for about a day. Lessons: validate `iss` against the token's actual issuer, alert on sudden validation-failure spikes, and never make Apple a user's only identity anchor — always offer a second sign-in method and an authenticated account-recovery/linking path.
- Web vs native use different client_id values: web uses the Services ID, native apps authenticate against the App ID (bundle). The `id_token` `aud` differs accordingly. Validate the `aud` you actually expect for that platform.

## Facebook (Meta)

Two distinct flows; pick per platform and do not mix them:
- Classic Facebook Login: OAuth 2.0 + Graph API (web/Android). No `id_token`, no `email_verified`.
- Limited Login: OIDC `id_token` signed RS256, for iOS/ATT contexts. Validate via Meta's JWKS like any OIDC token.

Pitfalls:
- The `email` permission requires App Review before it works in production. Without it, you get no email at all. Even with it, users who signed up with a phone number have no email, so `email` can be absent for a fully valid user. Plan a no-email path.
- Facebook does not assert email verification on classic login. There is no `email_verified`. Treat the email as unverified; do not auto-link on it (`allowDangerousEmailAccountLinking` off).
- Graph API version is pinned in the URL (for example `v25.0`, current as of early 2026) and versions sunset on roughly a two-year cycle. Pin a version, monitor deprecations, and bump deliberately.
- Going live requires Business Verification and a working Data Deletion Request callback. Build the deletion callback early; it blocks launch.
- Key on the app-scoped `sub`/user id. It is app-scoped, so the same person has different ids across your apps.

## Email-verification matrix

| Provider | `id_token`? | email source | verification signal | trust for auto-link |
|---|---|---|---|---|
| Google | yes | `email` claim | `email_verified` claim | yes when `email_verified=true` |
| GitHub | no | `GET /user/emails` | per-address `verified` + `primary` | only the verified primary; otherwise no |
| Microsoft | yes (v2.0) | `email`/`preferred_username` | `xms_edov` for org domains; none generic | only with `xms_edov=true`; never on `preferred_username` alone |
| Apple | yes | `email` (first auth only) | `email_verified` (`true`/`"true"`) | yes, but watch `is_private_email` and `sub` rotation |
| Facebook | Limited Login only | `email` (needs review, may be absent) | none | no |

## Auth.js (NextAuth v5) — TypeScript

Use `next-auth@5` (`next-auth@beta`) on `@auth/core`. v5 is stricter about OIDC spec compliance than v4, which can break loosely-configured v4 providers. For OIDC providers prefer the built-in provider (it already sets `wellKnown`/`issuer`) and let it decode the `id_token` instead of an extra userinfo round trip.

```ts
// auth.ts
import NextAuth from "next-auth"
import Google from "next-auth/providers/google"
import GitHub from "next-auth/providers/github"
import Apple from "next-auth/providers/apple"
import MicrosoftEntraID from "next-auth/providers/microsoft-entra-id"
import Facebook from "next-auth/providers/facebook"
import { PrismaAdapter } from "@auth/prisma-adapter"
import { prisma } from "./db"
import { appleClientSecret } from "./apple"

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: PrismaAdapter(prisma),
  session: { strategy: "database" },
  providers: [
    Google({
      allowDangerousEmailAccountLinking: true,            // Google verifies email
      authorization: { params: { scope: "openid email profile", prompt: "select_account" } },
    }),
    GitHub({ allowDangerousEmailAccountLinking: false }), // never auto-link GitHub
    MicrosoftEntraID({
      // single-tenant authority; for multi-tenant validate tid yourself in signIn()
      issuer: `https://login.microsoftonline.com/${process.env.AUTH_MICROSOFT_ENTRA_ID_TENANT_ID}/v2.0`,
    }),
    Apple({ clientSecret: await appleClientSecret() }),   // rotate <= 6 months
    Facebook({ allowDangerousEmailAccountLinking: false }),
  ],
  callbacks: {
    async signIn({ account, profile }) {
      if (account?.provider === "google" && profile?.email_verified !== true) return false
      if (account?.provider === "microsoft-entra-id") {
        const allowed = (process.env.ALLOWED_TENANTS ?? "").split(",")
        if (!allowed.includes(profile?.tid as string)) return false
      }
      return true
    },
  },
})
```

Notes:
- Auth.js's GitHub provider already falls back to the emails endpoint to find a verified primary when `/user` returns no email; do not re-implement it, but keep `allowDangerousEmailAccountLinking` off because GitHub verification is per-address, not guaranteed.
- Environment variables follow `AUTH_<PROVIDER>_ID` / `AUTH_<PROVIDER>_SECRET` plus `AUTH_SECRET`. Set `trustHost: true` only behind a trusted proxy where you control the `Host` header.
- The Apple `clientSecret` is the JWT, not a static string. Regenerate it on a schedule; Apple rejects a stale or over-6-month token.

## Authlib — Python

Use Authlib `>=1.3` (current 1.6.x). The integration clients (`authlib.integrations.starlette_client` / `flask_client` / `httpx_client`) handle state, PKCE, nonce, and `id_token` validation when configured through `register(...)`.

```python
from authlib.integrations.starlette_client import OAuth

oauth = OAuth()

oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=GOOGLE_ID,
    client_secret=GOOGLE_SECRET,
    client_kwargs={
        "scope": "openid email profile",
        "code_challenge_method": "S256",   # enables PKCE
    },
)
```

Login and callback:

```python
async def login(request):
    redirect_uri = request.url_for("auth_callback")
    # stores state, nonce, and the PKCE verifier in the session
    return await oauth.google.authorize_redirect(request, redirect_uri)

async def auth_callback(request):
    # validates state, exchanges the code with PKCE, verifies the id_token signature and nonce
    token = await oauth.google.authorize_access_token(request)
    claims = token["userinfo"]                 # parsed, validated id_token claims
    if claims.get("email_verified") is not True:
        raise PermissionError("Provider did not verify the email")
    subject = claims["sub"]
    # upsert by (provider='google', provider_account_id=subject)
```

`authorize_access_token` returns the parsed `userinfo` (the validated `id_token` claims) only when a `nonce` was stored and an `id_token` was returned; it verifies the `nonce` for you. Do not skip this by parsing the token yourself.

GitHub is not OIDC, so register raw endpoints and resolve the email manually:

```python
oauth.register(
    name="github",
    client_id=GH_ID, client_secret=GH_SECRET,
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "read:user user:email"},
)

async def github_callback(request):
    token = await oauth.github.authorize_access_token(request)   # state-validated
    emails = (await oauth.github.get("user/emails", token=token)).json()
    primary = next((e for e in emails if e["primary"] and e["verified"]), None)
    if primary is None:
        raise PermissionError("No verified primary email on the GitHub account")
    email = primary["email"]
```

Microsoft multi-tenant needs an explicit tenant check, because the `common` discovery issuer is templated and Authlib's default `iss` check will not match a fixed string:

```python
oauth.register(
    name="microsoft",
    server_metadata_url="https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
    client_id=MS_ID, client_secret=MS_SECRET,
    client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
)

async def microsoft_callback(request):
    token = await oauth.microsoft.authorize_access_token(request)
    claims = token["userinfo"]
    if claims.get("tid") not in ALLOWED_TENANTS:
        raise PermissionError("Tenant not allowed")
    # also assert iss == f"https://login.microsoftonline.com/{claims['tid']}/v2.0"
    key = (claims["oid"], claims["tid"])       # stable identity, not sub
```

For Apple in Authlib, sign the `client_secret` JWT with the `.p8` key (ES256, `aud=https://appleid.apple.com`, `exp <= ~180d`) and set the Apple callback's state cookie `SameSite=None; Secure` because Apple posts the callback (`response_mode=form_post`).

## Testing (mandatory, mock everything external)

- Mock the provider discovery doc, JWKS, token endpoint, and userinfo/REST. Never hit real providers in tests. Sign test `id_token`s with a local key and serve a matching JWKS so signature validation runs against your fixtures.
- Cover the failure paths explicitly: tampered `state`, mismatched `nonce`, expired `id_token`, wrong `aud`, wrong `iss`, GitHub `/user.email = null` with an unverified primary, Microsoft `tid` outside the allowlist, Apple second-login with missing email, Facebook missing-email user.
- Cover the linking matrix: existing verified-email user + verified-email provider (auto-link), existing user + unverified provider email (must not link), and email collision attack (attacker registers victim's email on an untrusted provider, then the victim signs in — must not merge).
- Use TDD: write the rejecting test first (red), implement the guard (green), then refactor the provider adapter behind a single interface.

## Common pitfalls

- Keying user identity on email. Emails are mutable and reusable; the moment a user changes theirs at the provider, or a provider recycles an address, accounts merge or orphan. The key is `(provider, provider_subject)`, full stop.
- Auto-linking accounts on an email the provider never verified. Enabling `allowDangerousEmailAccountLinking` (or hand-rolling the equivalent) for GitHub or Facebook lets an attacker register the victim's email at that provider and take over the existing account — the pre-account-takeover class.
- Assuming `GET /user` on GitHub returns an email. It is `null` for private-email users even with the `user:email` scope; skipping `GET /user/emails` (verified + primary) breaks valid users or, worse, links on an unverified address.
- Leaving the Microsoft `common` authority unvalidated, so any Entra tenant signs in; or matching users on `email`/`preferred_username`, which is the nOAuth takeover exactly. Validate `tid` against an allowlist, key on `oid+tid`, and require `xms_edov` before trusting an org email.
- Treating Microsoft `sub` as a portable user key. It is pairwise per (app, tenant, user) and differs between your own apps; migrations built on it strand every user.
- Discarding Apple's first-auth `user` form field. Name and email arrive exactly once; if the first callback does not persist them, they are gone until the user removes the app at appleid.apple.com.
- Setting the state cookie `SameSite=Lax` for the Apple callback. Apple posts the callback (`response_mode=form_post` when `name email` scope is requested), so the cookie is not sent and the flow fails intermittently. It must be `SameSite=None; Secure`.
- Minting the Apple `client_secret` JWT with `exp` beyond six months (rejected), or generating it once at deploy time and letting it expire in production.
- Emailing `@privaterelay.appleid.com` addresses from an unregistered sender: the mail bounces silently and "we sent you a link" is a lie for every Hide My Email user.
- Making Apple (or any single provider) a user's only identity anchor. The 2025 `sub`-rotation and issuer-redirect incidents detached users from their accounts for weeks; always offer a second sign-in method and an authenticated recovery path.
- Echoing a user-supplied `returnTo` into the redirect target without an allowlist check — an open redirect that launders phishing through your own domain.
- Skipping `nonce` verification because "the library probably does it". Parsing the `id_token` yourself instead of the library's validated path drops the replay protection silently.
- Assuming Facebook users have an email. Phone-number signups have none, the `email` permission needs App Review, and no verification is asserted either way. A no-email path is mandatory, not an edge case.

## Definition of done

- [ ] Every provider uses Authorization Code + PKCE (S256); no implicit/hybrid flow remains.
- [ ] `state` and `nonce` are generated per request and verified on callback; `redirect_uri` is exact-match and pre-registered.
- [ ] Every `id_token` is validated for signature (provider JWKS), `iss`, `aud`==client_id, and `exp`/`iat` within <=60s skew.
- [ ] Identity is keyed on `(provider, subject)` — `sub` (Google/Apple/Facebook), `oid+tid` (Microsoft), numeric `id` (GitHub) — never on email.
- [ ] Account creation and linking are gated on a verified email per the matrix; `allowDangerousEmailAccountLinking` (or equivalent) is enabled only for Google/Apple and off for GitHub/Facebook.
- [ ] GitHub email comes from `/user/emails` (verified primary) with a hard failure when none is verified.
- [ ] Microsoft `tid` is validated against an allowlist and `iss` is checked per-tenant; `email`/`preferred_username` is never used for linking without `xms_edov=true`; multi-tenant `common` is not left unvalidated.
- [ ] Apple `client_secret` JWT is ES256, `aud=https://appleid.apple.com`, `exp <= 6 months`, auto-rotated; first-auth name/email are persisted; the Apple callback state cookie is `SameSite=None; Secure`; private-relay senders are registered; discovery/JWKS are fetched dynamically; a second login method and recovery path exist.
- [ ] Facebook handles the no-email user, treats email as unverified, pins a Graph API version, and ships the data-deletion callback.
- [ ] Tokens stored for API use are encrypted at rest; refresh tokens rotate with reuse detection; session cookies are `HttpOnly`/`Secure`/`SameSite`.
- [ ] Unit and integration tests mock all provider endpoints and cover the failure and linking-attack paths above; suite is green.
- [ ] Auth design decision and the per-provider linking policy are written to project memory and handed off for security review.
