# Enterprise SSO: SAML 2.0, OIDC, and SCIM

Scope: implementing and reviewing enterprise single sign-on as a Service Provider (SP) / Relying Party (RP). Covers protocol choice, SP-initiated vs IdP-initiated flows, SAML assertion and signature validation, the SAML attack classes that keep recurring, OIDC token validation, and SCIM 2.0 provisioning. The recurring theme: signature validation and the binding between a validated signature and the data you actually trust are where these systems break.

## Choose the protocol

- New integrations: prefer OIDC (Authorization Code + PKCE) when the IdP supports it. JSON/JWT is simpler to validate correctly than XML DSig, and the attack surface is narrower.
- SAML 2.0 is non-negotiable for many enterprise buyers (Okta, Entra ID/Azure AD, Ping, ADFS, OneLogin, Google Workspace). Support it, but treat the XML signature layer as the highest-risk code in your auth stack.
- Do not hand-roll either. Use a maintained, pinned library and keep it current. Most catastrophic SSO bypasses are library or configuration bugs, not protocol bugs.
- Run both protocols off one stable user identifier. The value SCIM provisions (`userName` / `externalId`) must equal the subject your SAML assertion or OIDC ID token carries at login. A mismatch here is the top cause of duplicate accounts and orphaned sessions.

## SAML message flows: SP-initiated vs IdP-initiated

Bindings: the AuthnRequest goes out over HTTP-Redirect (GET, deflate+base64) or HTTP-POST; the Response comes back over HTTP-POST (a self-submitting form to your ACS URL). Never accept a SAML Response over plain GET.

SP-initiated (default, prefer this):
1. SP generates an `AuthnRequest` with a unique `ID` and stores it (session-bound, short TTL).
2. IdP authenticates the user and POSTs a `Response` to the ACS URL.
3. SP requires `InResponseTo` on the assertion's `SubjectConfirmationData` and the `Response` to equal the stored request `ID`, then consumes the request ID once.

`InResponseTo` gives you request/response correlation and replay binding for free. This is why SP-initiated is the safer default.

IdP-initiated (enable only when a customer requires it):
- There is no `AuthnRequest`, so there is no `InResponseTo` to bind against. The attack surface is materially wider — it is effectively login CSRF by design, and a captured Response is replayable anywhere the same SP trusts that IdP.
- If you must support it: keep it behind a per-tenant flag (default off), reject any assertion carrying an `InResponseTo` (it must be absent in this flow, present in SP-initiated), and rely on `Assertion/@ID` plus `AuthnStatement/@SessionIndex` caching for replay protection. Cache consumed IDs for at least the assertion validity window plus clock skew.
- pysaml2 `allow_unsolicited` and python3-saml's acceptance of unsolicited responses are exactly this switch. Keep them off unless required.

## SAML assertion validation: the ordered checklist

Validate in this order and reject on the first failure. Order matters — parse and schema-check before you trust anything, verify the signature before you read claims, and read claims only from the node the signature actually covered.

1. Transport: Response arrived over TLS 1.2+ via HTTP-POST to the exact ACS URL.
2. Schema-validate the XML against local, trusted SAML XSDs. Disable DTDs and external entity resolution (XXE). Never fetch schemas at runtime.
3. Reject documents where more than one element shares the same `ID` value. This single check kills a large family of signature-wrapping variants.
4. Verify the XML signature with the IdP signing key taken from pinned metadata — not from the `KeyInfo` in the message. Confirm the `ds:Reference URI` resolves to the `Assertion` (or `Response`) element you will actually read, and that the signed node is that exact node, not a sibling or wrapper.
5. Require the signature on the assertion. A signed `Response` wrapping an unsigned `Assertion` is not sufficient if you read identity from the assertion. Set `wantAssertionsSigned`. Do not accept "response-or-assertion signed."
6. Reject SHA-1 (`rsa-sha1`, digest `sha1`) per NIST SP 800-131A Rev. 2. Require RSA-SHA-256 or stronger (ECDSA-SHA-256 acceptable). Pin the expected `SignatureMethod`/`DigestMethod`.
7. `Issuer` matches the configured IdP EntityID.
8. `Conditions`: current time is within `NotBefore` and `NotOnOrAfter` with a small clock-skew allowance (60s typical, 180s hard ceiling).
9. `AudienceRestriction/Audience` equals your SP EntityID exactly.
10. `Subject/SubjectConfirmationData`: `Recipient` equals the ACS URL, `NotOnOrAfter` is in the future, and `InResponseTo` matches your stored request ID (SP-initiated) or is absent (IdP-initiated).
11. `Destination` on the `Response`, when present, equals the ACS URL.
12. Replay: the `Assertion/@ID` has not been seen. Cache consumed IDs until `NotOnOrAfter` + skew. Honor `OneTimeUse` if present.
13. Only now read `NameID` and attributes — exclusively from the signed, validated assertion node. Do not re-query the document by tag name or XPath after validation.

