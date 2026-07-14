---
name: password-security
description: Governs how passwords and credentials are stored and verified so a database dump does not become an account-takeover event, covering breach-corpus screening, NIST SP 800-63B-4 policy, and online-guessing throttling. Use when implementing password hashing, credential storage, or rate limiting for a login endpoint.
---

# Password and Credential Security

Purpose: store and verify passwords so a database dump does not become an account-takeover event, screen credentials against breach corpora, set a policy that matches NIST SP 800-63B-4, and throttle online guessing. This is the credential half of the Auth Engineer role; MFA, sessions, and OAuth flows live in their own skills.

## Scope and version baseline

- NIST SP 800-63B-4, finalized 2025-07-31, is the current digital-identity standard. It replaced complexity rules and forced rotation with length, breach screening, and rate limiting. Cite the section, not folklore.
- RFC 9106 (2021) is the Argon2 spec. Argon2id is the variant to use; it combines Argon2i side-channel resistance with Argon2d GPU resistance.
- OWASP Password Storage Cheat Sheet is the working reference for concrete parameters and is updated more often than the RFC.
- Library pins this skill assumes: `argon2-cffi >= 23.1` (Python, wraps the reference C library), `bcrypt >= 4.1` (Python; behavior changed at 5.0, see below), Node `argon2 >= 0.31` (node-argon2) or `@node-rs/argon2`, PHP `password_hash` with `PASSWORD_ARGON2ID` (PHP 7.3+ compiled with Argon2 support), Java Spring Security `Argon2PasswordEncoder` / `BCryptPasswordEncoder` (Spring Security 6.x). Pin exact versions; a hashing library is not a place to float to `latest`.

## Choosing the hash: Argon2id first, bcrypt for constrained or legacy

Decision rule:

1. New systems: Argon2id.
2. Argon2 unavailable in the platform or you are constrained to a FIPS-validated module: bcrypt with the pre-hash recipe below, or PBKDF2-HMAC-SHA-256 (FIPS-approved) with a high iteration count.
3. Never a plain or fast hash. SHA-256, SHA-512, MD5, SHA-1, or any single-pass hash is unacceptable for passwords regardless of salting; GPUs compute billions per second. Reject these in review on sight.

Why Argon2id over bcrypt: bcrypt is CPU-hard only, so it is cheap to attack on memory-rich GPU and ASIC rigs, and it caps input at 72 bytes. Argon2id is memory-hard with tunable memory, time, and parallelism, which is what raises the attacker's per-guess cost.

## Argon2id

OWASP minimum parameters (pick one of the two trade-offs, both calibrated to the same security level):

- `m = 19456` KiB (19 MiB), `t = 2`, `p = 1` — the memory-leaning profile.
- `m = 47104` KiB (46 MiB), `t = 1`, `p = 1` — the CPU-leaning profile when memory is scarce.

Memory is expressed in KiB. Tune upward on real hardware until a single verify lands near 250-500 ms server-side, then hold that as the floor. Output and salt lengths: `hash_len = 32`, `salt_len = 16` (the library generates a CSPRNG salt per hash; never reuse or hand-roll salts).

Python with `argon2-cffi`. Note the library's own `PasswordHasher` defaults (`t=3, m=65536, p=4`) differ from the OWASP minimums, so set parameters explicitly rather than trusting defaults:

```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError, VerificationError

ph = PasswordHasher(
    time_cost=2,        # t: iterations
    memory_cost=19456,  # m: 19 MiB, expressed in KiB
    parallelism=1,      # p: lanes; keep <= verifier CPU threads
    hash_len=32,
    salt_len=16,
)

# Store this whole PHC string; it self-describes the parameters and salt:
# $argon2id$v=19$m=19456,t=2,p=1$<b64 salt>$<b64 hash>
stored = ph.hash(password)

def verify(stored: str, password: str) -> bool:
    try:
        ph.verify(stored, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    # Transparent upgrade: re-hash when the stored params are below current policy.
    if ph.check_needs_rehash(stored):
        new_hash = ph.hash(password)   # persist new_hash for this user now
    return True
```

The PHC string (`$argon2id$v=19$m=...,t=...,p=...$salt$hash`) is the storage format. Store it verbatim in a single column; do not split parameters into separate columns. `check_needs_rehash` plus re-hash on successful login is how you raise cost over time without a forced reset.

