---
name: mfa-passkeys
description: Governs the second-factor and passwordless layer, making the strongest available authenticator the default and weaker factors fallbacks with a migration path, with every enrollment and recovery step replay-safe and rate-limited. Use when adding or reviewing MFA, WebAuthn/passkeys, TOTP, or SMS-based authentication.
---

# MFA and Passkeys

Build the second-factor and passwordless layer so that the strongest available authenticator is the default, weaker factors are fallbacks with a migration path, and every enrollment, verification, and recovery step is replay-safe and rate-limited. Treat phishing-resistant authenticators (WebAuthn/passkeys) as the target and TOTP/SMS as the legacy on-ramp, not the destination.

## Standards baseline and assurance levels

- WebAuthn is a W3C standard (Level 2 is the deployed baseline; Level 3 adds the Signal API, related origin requests, and richer hints). FIDO2 = WebAuthn (browser/RP API) + CTAP2 (authenticator transport). A "passkey" is a discoverable (resident) WebAuthn credential, usually multi-device/synced.
- TOTP is RFC 6238 (built on HOTP, RFC 4226). Step-up over OAuth is RFC 9470. ACR/AMR/`auth_time` come from OpenID Connect Core.
- NIST SP 800-63B-4 (final, 2025) drives the policy: SMS/PSTN OTP is now a restricted authenticator, and synced passkeys and TOTP meet AAL2, while AAL3 requires a hardware-bound, verifier-impersonation-resistant authenticator (FIDO2 security key or a device-bound passkey).
- AAL mapping to use in design:
  - AAL1: any single factor.
  - AAL2: password + TOTP, or a single passkey with user verification (a multi-factor cryptographic authenticator satisfies AAL2 on its own).
  - AAL3: device-bound FIDO2 authenticator with user verification; synced passkeys do not qualify because the private key leaves a single device.
- Phishing resistance is defined by channel binding and verifier name binding. Only WebAuthn provides it out of the box. TOTP, SMS, and push are all phishable via real-time relay.

## TOTP (RFC 6238)

Defaults that keep authenticator-app compatibility: 6 digits, 30-second period, HMAC-SHA1. SHA-256/SHA-512 are spec-legal but break most consumer apps (Google Authenticator, Authy, 1Password assume SHA1 unless the `algorithm` parameter is honored, and many ignore it). Only deviate if you control the authenticator app.

Python with `pyotp` (2.9.x), matching this project's stack:

```python
import pyotp

# Enrollment: 160-bit Base32 secret. Encrypt at rest (KMS/envelope), never log it.
secret = pyotp.random_base32()  # 32 Base32 chars ~= 160 bits
uri = pyotp.totp.TOTP(secret).provisioning_uri(
    name=user.email, issuer_name="Example",
)
# Render `uri` as a QR code (e.g. the `qrcode` package). Never send the secret over email/SMS.

# Verification: accept the current step plus one back and one forward for clock drift.
totp = pyotp.TOTP(secret)              # 6 digits, 30s, SHA1 by default
ok = totp.verify(code, valid_window=1)  # +-1 step; do not raise above 2
```

Thresholds and required controls:

- Drift window: `valid_window=1` (accept previous/current/next step, ~89s worst-case skew). Never go above 2; each extra step linearly enlarges the brute-force surface.
- Replay protection is not free. `pyotp` does not track used codes. Persist the last accepted time step `int(time.time() // 30)` per user and reject any code whose step is less than or equal to it. Without this, a code is valid for its full 30-90s window and is replayable after a real-time phish.
- Rate-limit verification: hard cap (for example 5 attempts), then exponential backoff or temporary lockout. A 6-digit code is 1 in 1,000,000; unlimited guesses break it in hours.
- Enrollment must require a successful verify of a freshly generated code before the secret is marked active, so a mis-scanned QR never produces a locked-out account.
- Secret storage: encrypted column or secrets manager, decrypt only to verify. Treat it as a credential, not config.

JS/TS equivalent: `otplib` (`authenticator.generate`/`authenticator.verify`, `Options.window` is the drift window). Same replay and rate-limit rules apply.

## WebAuthn / passkeys (FIDO2)

This is the phishing-resistant factor and the preferred default. Two ceremonies (registration, authentication), each a server-issued challenge plus a client assertion you verify.