Thresholds: assertion lifetime should be short (~5 min from the IdP); reject anything with a multi-hour `NotOnOrAfter`. Clock skew tolerance 60s, never above 180s.

## XML signature verification: the rules that actually matter

- Get the key from pinned IdP metadata. Ignore `KeyInfo`/embedded certs in the incoming message; they are attacker-controlled.
- Pin the full X.509 certificate (or its public key), not a fingerprint. SHA-1 fingerprints are subject to collision and have been used to bypass validation; a fingerprint also tells you nothing about the rest of the cert.
- Never locate the signed element with `getElementsByTagName` or an absolute, position-based XPath. Resolve by the signature's `Reference URI` and confirm exactly one element matches that ID. This is the precise bug behind the ruby-saml and samlify bypasses below.
- After verification, operate on the exact validated DOM node object. Re-selecting "the assertion" from the document is how wrapping attacks land even when the signature check passed.
- Support IdP key rollover: accept multiple signing certs from metadata simultaneously and pick by the signature, so you can rotate without an outage.

## Known SAML vulnerability classes and CVEs

- XML Signature Wrapping (XSW): attacker keeps a validly signed blob and injects a second, unsigned assertion (often impersonating an admin) that the parser reads instead. Mitigations: steps 3, 4, and 13 above. This class has recurred for over a decade across many libraries.
- Signature exclusion: SP accepts an assertion with no signature at all. Require a signature to be present and verified; do not treat "no signature" as "valid."
- Signature confusion: only the `Response` is signed but identity is read from an unsigned child `Assertion`. Require assertion-level signatures.
- XML canonicalization / comment-truncation (the 2018 "GitHub/Duo/Shibboleth" class): a comment injected into a text node (`admin<!---->@evil.com`) makes the canonicalizer and the application read different NameID strings. Mitigation: use a library that extracts NameID from canonicalized output, and keep it patched.
- Certificate fingerprint collision: see above; pin the full cert.
- Replay and audience/recipient confusion: covered by steps 8-12.
- XXE / DTD: disable entity expansion and DTDs in the XML parser.
- CVE-2024-45409 (ruby-saml, CVSS 9.8): affected versions (up to 1.12.2, and 1.13.0 through 1.16.0) verified the response signature with an absolute XPath (`//ds:Reference` instead of `./ds:Reference`) and did not confirm that exactly one element matched the signed `ID`, so a forged Response/Assertion could ride on any one legitimately signed document. Drove the GitLab auth-bypass advisory. Fixed in 1.17.0 (and 1.12.3 on the legacy branch). Pin >= 1.18 to also clear the 2025 ruby-saml wrapping CVEs (CVE-2025-25291/25292).
- CVE-2025-47949 (samlify, Node): CVSS 9.9. The signature verified, but parsing read identity from an injected unsigned assertion — textbook XSW, full admin impersonation from one signed document. Fixed in 2.10.0. Upgrade immediately.

The pattern across all of these: "signature is valid" and "the data I read was signed" are different statements. Your code must guarantee the second.

## Library notes

### pysaml2 (IdentityPython, Python)

- Current 7.x line. Requires the `xmlsec1` binary. Note: xmlsec1 1.3.0 introduced breaking changes that surface as "key not found" signing failures — pin a known-good xmlsec1 and test the binary in CI, not just the Python package.
- `want_assertions_signed` defaults to False historically. Set it explicitly. Do not weaken to `want_assertions_or_response_signed`.

```python
from saml2 import BINDING_HTTP_POST, BINDING_HTTP_REDIRECT
from saml2.saml import NAMEID_FORMAT_PERSISTENT

CONFIG = {
    "entityid": "https://app.example.com/saml/metadata",
    "xmlsec_binary": "/usr/bin/xmlsec1",
    "accepted_time_diff": 60,            # clock skew seconds; keep small
    "service": {
        "sp": {
            "allow_unsolicited": False,  # reject IdP-initiated unless required
            "authn_requests_signed": True,
            "want_response_signed": True,
            "want_assertions_signed": True,
            "name_id_format": NAMEID_FORMAT_PERSISTENT,
            "allow_unknown_attributes": False,
            "endpoints": {
                "assertion_consumer_service": [
                    ("https://app.example.com/saml/acs", BINDING_HTTP_POST),
                ],
            },
        },
    },
    "metadata": {"local": ["idp_metadata.xml"]},   # pinned IdP cert lives here
    "key_file": "/etc/saml/sp_private.pem",
    "cert_file": "/etc/saml/sp_public.pem",
}
```