Cross-stack equivalents: PHP `password_hash($pw, PASSWORD_ARGON2ID, ['memory_cost'=>19456,'time_cost'=>2,'threads'=>1])` and `password_needs_rehash`; Node `argon2.hash(pw, {type: argon2.argon2id, memoryCost: 19456, timeCost: 2, parallelism: 1})`; Spring `new Argon2PasswordEncoder(16, 32, 1, 19456, 2)`.

Argon2 pitfalls:
- Setting `p` higher than the verifier's available threads gives no security benefit and slows verification. Match `p` to the box, default to 1.
- Memory cost is per concurrent hash. `m = 64 MiB` with 200 simultaneous logins is 12.8 GiB of transient RAM; size the pool and the host, or you self-inflict a DoS at the login spike.
- Do not pepper by concatenation (see Peppering). Do not truncate or normalize the PHC string.

## bcrypt

Only when Argon2 is genuinely unavailable. Two hard constraints define correct usage.

1. 72-byte input cap. bcrypt ignores everything past 72 bytes. Until Python `bcrypt` 5.0 this truncation was silent; from 5.0.0 the library raises on input longer than 72 bytes. Silent truncation means "correcthorsebatterystaple..." and the same prefix authenticate identically.
2. Null-byte truncation. Classic bcrypt stops at the first `0x00`. A raw-binary pre-hash can contain a null and get cut short.

Both are solved by pre-hashing with base64-encoded SHA-256, which is always ASCII, never contains a null, and fits well under 72 bytes:

```python
import bcrypt, hashlib, base64

def _prehash(password: str) -> bytes:
    digest = hashlib.sha256(password.encode("utf-8")).digest()  # 32 raw bytes
    return base64.b64encode(digest)                             # 44 ASCII bytes, no NUL

def hash_pw(password: str) -> bytes:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=12))  # cost 12 -> $2b$12$...

def verify_pw(password: str, stored: bytes) -> bool:
    return bcrypt.checkpw(_prehash(password), stored)
```

The pre-hash also keeps you compliant with the 800-63B-4 SHALL to verify the entire submitted password: nothing is truncated because the full input is folded into the 44-byte digest before bcrypt sees it.

Work factor (cost): OWASP floor is 10; 12 is a common modern default. The cost is a log2 exponent, so each step doubles work. Calibrate to roughly 250 ms on the verifier and store the cost in the hash (`$2b$12$...`), which lets you raise it later and re-hash on login.

bcrypt pitfalls:
- Prefer the `$2b$` prefix. `$2a$` carries an old length-counter wraparound bug for very long inputs; `$2y$` is a PHP-only variant. Most current libraries emit `$2b$`.
- Pre-hash with base64, not raw bytes, to dodge the null-byte cut.
- Password shucking: if you pre-hash with an unsalted fast hash, an attacker who finds the same fast-hash digest in a breach can verify candidates against your bcrypt column without cracking bcrypt. Mitigate by making the pre-hash a keyed HMAC with a secret pepper (next section), e.g. `bcrypt(base64(hmac_sha384(pepper, password)))`, so the intermediate digest is useless without the pepper.

## Peppering (defense for both algorithms)

A pepper is a single secret key, the same for all users, applied with an HMAC before the password hash, and kept outside the database in a KMS, HSM, or secrets manager. A salt defeats precomputation and is stored next to the hash; a pepper defeats offline cracking of a stolen database because the attacker does not have the key.

```python
import hmac, hashlib, base64

def peppered(password: str, pepper: bytes) -> bytes:
    # pepper: >= 32 random bytes from KMS/HSM, never written to the DB
    return base64.b64encode(hmac.new(pepper, password.encode("utf-8"), hashlib.sha384).digest())

stored = ph.hash(peppered(password, pepper).decode())   # then Argon2id over the peppered value
```

Pepper rules: store a key id alongside the hash so peppers can be rotated; rotate by re-peppering on next successful login; never log it or commit it. A pepper is not a substitute for a strong hash, only an additive layer.

## NIST SP 800-63B-4 password policy

Encode these as the verifier's rules. The SHALLs are mandatory, the SHALL NOTs are prohibitions auditors check for.

Length:
- SHALL require at least 15 characters when the password is the only authentication factor.
- MAY allow 8 as the floor only when the password is one factor inside MFA.
- SHOULD allow at least 64 characters. Do not cap shorter; long passphrases are the goal.

Composition and rotation (the big reversals):
- SHALL NOT impose composition rules (no "one upper, one digit, one symbol").
- SHALL NOT require periodic rotation. Force a change only on evidence of compromise.
- SHALL NOT permit password hints accessible to an unauthenticated party, and SHALL NOT use knowledge-based questions ("mother's maiden name").