Server with `py_webauthn` (`webauthn` on PyPI, 2.x; 2.8.0 current, requires Python 3.10+):

```python
from webauthn import (
    generate_registration_options, verify_registration_response,
    generate_authentication_options, verify_authentication_response, options_to_json,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria, ResidentKeyRequirement,
    UserVerificationRequirement, PublicKeyCredentialDescriptor,
)

opts = generate_registration_options(
    rp_id="example.com",                 # registrable suffix of the origin, NOT the full URL
    rp_name="Example",
    user_id=user.uuid.bytes,             # opaque handle, <= 64 bytes, never email/PII
    user_name=user.email,
    user_display_name=user.full_name,
    attestation="none",                  # consumer default; "direct" only if you verify via FIDO MDS
    authenticator_selection=AuthenticatorSelectionCriteria(
        resident_key=ResidentKeyRequirement.REQUIRED,        # discoverable => usernameless login
        user_verification=UserVerificationRequirement.REQUIRED,
    ),
    exclude_credentials=[PublicKeyCredentialDescriptor(id=c.id) for c in user.passkeys],
    timeout=60000,
)
session["reg_challenge"] = opts.challenge   # bind challenge to the session/server, single use
return options_to_json(opts)
```

```python
v = verify_registration_response(
    credential=request_json,             # navigator.credentials.create() result
    expected_challenge=session["reg_challenge"],
    expected_rp_id="example.com",
    expected_origin="https://example.com",   # exact allowlist: scheme+host+port
    require_user_verification=True,
)
# Persist: v.credential_id, v.credential_public_key, v.sign_count, v.aaguid,
# and v.credential_device_type ("single_device" vs "multi_device" => synced passkey).
```

Authentication, usernameless via discoverable credentials:

```python
opts = generate_authentication_options(
    rp_id="example.com",
    user_verification=UserVerificationRequirement.REQUIRED,
    # omit allow_credentials for usernameless/conditional-UI flows
)
session["auth_challenge"] = opts.challenge

v = verify_authentication_response(
    credential=request_json,
    expected_challenge=session["auth_challenge"],
    expected_rp_id="example.com",
    expected_origin="https://example.com",
    credential_public_key=stored.public_key,
    credential_current_sign_count=stored.sign_count,
    require_user_verification=True,
)
# Cloned-authenticator check: if v.new_sign_count != 0 and v.new_sign_count <= stored.sign_count,
# reject and flag. Many synced passkeys report 0 forever; only enforce when the counter increments.
stored.sign_count = v.new_sign_count
```

Browser with `@simplewebauthn/browser` v13 (pass a single `{ optionsJSON }` object; that signature has been required since v11, replacing the older positional arguments):

```ts
import { startRegistration, startAuthentication } from '@simplewebauthn/browser';

const reg = await startRegistration({ optionsJSON });                 // send back to /verify
const asr = await startAuthentication({ optionsJSON, useBrowserAutofill: true }); // conditional UI
```

Server-side, `@simplewebauthn/server` v13 mirrors `py_webauthn`: `generateRegistrationOptions` / `verifyRegistrationResponse` and the matching `generateAuthenticationOptions` / `verifyAuthenticationResponse` pair. WebAuthn hints surface as `preferredAuthenticatorType` (`'securityKey' | 'localDevice' | 'remoteDevice'`) on `generateRegistrationOptions`, not on the verify call, and intermediate certificates are recognized as attestation trust anchors. Pick one server library; do not split a ceremony across two.

Key configuration decisions:

- `rp_id` must be the registrable domain (`example.com`), not the origin URL, and must be a suffix of every origin you accept. `auth.example.com` can use `rp_id=example.com`; it cannot use `rp_id=accounts.google.com`. To share passkeys across sibling domains (`example.com` and `example.co.uk`), publish a related origin requests file at `/.well-known/webauthn`.
- `user_verification=REQUIRED` makes the passkey a true second factor (PIN/biometric). `PREFERRED` silently degrades to presence-only on authenticators without UV, which drops you below AAL2. Choose deliberately.
- Conditional UI (autofill): add `autocomplete="username webauthn"` to the username field and start authentication with autofill; passkeys appear in the native credential dropdown. Requires a discoverable credential.
- Signal API (Chrome 132+, on by default) keeps the authenticator's passkey list in sync with your server: call `PublicKeyCredential.signalUnknownCredential` when a user presents a credential you deleted, and `signalAllAcceptedCredentials` / `signalCurrentUserDetails` after revocation or profile changes. Without it, deleted passkeys linger in the user's manager and produce confusing failed logins.
- `exclude_credentials` on registration prevents a user from registering the same authenticator twice. `allow_credentials` on authentication is for username-first flows; omit it for usernameless.
- Attestation: default to `"none"`. Only request `"direct"` if you enforce an authenticator allowlist (enterprise) and verify the statement against the FIDO Metadata Service (MDS) by AAGUID. Demanding attestation from consumers harms conversion and privacy for little gain.
- Always verify the challenge is one you issued and is single-use, and that the origin is on an exact allowlist. The challenge and origin checks are what make WebAuthn phishing-resistant; skipping them turns it into a signature with no binding.

## Recovery codes

The break-glass path when every authenticator is lost. Get this wrong and it becomes the soft underbelly attackers target instead of the passkey.

```python
import secrets, hashlib

def generate_recovery_codes(n: int = 10) -> list[str]:
    # ~80 bits each; high entropy means a fast hash is sufficient (unlike passwords).
    return [secrets.token_urlsafe(10) for _ in range(n)]

def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()
```

Rules:

- Generate a set of 8-10 codes, each with at least 64 bits of entropy. Display once at generation; never show again and never email them.
- Store only hashes. Because the codes are high-entropy random, a single SHA-256 is fine; do not store plaintext, and do not reach for Argon2id here (that is for low-entropy passwords).
- Single-use: mark a code consumed on success and reject reuse. Surface the remaining count to the user.
- Regenerate the whole set (invalidating all old codes) when the user requests new ones, after MFA reset, or after a code is used and the set runs low.
- Rate-limit recovery-code entry exactly like TOTP. It is a bearer secret.
- A recovery code should restore access at a normal trust level only; using one to immediately disable all other factors with no cooldown is an account-takeover primitive. Require re-enrollment of a strong factor after recovery.

## SMS-OTP risks

Under NIST SP 800-63B-4, SMS/PSTN delivery is a restricted authenticator. It is not banned, but using it carries obligations: offer at least one unrestricted alternative at the same AAL, notify users of the risk and the alternative, and keep a documented migration plan to retire it.

Why it is restricted, concretely:

- SIM swap: an attacker ports the number to their SIM and receives every code. No app-side fix.
- SS7/signaling interception: codes can be read in transit on the carrier network.
- Real-time phishing relay: a proxy (Evilginx-style) prompts the victim, captures the typed OTP, and replays it within the validity window. SMS, TOTP, and push are all vulnerable; only WebAuthn's origin binding defeats it.
- Number recycling and carrier delivery delays, which also hurt usability.

Practical stance:

- Do not use SMS as a primary second factor for high-value accounts. If you must support it, gate it behind risk and never let SMS alone bootstrap enrollment of stronger factors (a SIM-swapper would otherwise enroll their own passkey).
- Validate and store numbers in E.164, rate-limit sends and verifies, set short code lifetimes (5 minutes), and bind the code to the session.
- Prefer push-with-number-matching or, better, passkeys. Present SMS in the UI as the weakest option, not the recommended one.

## Step-up authentication

Re-verify a stronger or fresher factor before a sensitive action (changing email, moving money, viewing secrets) instead of forcing the strongest factor on every login. Two patterns.

Session-internal: record which factors were satisfied and when (`amr`, `auth_time`). Before a sensitive route, require a recent passkey assertion (for example within the last 5 minutes); if stale, trigger a fresh WebAuthn ceremony and update the timestamp. Keep the freshness window tight for money movement, looser for read-only sensitive views.

OAuth/OIDC across services (RFC 9470): the resource server rejects an insufficiently-authenticated token with a challenge, and the client repeats authorization with `acr_values` and `max_age`:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="insufficient_user_authentication",
  error_description="Phishing-resistant authentication required",
  acr_values="urn:example:acr:passkey", max_age=300