Track and reject seen `Assertion/@ID`s yourself; pysaml2 does not persist a replay cache across processes.

### python3-saml (SAML-Toolkits, formerly OneLogin)

- Current 1.16.x line; depends on `python3-xmlsec` / libxmlsec1. `strict: true` is mandatory in production — without it the toolkit skips security validations and you are exposed.
- Register the IdP `x509cert`, not a fingerprint. Set `rejectDeprecatedAlgorithm: true` to refuse SHA-1.

```json
{
  "strict": true,
  "debug": false,
  "sp": {
    "entityId": "https://app.example.com/saml/metadata",
    "assertionConsumerService": {
      "url": "https://app.example.com/saml/acs",
      "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
    },
    "NameIDFormat": "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
  },
  "idp": {
    "entityId": "https://idp.okta.com/exk...",
    "singleSignOnService": {
      "url": "https://idp.okta.com/app/.../sso/saml",
      "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
    },
    "x509cert": "MIID...full base64 cert, not a fingerprint..."
  },
  "security": {
    "wantMessagesSigned": true,
    "wantAssertionsSigned": true,
    "authnRequestsSigned": true,
    "rejectDeprecatedAlgorithm": true,
    "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
    "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256",
    "wantNameId": true,
    "requestedAuthnContext": true
  }
}
```

After `auth.process_response()`, check `auth.get_errors()` and `auth.is_authenticated()`, then persist `auth.get_last_assertion_id()` in a store and reject duplicates for the replay window.

### ruby-saml (SAML-Toolkits, Ruby)

- Pin >= 1.18 (clears CVE-2024-45409 and the 2025 ruby-saml wrapping CVEs). Set `settings.idp_cert` to the full cert, not `idp_cert_fingerprint`. Enable `settings.security[:want_assertions_signed] = true` and set `settings.security[:digest_method]`/`signature_method` to SHA-256.
- Run with `soft = false` so validation failures raise instead of silently returning an unauthenticated-but-usable object. Pass `:matches_request_id` when building the `Response` so `InResponseTo` is enforced.

### samlify (Node)

- Pin >= 2.10.0 (post CVE-2025-47949). Configure `wantMessageSigned` and `wantAssertionsSigned` on the SP, validate with `sp.parseLoginResponse(idp, 'post', req)`, and read identity only from the parsed extract, never by re-querying the raw XML.

## OIDC for enterprise SSO

Use Authorization Code with PKCE (`code_challenge_method=S256`). Do not use Implicit or the hybrid `id_token` response types for new work. For browser apps, prefer a Backend-For-Frontend that holds tokens server-side rather than exposing them to JS.

The three parameters are not interchangeable: `state` defeats CSRF/misbinding on the redirect, `nonce` binds the ID token to this login and blocks ID-token replay, PKCE binds the authorization code to the client that started the flow. Dropping any one reopens a distinct attack path.

ID token validation (Python, Authlib + discovery):

```python
import requests
from authlib.jose import jwt, JsonWebKey

oidc = requests.get(
    "https://idp.example.com/.well-known/openid-configuration", timeout=5
).json()
jwks = JsonWebKey.import_key_set(requests.get(oidc["jwks_uri"], timeout=5).json())

claims = jwt.decode(
    id_token, jwks,
    claims_options={
        "iss":   {"essential": True, "value": oidc["issuer"]},
        "aud":   {"essential": True, "value": CLIENT_ID},
        "exp":   {"essential": True},
        "nonce": {"essential": True, "value": session_nonce},
    },
)
claims.validate(leeway=60)   # clock skew, seconds
# If aud is an array, also require azp == CLIENT_ID.
```

Rules:
- Enforce the signing `alg` from `id_token_signing_alg_values_supported` (RS256/ES256). Reject `alg: none` and reject HS256 when you expect asymmetric — alg confusion turns your client secret into a signing key.
- Verify `iss`, `aud`, `exp`, `iat`, and `nonce` every time. Verify `at_hash`/`c_hash` for hybrid/implicit flows if used.
- Cache JWKS by `kid`; refresh on an unknown `kid` and honor `Cache-Control`. Tolerate key rotation by accepting multiple keys.
- Enforce exact `redirect_uri` matching server-side; no wildcards, no path-suffix tricks.
- Token lifetimes: access tokens 5-15 min; rotate refresh tokens with reuse detection; consider sender-constrained tokens (DPoP or mTLS) for high-value APIs.