Character handling:
- SHALL accept all printing ASCII and the space character; SHOULD accept Unicode. Count each Unicode code point as one character toward the minimum.
- If you normalize Unicode before hashing, 800-63B-4 specifies NFC; apply it consistently on both set and verify, or the same typed password will fail to match. Normalize once, in one place.
- Allow paste so password managers work; do not block paste into password fields.

Screening and feedback:
- SHALL compare prospective passwords against a blocklist of compromised values, common words, dictionary words, repetitive or sequential strings, and context-specific words (the service name, the username). On a hit, reject and tell the user why so they can choose another.

## Breached-password checks (Have I Been Pwned, k-anonymity)

The Pwned Passwords range API screens against billions of breached credentials without sending the password or its full hash. You SHA-1 the password, send only the first 5 hex characters of the digest, and the API returns every suffix sharing that prefix with its breach count. You match the suffix locally. The server never learns which password you asked about.

```python
import hashlib, httpx

def pwned_count(password: str) -> int:
    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    resp = httpx.get(
        f"https://api.pwnedpasswords.com/range/{prefix}",
        headers={"Add-Padding": "true"},   # pads response with synthetic rows to defeat response-size analysis
        timeout=2.0,
    )
    resp.raise_for_status()
    for line in resp.text.splitlines():
        tail, _, count = line.partition(":")
        if tail == suffix:
            return int(count)
    return 0
```

Operational notes:
- The range endpoint is free and needs no API key (only the account/email-breach API is keyed). SHA-1 here is a lookup index, not a password hash, so its collision weakness is irrelevant; the password is still stored under Argon2id.
- `Add-Padding: true` returns each prefix bucket padded with synthetic zero-count rows to a uniform size, so an on-path observer cannot infer a hit from the response length. Keep it on, and ignore rows with a count of 0.
- NTLM variant exists (request the NTLM list) for Active Directory screening; suffixes are 27 hex chars instead of 35.
- Reliability: on signup, fail open and log if the API is unreachable. Blocking new registrations because a third party is down trades a security nicety for an availability outage. For high-volume or air-gapped systems, download the full ordered Pwned Passwords corpus and self-host the range API; the dataset is large but lookups are O(1) by prefix.
- Where to apply: screen on registration and on password change always. Optionally screen at login and, on a hit, force a reset on next sign-in, since a password can be breached after it was set.

## Account lockout and rate limiting

Goal: make online guessing and credential stuffing uneconomical without handing attackers a denial-of-service lever against real users.

- NIST ceiling: no more than 100 consecutive failed attempts per account before additional defenses engage. Prefer throttling and step-up over a hard permanent lock; a permanent lock on a known username is itself a DoS.
- Two independent counters. Per-account (someone targeting one user) and per-IP or per-subnet (one source spraying many users). Credential stuffing trips the per-IP counter while staying under any single account's threshold.
- Exponential backoff with jitter on repeated failures for the same account, backed by an atomic store (Redis counter with TTL). Add a CAPTCHA after a few failures and step-up to MFA before lockout rather than denying outright.
- Reset failure counters on a successful, MFA-completed login.
- Detect distributed stuffing by velocity and reputation (impossible travel, datacenter ASN, many-accounts-one-IP), not by per-account counts alone.

Tooling: Python `fastapi-limiter` or `slowapi` over Redis, `limits` for the algorithm; Node `rate-limiter-flexible`; Spring Security with Bucket4j or `resilience4j`; or an edge WAF rate-limit rule as the first line. Keep the authoritative counter server-side and atomic so parallel requests cannot race past the limit.

Two correctness requirements at the verify step, both about not leaking which accounts exist:

```python
import secrets

DUMMY_HASH = ph.hash(secrets.token_urlsafe(32))  # precomputed once at startup

def authenticate(username: str, password: str) -> bool:
    user = users.get(username)
    record = user.password_hash if user else DUMMY_HASH
    ok = verify(record, password)   # constant work whether or not the user exists
    return bool(user) and ok
```

- Always run the hash verify even for an unknown username (against a dummy hash), so response time does not reveal valid accounts. Argon2 and bcrypt comparisons are already constant-time internally; the timing leak you are closing is the early return.
- Return one generic message ("invalid username or password") for wrong-user and wrong-password alike. Do the same on the password-reset flow: respond identically whether or not the email exists.

## Storage and operational hygiene

