---
name: mobile-security-stride-relevant
description: Governs client-side Flutter security by STRIDE category, covering secure credential storage, certificate pinning, release-build hardening, platform-channel trust boundaries, root/jailbreak signal handling, and secret management benchmarked against OWASP MASVS/MASTG. Use when storing tokens, adding a platform channel, configuring TLS pinning, or reviewing a release build for leaked secrets.
---

# Mobile Security (STRIDE-Relevant)

This skill governs client-side security for Flutter apps, organized by the STRIDE categories that matter on a device the attacker owns: credential storage, certificate pinning, binary hardening, platform-channel trust boundaries, root/jailbreak signals, and secret handling. The stance: a shipped Flutter binary is attacker-readable input — `strings` on the release artifact recovers every Dart const — so the client enforces nothing alone; it raises attacker cost while the server stays the authority. Benchmark decisions against OWASP MASVS/MASTG.

## Information disclosure: secure storage and secrets

- Per-user credentials (refresh tokens, session material) go in `flutter_secure_storage` (9.x), which fronts the iOS Keychain and Android Keystore-backed `EncryptedSharedPreferences`. Configure deliberately: iOS `KeychainAccessibility.first_unlock_this_device` (survives background refresh, never migrates via backup to another device); Android `encryptedSharedPreferences: true`. Never store tokens in `shared_preferences`, SQLite, or files — all plaintext on a rooted device and in some backup paths.
- Secrets never live in Dart consts. `--dart-define` values, `String.fromEnvironment`, and "obfuscated" literals all end up extractable from the AOT snapshot; obfuscation renames symbols, it does not encrypt strings. Third-party API keys that must not leak belong behind your backend proxy; keys that are inherently public (Maps client key) get platform-side restrictions (package name + SHA-256 cert on Android, bundle id on iOS) instead of hiding.
- Keep secrets out of logs and crash reports: no token-bearing `debugPrint`, redact PII in the crash-reporting `beforeSend` hook, and strip verbose logging from release builds (`kReleaseMode` guard or a logger with release-level filtering).

## Spoofing: TLS and certificate pinning

All traffic is TLS; pin for the endpoints that carry credentials or money. Pin the SPKI (public-key) hash, not the leaf certificate, so routine renewals with the same key do not brick the app; ship at least two pins (current + backup key) and an expiry strategy — a remotely killable pin config beats an app-store-release scramble when a key rotates. With `dio`, implement pinning via a `badCertificateCallback`/`SecurityContext` on the underlying adapter or a maintained pinning interceptor; verify behavior with a mitmproxy run — the app must refuse the proxied connection. Never ship `badCertificateCallback: (cert, host, port) => true` or an `allowInsecure` debug flag reachable in release; gate any dev-proxy allowance on `kDebugMode` and assert it in a test.

## Tampering: binary hardening and channel validation

- Build releases with `flutter build apk|ipa --obfuscate --split-debug-info=build/symbols/<version>`; archive the symbols privately per release for crash symbolication. This raises reverse-engineering cost; it is not confidentiality.
- Treat every platform channel as a trust boundary. A `MethodChannel` handler on the native side receives whatever any code in the process sends: validate argument types and ranges before acting (file paths canonicalized and confined to app storage, URLs allowlisted, numeric bounds checked), and never build native SQL/shell/intent payloads from unvalidated channel arguments. On the Dart side, treat native responses as untrusted input too — decode defensively.
- Enable Android app integrity via Play Integrity API and iOS App Attest for high-value actions when the backend can verify the verdict server-side; a client-side-only integrity check is decoration.

## Elevation of privilege: root/jailbreak signals and least privilege

Detect compromised environments with `freerasp` (Talsec) or `flutter_jailbreak_detection`: root/jailbreak, Frida-style hooking, emulator, debugger. Treat results as risk signals, not gates — report them to the backend and let policy decide (step-up auth, restrict sensitive features, deny high-value transactions). Hard-blocking every rooted device ships false positives and a support queue while a competent attacker bypasses the check anyway; the server-side decision is what the attacker cannot patch out. Request platform permissions at the moment of use, least-privilege (`ACCESS_FINE_LOCATION` only if coarse is insufficient), and never rely on client-side feature gating for authorization — every privileged operation re-checks authorization server-side.

## Repudiation and denial of service

Audit-log sensitive actions server-side with server timestamps and authenticated identity; client logs are attacker-editable and disappear with an uninstall. Network calls carry timeouts (`connectTimeout`/`receiveTimeout` on `dio`, ~10–30 s) and retry with exponential backoff plus jitter, capped, so a degraded backend does not meet a synchronized client stampede. Debounce user-triggered expensive calls; make mutation endpoints idempotent (idempotency keys) so retries are safe.

## Remaining hygiene

Flag Android screens showing balances or credentials with `FLAG_SECURE` (blocks screenshots/recents thumbnails) and blur the iOS app-switcher snapshot. Exclude token stores from OS backups where feasible. Keep WebViews away from authenticated sessions unless required; if required, disable JavaScript bridges you do not use and pin/allowlist their origins. Run `dart pub audit`-equivalent dependency checks (osv-scanner, Dependabot) in CI, and never commit keystores or provisioning secrets — CI injects them.

## Common pitfalls

- API keys or endpoints in Dart consts / `--dart-define`, "protected" by obfuscation; `strings` on the AOT snapshot recovers them.
- Tokens in `shared_preferences` or app documents because secure storage "had a platform issue"; plaintext on rooted devices.
- Pinning the leaf certificate with a single pin; first renewal bricks every installed client.
- `badCertificateCallback => true` (or a global proxy-trust flag) reachable in release builds.
- Native channel handlers acting on unvalidated paths/URLs/amounts from `MethodCall.arguments`; path traversal and intent redirection follow.
- Hard-blocking on root detection client-side only; false positives for legitimate users, trivially patched out by attackers, no server-side signal recorded.
- Authorization enforced by hiding buttons; the API happily executes for anyone replaying requests.
- Verbose logging of requests/responses (with headers) left on in release; tokens end up in device logs and crash breadcrumbs.
- `--obfuscate` without archiving `--split-debug-info` symbols; production crashes become unreadable.

## Definition of done

- [ ] Credentials live only in `flutter_secure_storage` with explicit Keychain accessibility and Keystore-backed encryption; nothing token-shaped in prefs, SQLite, files, or backups.
- [ ] No secret in Dart source, consts, or dart-defines; third-party keys proxied server-side or platform-restricted; repo and CI history clean of keys and keystores.
- [ ] SPKI pinning (>= 2 pins, rotation plan) active on credential/money endpoints; mitmproxy verification performed; no insecure-TLS escape hatch in release.
- [ ] Release builds use `--obfuscate --split-debug-info`; symbols archived per release for symbolication.
- [ ] Every platform-channel handler validates types, ranges, paths, and URLs on both sides; a test covers a malicious-argument case.
- [ ] Root/jailbreak/hooking signals collected and reported; policy decisions (step-up, restrict, allow) made server-side; no client-only hard gate.
- [ ] Sensitive actions audit-logged server-side; network calls have timeouts and capped jittered backoff; mutations idempotent.
- [ ] `FLAG_SECURE`/switcher-snapshot protection on sensitive screens; release logging redacted; dependency vulnerability scanning runs in CI.