## SCIM 2.0 provisioning

SCIM (RFC 7642 requirements, RFC 7643 schema, RFC 7644 protocol) handles lifecycle; SAML/OIDC handle authentication. Enterprises need both. Implement the SP side as a resource server the IdP calls.

Endpoints to expose under a `/scim/v2` base: `/Users`, `/Groups`, `/ServiceProviderConfig`, `/ResourceTypes`, `/Schemas`. Content type is `application/scim+json`.

- Auth: accept an OAuth 2.0 bearer token, not a static API key. Scope it least-privilege and keep it short-lived/rotated. Reject calls without it.
- Stable identifier: store the IdP's `externalId` and treat it (or a normalized `userName`) as the join key to SAML/OIDC subjects. This is the most important design decision in the integration.
- Use PATCH (RFC 7644 `PatchOp`) for updates; full PUT replaces are lossy. Support `add` / `replace` / `remove`.
- Deprovisioning: prefer a soft disable (`active: false`) so sessions are killed and audit history survives; also honor `DELETE` since some IdPs send it. Disabling a user must immediately invalidate active sessions and tokens, not just block next login.
- Filtering and paging: support `filter=userName eq "x"`, `startIndex`, and `count`. IdPs probe with these before creating users; getting them wrong produces duplicates.
- Idempotency and ordering: SCIM calls arrive out of order, late, or retried. Make creates idempotent on `externalId` and build a reconciliation job to catch missed updates.
- Attribute mapping: IdPs disagree on attribute names and lean on custom/enterprise extensions (`urn:ietf:params:scim:schemas:extension:enterprise:2.0:User`). Map flexibly; do not hard-code one IdP's layout.

Disable a user with PATCH:

```http
PATCH /scim/v2/Users/2819c223-7f76-453a-919d-413861904646
Authorization: Bearer <short-lived-token>
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [ { "op": "replace", "path": "active", "value": false } ]
}
```

## Testing

TDD is mandatory here, and the tests that matter are the negative ones. Mock the IdP; feed your ACS handler crafted assertions and assert rejection:

- A valid signature wrapping a second, unsigned admin assertion (XSW). Must reject.
- An assertion with the signature element stripped. Must reject.
- A Response signed but the inner Assertion unsigned, identity read from the assertion. Must reject.
- SHA-1 `SignatureMethod`. Must reject.
- Expired `NotOnOrAfter`, wrong `Audience`, wrong `Recipient`/`Destination`, mismatched `InResponseTo`. Each must reject.
- A replayed assertion (same `@ID` twice). Second must reject.
- Comment-truncation NameID (`user<!---->@evil.com`). Must resolve to the canonicalized value, not the spoofed one.
- OIDC: `alg: none`, HS256 signed with the client secret, wrong `aud`, missing/mismatched `nonce`, expired `exp`. Each must reject.

Tools: SAML Raider (Burp extension) and python3-saml/ruby-saml's own test fixtures for generating malicious documents. Pin library versions in tests and add a CI check that fails the build on known-vulnerable versions of the SAML/OIDC libraries.

## Operational hardening

- Keys/certs: SP and IdP signing keys RSA 2048 minimum (prefer 3072) or EC P-256, SHA-256 digests, certificate lifetime <= 2 years. Keep private keys in an HSM or KMS, never in the repo.
- Metadata: consume signed IdP metadata, honor `validUntil`, and alert before IdP cert expiry. Automate SP metadata publication so EntityID, ACS URL, and certs stay consistent.
- Logging: log every assertion/token rejection with the reason and a correlation ID, but never log raw assertions, tokens, or private keys. Alert on spikes in signature-validation failures — that is an attack signature.

## Common pitfalls