- One text column holds the full PHC / `$2...$` string; it encodes algorithm, parameters, and salt, so you can migrate algorithms by reading the prefix.
- Never log passwords, pre-hashes, peppers, or full hashes. Scrub them from request logs, crash dumps, and error trackers.
- Migrate legacy hashes lazily: on the next successful login, verify with the old scheme then re-hash with Argon2id and overwrite. For dead-account legacy hashes (SHA-1, MD5), wrap them as `argon2id(legacy_hash)` in a bulk pass so nothing weak remains at rest, then peel off the wrapper on next login.
- Send a notification (out-of-band) on password change and on lockout, so an account-takeover attempt is visible to the real owner.

## Testing (TDD applies)

- Hashing: assert `hash(pw) != hash(pw)` (per-call random salt), `verify` true for the right password and false for the wrong one, and that the emitted PHC string carries the configured parameters.
- Rehash path: hash with low parameters, raise the policy, assert `check_needs_rehash` is true and that a successful login persists a new hash.
- bcrypt: a 73-plus-byte password and one differing only past byte 72 must not authenticate each other; a password containing `\x00` after pre-hashing must still verify.
- Breach check: mock the HIBP HTTP call (never hit the network in tests); assert a known-pwned suffix is rejected, a clean one passes, and a simulated timeout fails open on signup.
- Lockout: drive N failures and assert throttling, that an unknown user and a wrong password return the same message and comparable timing, and that a success resets the counter.

## Common pitfalls

- Any fast or unsalted hash (MD5, SHA-1, SHA-256, SHA-512) used directly for passwords.
- Trusting library defaults instead of setting Argon2 `m/t/p` to a calibrated, documented value.
- bcrypt without the base64 SHA-256 pre-hash, so passwords silently truncate at 72 bytes or a null byte.
- Storing the pepper in the same database as the hashes, or peppering by plain concatenation instead of HMAC.
- Sending the full password or full hash to a third-party breach API instead of the 5-character k-anonymity prefix; or hard-failing signup when that API is down.
- Composition rules, forced periodic rotation, password hints, or KBA still present after the 800-63B-4 update.
- Blocking paste, capping length below 64, or counting bytes instead of code points for Unicode.
- Early return on unknown username, or distinct error messages, leaking which accounts exist.
- Permanent hard lockout with no MFA/CAPTCHA off-ramp, turning a guessing defense into a DoS.

## Definition of done

- [ ] Passwords hashed with Argon2id at OWASP-minimum-or-higher parameters (`m>=19456 KiB, t>=2, p=1`), or bcrypt `cost>=10` with a base64 SHA-256 pre-hash where Argon2 is unavailable; parameters calibrated to ~250 ms on real hardware and documented.
- [ ] Full PHC / cost string stored verbatim; per-call CSPRNG salt; algorithm and parameters upgradeable.
- [ ] `check_needs_rehash` (or equivalent) runs on every successful login and persists an upgraded hash.
- [ ] Optional pepper applied via HMAC, sourced from KMS/HSM, never in the database, with a key id for rotation.
- [ ] Policy matches NIST SP 800-63B-4: minimum 15 (8 inside MFA), maximum >= 64, all printing ASCII plus space and Unicode accepted, consistent NFC normalization, paste allowed; no composition rules, no forced rotation, no hints, no KBA.
- [ ] Breach screening against Pwned Passwords via the k-anonymity range API (`Add-Padding: true`) on registration and password change; signup fails open and logs on API outage.
- [ ] Per-account and per-IP rate limiting with exponential backoff and a CAPTCHA/MFA step-up; failed-attempt ceiling at or below 100; counters atomic and server-side; reset on success.
- [ ] Unknown-user logins run a dummy verify; login and reset return generic, timing-equalized responses.
- [ ] No password, pre-hash, pepper, or hash written to any log, trace, or error report.
- [ ] Legacy/weak hashes migrated lazily on login or wrapped at rest; out-of-band notification on password change and lockout.
- [ ] Unit and integration tests cover hashing, rehash, bcrypt truncation and null-byte cases, mocked breach checks, and lockout; external services mocked.
- [ ] Decision and parameters persisted to project memory (`save_decision`); security-sensitive changes handed off for review.

## References

- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- NIST SP 800-63B (Rev. 4): https://pages.nist.gov/800-63-4/sp800-63b.html
- RFC 9106 (Argon2): https://www.rfc-editor.org/rfc/rfc9106.html
- Have I Been Pwned API (range / Pwned Passwords): https://haveibeenpwned.com/API/v3
- Pwned Passwords padding: https://www.troyhunt.com/enhancing-pwned-passwords-privacy-with-padding/
- argon2-cffi: https://argon2-cffi.readthedocs.io/
- Python bcrypt: https://github.com/pyca/bcrypt