```

The authorization server performs the step-up, issues a token whose `acr`/`amr` reflect the method and whose `auth_time` is fresh, and the resource server validates `acr` against its policy and checks `auth_time` against `max_age`. Map `acr` values to your AALs explicitly (for example a phishing-resistant value for passkey, a lower one for TOTP) so policy is data, not scattered conditionals. Keycloak, Okta, and Auth0 expose this through ACR-to-flow mappings; define the ACR catalog once and enforce it at each protected endpoint.

## Data model and operational notes

- Store per credential: type (totp/passkey/recovery/sms), for passkeys the credential id, public key, `sign_count`, `aaguid`, transports, and device type (single vs multi-device); for TOTP the encrypted secret and last-accepted step; for recovery the hashes and used flags.
- Require at least two distinct factors registered before letting a user remove their last password fallback, so a single lost device does not lock them out.
- Log enroll, verify, fail, lockout, recovery-code use, and factor removal as security events; alert on factor removal and recovery-code use. Removing an MFA factor is itself a sensitive action and should require step-up.
- Enrollment of a new strong factor should not be gated behind only a weak factor (do not let an SMS code authorize adding a passkey on a high-value account).

## Common pitfalls

- TOTP with no replay tracking: a code stays valid for its whole window and is replayable after a phish. Persist and check the last used step.
- Drift window cranked to 5-10 steps "to stop support tickets"; it multiplies the brute-force surface. Fix client clocks, keep window at 1.
- WebAuthn `rp_id` set to the full origin URL or a domain the origin is not a suffix of: every ceremony fails or, worse, you weaken binding.
- `user_verification=PREFERRED` shipped as if it were a real second factor; it degrades to presence-only and drops below AAL2.
- Treating synced passkeys as AAL3. They are AAL2; require a device-bound authenticator for AAL3.
- Sign-count check that rejects synced passkeys reporting 0. Only enforce the cloned-authenticator check when the counter actually increments.
- WebAuthn `user_id` set to the email or a database PK that is PII; it must be opaque and <= 64 bytes.
- Challenge reuse or accepting a challenge not issued this session, which removes the anti-replay guarantee.
- SimpleWebAuthn v13 called with old positional arguments instead of `{ optionsJSON }`.
- Recovery codes emailed, stored in plaintext, not single-use, or not rate-limited.
- SMS allowed to reset or enroll stronger factors, handing SIM-swappers the account.
- Step-up that checks a scope but never `auth_time`/`acr`, so a stale or weak login passes the sensitive gate.

## Definition of done

- [ ] WebAuthn/passkeys is the default offered factor; TOTP and SMS are fallbacks, with SMS presented as the weakest and behind risk gating.
- [ ] TOTP uses 6 digits / 30s / SHA1, `valid_window=1`, persists and rejects the last-used step, rate-limits verification, and requires a verified code before activation; secrets are encrypted at rest.
- [ ] WebAuthn verifies a single-use server challenge, an exact origin allowlist, and the correct `rp_id`; `user_verification=REQUIRED`; sign-count cloned-authenticator check applied only on increment; `user_id` is opaque and <= 64 bytes.
- [ ] Discoverable credentials plus conditional UI enabled for usernameless login; Signal API used to keep client passkey lists in sync after revocation.
- [ ] Attestation defaults to `"none"`; `"direct"` is used only with a FIDO MDS-backed AAGUID allowlist.
- [ ] Recovery codes are high-entropy, hashed, single-use, shown once, rate-limited, and regenerable; using one forces re-enrollment of a strong factor.
- [ ] SMS, if present, is E.164-validated, rate-limited, short-lived, cannot bootstrap stronger factors, and ships with an unrestricted AAL2 alternative, a user notice, and a migration plan per NIST SP 800-63B-4.
- [ ] Step-up re-verifies a fresh, sufficiently strong factor for sensitive actions; OAuth flows use RFC 9470 (`insufficient_user_authentication`, `acr_values`, `max_age`) and validate `acr`/`amr`/`auth_time`.
- [ ] Factors map to explicit AAL levels; AAL3 paths require a device-bound authenticator, not a synced passkey.
- [ ] Enroll/verify/fail/lockout/recovery/removal are logged as security events; factor removal and recovery-code use alert and require step-up.
- [ ] Tests cover replay rejection, drift edges, wrong-origin/wrong-rpId rejection, cloned sign-count, recovery-code single-use, and rate-limit lockout, with all external SMS/email senders mocked.