- Verifying the signature, then re-selecting "the assertion" from the document by tag name or XPath. That gap between the validated node and the node you read is XML Signature Wrapping — the exact bug behind CVE-2024-45409 (ruby-saml) and CVE-2025-47949 (samlify). Read identity only from the DOM node the signature covered.
- Accepting "response signed, assertion unsigned" while reading identity from the assertion. Signature confusion; set `wantAssertionsSigned` and do not weaken it to response-or-assertion.
- Treating a missing signature as a pass. Signature exclusion attacks work because the code path for "no signature present" forgets to fail.
- Taking the verification key from the message's `KeyInfo` instead of pinned metadata. The attacker controls `KeyInfo`; they will happily sign with their own key.
- Pinning a SHA-1 certificate fingerprint instead of the full cert. Fingerprint collisions have bypassed validation, and a fingerprint says nothing about the rest of the certificate.
- Not rejecting documents with duplicate element IDs, which is the cheap check that kills most wrapping variants before signature logic even runs.
- Leaving `allow_unsolicited` (pysaml2) or unsolicited-response acceptance (python3-saml) on by default. IdP-initiated flow has no `InResponseTo` binding and is login-CSRF by design; it must be per-tenant, default off.
- Running python3-saml with `strict: false` or ruby-saml with `soft = true` in production. Both silently skip or swallow the validations this whole skill is about.
- Assuming the library keeps a replay cache. pysaml2 does not persist consumed assertion IDs across processes; without your own store, every assertion is replayable until `NotOnOrAfter`.
- Accepting SHA-1 signatures or multi-hour assertion lifetimes, or stretching clock-skew tolerance past 180 seconds to paper over an unsynced server clock.
- Parsing SAML XML with DTDs or external entities enabled — an XXE reading your filesystem is a strange price for single sign-on.
- Provisioning SCIM users with an `externalId`/`userName` that does not equal the SAML `NameID`/OIDC subject seen at login. Every mismatch is a duplicate account or an orphaned session, and it is the top integration defect.
- Treating SCIM deprovisioning (`active: false` or DELETE) as "block the next login" while existing sessions and tokens keep working. Disable must kill live sessions immediately.
- OIDC-side: choosing HS256 with the client secret when you expect asymmetric keys (alg confusion), skipping `nonce`, or wildcarding `redirect_uri` matching.

## Definition of done

- [ ] SP-initiated is the default; IdP-initiated is per-tenant, default off, with `InResponseTo` absent enforced and `@ID`/`SessionIndex` replay caching.
- [ ] Signature verified against pinned IdP cert from metadata (not `KeyInfo`, not a fingerprint); the signed `Reference URI` resolves to the exact node identity is read from.
- [ ] Documents with duplicate element IDs are rejected; schema validation runs first; DTD/XXE disabled.
- [ ] `wantAssertionsSigned` on; SHA-1 rejected; RSA-SHA-256+ required; `strict`/`soft=false` set per library.
- [ ] `Issuer`, `Conditions` (NotBefore/NotOnOrAfter, skew <= 180s), `Audience`, `Recipient`, `Destination`, and `InResponseTo` all validated; assertion `@ID` replay cache in place.
- [ ] SAML library pinned to a fixed, non-vulnerable version (ruby-saml >= 1.18, samlify >= 2.10.0, current python3-saml/pysaml2); CI fails on known-CVE versions.
- [ ] OIDC uses Auth Code + PKCE(S256); ID token `iss`/`aud`/`exp`/`nonce` and signing `alg` validated; `alg:none` and alg-confusion rejected; exact redirect_uri match; JWKS cached by `kid` with rotation.
- [ ] SCIM uses bearer-token auth, stable `externalId` join key, PATCH semantics, soft-disable that kills live sessions, idempotent creates, and a reconciliation path.
- [ ] One stable identifier shared across SAML/OIDC subject and SCIM `userName`/`externalId`; no duplicate-account path.
- [ ] Negative-path tests (XSW, signature exclusion/confusion, replay, comment truncation, OIDC alg/aud/nonce) exist and pass; rejections logged without leaking secrets.
- [ ] Keys >= RSA 2048 / EC P-256 in HSM/KMS, certs <= 2-year lifetime, IdP metadata expiry alerting in place.

## References

- OWASP SAML Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
- CVE-2024-45409 (ruby-saml): https://nvd.nist.gov/vuln/detail/cve-2024-45409 and https://projectdiscovery.io/blog/ruby-saml-gitlab-auth-bypass
- CVE-2025-47949 (samlify): https://www.endorlabs.com/learn/cve-2025-47949-reveals-flaw-in-samlify-that-opens-door-to-saml-single-sign-on-bypass
- python3-saml: https://github.com/SAML-Toolkits/python3-saml
- pysaml2 config: https://pysaml2.readthedocs.io/en/latest/howto/config.html
- SCIM RFCs 7642/7643/7644; AWS IAM Identity Center SCIM+SAML: https://docs.aws.amazon.com/singlesignon/latest/userguide/scim-profile-saml.html
- OIDC state/nonce/PKCE: https://auth0.com/blog/demystifying-oauth-security-state-vs-nonce-vs-pkce/
