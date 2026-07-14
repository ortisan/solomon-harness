---
name: networking-and-secure-storage
description: Governs async/await URLSession clients, typed error mapping, bounded retry with backoff, App Transport Security, Keychain accessibility levels and biometric access control, and certificate pinning on Apple platforms. Use when implementing network calls, storing tokens or secrets, or reviewing ATS exceptions and Keychain accessibility choices.
---

# Networking and Secure Storage

Move every network call onto async/await `URLSession` with `Codable` models, typed error handling and bounded retries, and keep every token, key, or secret in the Keychain with the right access-control flags rather than in `UserDefaults`, files, or `Info.plist`. The stance: the network is hostile and the device may be lost, so transport is encrypted and authenticated by App Transport Security (plus pinning for high-value endpoints), and at-rest secrets are scoped to the tightest `kSecAttrAccessible` level and gated by biometrics when they protect funds or identity.

Targets as of 2026: Swift 6.2, Xcode 26, deployment baseline iOS 18 / iOS 26, macOS 26 (Tahoe). The networking and Keychain APIs below are stable back to iOS 13; the structured-concurrency forms require iOS 15+.

## URLSession with async/await and Codable

Use the `async` `URLSession` methods (`data(for:)`, `data(from:)`, `upload(for:from:)`, `download(for:)`) instead of completion handlers or Combine. They are cancellation-aware: cancelling the enclosing `Task` cancels the transfer. Build one `URLSession` per logical backend from a configured `URLSessionConfiguration` and reuse it; do not create a session per request and never call `URLSession.shared` for authenticated APIs because you cannot pin or tune it.

```swift
struct APIClient {
    let baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder

    init(baseURL: URL, delegate: URLSessionDelegate? = nil) {
        self.baseURL = baseURL
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30          // per-request stall timeout
        config.timeoutIntervalForResource = 120        // whole-resource ceiling
        config.waitsForConnectivity = true             // queue instead of failing when offline
        config.httpAdditionalHeaders = ["Accept": "application/json"]
        self.session = URLSession(configuration: config,
                                  delegate: delegate, delegateQueue: nil)
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .iso8601
        self.decoder = d
    }

    func get<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = "GET"
        let (data, response) = try await session.data(for: request)
        try Self.validate(response, data)
        do { return try decoder.decode(T.self, from: data) }
        catch { throw APIError.decoding(error) }
    }
}
```

Decode into `Codable` value types. Make the model own its wire contract with `CodingKeys` rather than scattering string keys across the app, and keep optionals honest: a field the server may omit is `Optional`, not a force-unwrap waiting to crash. Decode dates and snake_case once on the decoder, not field by field.

## Typed errors and HTTP validation

Map outcomes to a single typed error so call sites can branch on `cancelled`, `unauthorized`, `server`, or `decoding` instead of inspecting `NSError` codes. Always cast the response to `HTTPURLResponse` and check the status code; `URLSession` only throws on transport failures, so a 500 with a JSON error body arrives as a successful `(data, response)` pair.

```swift
enum APIError: Error {
    case transport(URLError)
    case http(status: Int, data: Data)
    case unauthorized
    case decoding(Error)
    case cancelled

    var isRetryable: Bool {
        switch self {
        case .http(let status, _): return status == 429 || (500...599).contains(status)
        case .transport(let e):     return [.timedOut, .networkConnectionLost,
                                            .cannotConnectToHost].contains(e.code)
        default: return false
        }
    }
}

static func validate(_ response: URLResponse, _ data: Data) throws {
    guard let http = response as? HTTPURLResponse else { throw APIError.transport(URLError(.badServerResponse)) }
    switch http.statusCode {
    case 200..<300: return
    case 401, 403:  throw APIError.unauthorized
    default:        throw APIError.http(status: http.statusCode, data: data)
    }
}
```

Treat cancellation as a first-class outcome: a `URLError(.cancelled)` (or `CancellationError`) means the user moved on, not a failure to surface. Check `Task.isCancelled` or catch it explicitly and return quietly rather than showing an alert.

## Retries with backoff and idempotency

Retry only idempotent requests (GET, PUT, DELETE, or POST guarded by an `Idempotency-Key`) and only on retryable errors. Use exponential backoff with jitter, honor a `Retry-After` header when present, and cap attempts so a dead backend cannot spin the radio and drain the battery.

```swift
func send<T: Decodable>(_ request: URLRequest, as type: T.Type,
                        maxAttempts: Int = 3) async throws -> T {
    var attempt = 0
    while true {
        attempt += 1
        do {
            let (data, response) = try await session.data(for: request)
            try Self.validate(response, data)
            return try decoder.decode(T.self, from: data)
        } catch let error as APIError where error.isRetryable && attempt < maxAttempts {
            let backoff = pow(2.0, Double(attempt - 1)) * 0.5      // 0.5s, 1s, 2s
            let jitter  = Double.random(in: 0...0.3)
            try await Task.sleep(for: .seconds(backoff + jitter))
        } catch let error as URLError where error.code == .cancelled {
            throw APIError.cancelled
        }
    }
}
```

Thresholds: 3 attempts total, base delay 0.5s, full jitter up to 0.3s, and never retry a non-idempotent POST without a server-honored idempotency key, because a retried "charge" or "transfer" double-executes. Use `config.waitsForConnectivity = true` for the offline case instead of a busy-retry loop.

## App Transport Security

ATS forces TLS 1.2+ with forward-secret ciphers and is on by default; keep it that way. Do not add `NSAllowsArbitraryLoads = true` to ship faster, because App Review now requires a written justification for every ATS exception and a global allow-all is routinely rejected. If a single legacy host genuinely cannot do TLS 1.2, scope the exception to that domain only.

```xml
<key>NSAppTransportSecurity</key>
<dict>
  <key>NSExceptionDomains</key>
  <dict>
    <key>legacy.partner-api.com</key>
    <dict>
      <key>NSExceptionMinimumTLSVersion</key>
      <string>TLSv1.2</string>
      <key>NSIncludesSubdomains</key>
      <false/>
    </dict>
  </dict>
</dict>
```

Never use `http://`. Local-network and IoT exceptions go through `NSAllowsLocalNetworking`, not a blanket arbitrary-loads switch. ATS is transport hygiene, not authentication: it proves you reached a host with a valid CA chain, not that it is the host you intended, which is what pinning adds below.

## Keychain for tokens and secrets

Store access tokens, refresh tokens, API keys, and symmetric keys in the Keychain through `SecItem` calls (or a thin wrapper). Never put them in `UserDefaults` (plaintext plist, trivially read from a backup), in a file, or in source. Key the item by `kSecAttrService` plus `kSecAttrAccount`, and store the value as `Data` under `kSecValueData`.

```swift
enum Keychain {
    static func save(_ value: Data, service: String, account: String,
                     accessible: CFString = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly) throws {
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let attributes: [String: Any] = [
            kSecValueData as String:   value,
            kSecAttrAccessible as String: accessible,
        ]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            let add = query.merging(attributes) { _, new in new }
            let addStatus = SecItemAdd(add as CFDictionary, nil)
            guard addStatus == errSecSuccess else { throw KeychainError.os(addStatus) }
        } else if status != errSecSuccess {
            throw KeychainError.os(status)
        }
    }

    static func read(service: String, account: String) throws -> Data? {
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String:  true,
            kSecMatchLimit as String:  kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        switch status {
        case errSecSuccess:      return item as? Data
        case errSecItemNotFound: return nil
        default:                 throw KeychainError.os(status)
        }
    }
}
```

`kSecAttrAccessible` controls when the item is readable; pick the most restrictive level that still works:

- `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` — readable only while the device is unlocked. The default for tokens the app uses only in the foreground.
- `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` — readable after the first unlock following a boot. Required for anything a background task or `BGTaskScheduler` job must read while the screen is locked, such as a refresh token used by a background URLSession.
- Never use `kSecAttrAccessibleAlways` / `kSecAttrAccessibleAlwaysThisDeviceOnly` — deprecated and readable on a locked device.
- Always prefer the `...ThisDeviceOnly` variants for secrets. They exclude the item from iCloud Keychain sync and from encrypted iTunes/Finder backups, so a stolen backup cannot exfiltrate the token. Drop `ThisDeviceOnly` only when you deliberately want the secret to roam across the user's devices.

## Access control and biometrics

For secrets guarding money, identity, or a second factor, attach a `SecAccessControl` so the item is released only after a successful Face ID / Touch ID (or device-passcode) check at read time. This binds the secret to user presence; a thief with an unlocked phone still cannot read it without biometric or passcode.

```swift
var error: Unmanaged<CFError>?
guard let access = SecAccessControlCreateWithFlags(
    nil,
    kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly,   // item evaporates if passcode removed
    [.biometryCurrentSet, .privateKeyUsage],           // invalidates if Face/Touch set changes
    &error) else { throw KeychainError.access(error!.takeRetainedValue()) }

let query: [String: Any] = [
    kSecClass as String:            kSecClassGenericPassword,
    kSecAttrService as String:      "wallet",
    kSecAttrAccount as String:      "signing-key",
    kSecValueData as String:        secret,
    kSecAttrAccessControl as String: access,            // replaces kSecAttrAccessible
    kSecUseAuthenticationContext as String: LAContext(),
]
```

Use `.biometryCurrentSet` rather than `.biometryAny` so enrolling a new fingerprint or face after the fact does not silently grant access to the existing secret; the item becomes unusable and must be re-created, which is the correct security posture. `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly` ties the item's existence to the passcode being set, so disabling the passcode destroys it. For asymmetric keys, generate them in the Secure Enclave (`kSecAttrTokenIDSecureEnclave`) so the private key never leaves hardware and only signatures cross the boundary.

## No secrets in Info.plist or the binary

`Info.plist` ships in cleartext inside the app bundle and is trivially dumped with `unzip` on the `.ipa`; the same is true for string constants compiled into the binary. Never store API keys, client secrets, signing keys, or tokens there. A symmetric secret embedded in any shipped app is already compromised, so the correct fix is server-side: keep the secret on a backend and have the app call your endpoint, or use OAuth with PKCE so the public client holds no long-lived secret. If a third-party SDK key must reach the device, fetch it at runtime over TLS from your backend and place it in the Keychain, never bake it into the bundle. Keep build-time configuration that is merely non-sensitive (feature flags, base URLs) in `.xcconfig` and out of source control if it varies per environment, but understand that `.xcconfig` is not a secret store either.

## Certificate and public-key pinning

For high-value endpoints (auth, payments, account management), pin so a fraudulent-but-valid certificate from a mis-issued or attacker-controlled CA cannot impersonate your server. Pin the public key (SPKI) rather than the leaf certificate, because the key survives normal certificate rotation while the certificate bytes do not; pinning the leaf forces an app update on every renewal. Implement it in the session delegate's authentication challenge.

```swift
final class PinningDelegate: NSObject, URLSessionDelegate {
    private let pinnedSPKIHashes: Set<String>   // base64 SHA-256 of the SPKI

    init(pinnedSPKIHashes: Set<String>) { self.pinnedSPKIHashes = pinnedSPKIHashes }

    func urlSession(_ session: URLSession,
                    didReceive challenge: URLAuthenticationChallenge) async
        -> (URLSession.AuthChallengeDisposition, URLCredential?) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let trust = challenge.protectionSpace.serverTrust,
              SecTrustEvaluateWithError(trust, nil)              // chain still validated against CAs first
        else { return (.cancelAuthenticationChallenge, nil) }

        guard let chain = SecTrustCopyCertificateChain(trust) as? [SecCertificate],
              let leaf = chain.first,
              let key = SecCertificateCopyKey(leaf),
              let spki = SecKeyCopyExternalRepresentation(key, nil) as Data?,
              pinnedSPKIHashes.contains(sha256Base64(spki))
        else { return (.cancelAuthenticationChallenge, nil) }

        return (.useCredential, URLCredential(trust: trust))
    }
}
```

Operational rules: pin at least two keys (the live key and a pre-provisioned backup) so a forced key rotation does not brick every installed app, validate the normal CA chain before checking the pin (pinning replaces nothing it adds to it), and ship a remote kill-switch or short pin-expiry so a botched rotation is recoverable without an App Store release. Apple's `NSPinnedDomains` Info.plist key offers declarative pinning, but the code path above gives you the backup-pin and kill-switch logic that bare declarative pinning lacks.

## Background URLSession

Use a background session for large or long uploads/downloads that must continue after the app is suspended or terminated (asset sync, video upload, model download), not for ordinary API calls. A background session needs a unique, stable identifier, must use the delegate API (the async `data(for:)` form is not available for background transfers), and may only enqueue tasks created from a file or URL, not from in-memory `Data`.

```swift
let config = URLSessionConfiguration.background(withIdentifier: "com.example.app.bg-upload")
config.isDiscretionary = false          // true => OS waits for Wi-Fi + power
config.sessionSendsLaunchEvents = true  // relaunch app on completion
let session = URLSession(configuration: config, delegate: handler, delegateQueue: nil)
session.uploadTask(with: request, fromFile: fileURL).resume()
```

On iOS, persist the completion handler from `application(_:handleEventsForBackgroundURLSession:completionHandler:)` (or the SwiftUI `.backgroundTask` / scene equivalent), then call it from `urlSessionDidFinishEvents(forBackgroundSession:)` so the system can snapshot and suspend the app cleanly; failing to call it gets the app killed. Recreate the session with the same identifier on relaunch to reattach to in-flight tasks. Secrets the background session needs (a bearer token in the request header) must live under `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`, since the transfer can complete while the device is locked.

## Common pitfalls

- A `URLSession` per request, or `URLSession.shared` for an authenticated API: you cannot pin, set a delegate, or tune timeouts. Reject; reuse one configured session per backend.
- Trusting `(data, response)` as success without casting to `HTTPURLResponse` and checking the status code; a 500 with an error body is delivered as a non-throwing result.
- Retrying a non-idempotent POST with no idempotency key, double-charging or double-posting on a flaky network.
- Retry loops with no cap, no backoff, or no jitter, hammering a degraded backend and draining the battery.
- `NSAllowsArbitraryLoads = true` to silence an ATS error; it disables transport security app-wide and is rejected in review. Scope exceptions per domain.
- Tokens or keys in `UserDefaults`, a plist, a file, the bundle, or `Info.plist`; all are readable from a backup or an unzipped `.ipa`.
- `kSecAttrAccessibleAlways` or any non-`ThisDeviceOnly` accessible level for a secret, leaving it in iCloud sync and encrypted backups.
- Biometric items created with `.biometryAny` instead of `.biometryCurrentSet`, so adding a fingerprint or face silently widens access.
- Pinning the leaf certificate instead of the SPKI, with a single pin and no backup, bricking the app at the next certificate renewal.
- Pinning that replaces CA chain validation rather than running after it, accepting a self-signed cert whose key happens to match.
- A background session built but its system completion handler never invoked, getting the app terminated and transfers orphaned.
- Treating a cancelled request as an error and surfacing an alert when the user simply navigated away.

## Definition of done

- [ ] All network calls use async/await `URLSession` on a reused, per-backend configured session; `URLSession.shared` is not used for authenticated traffic.
- [ ] Responses are validated against `HTTPURLResponse` status codes and mapped to a single typed error; cancellation is handled distinctly from failure.
- [ ] Retries are bounded (3 attempts), use exponential backoff with jitter, honor `Retry-After`, and run only for idempotent requests or POSTs with an idempotency key.
- [ ] ATS is left on; any exception is scoped to a named domain with a written justification, and no `http://` or global arbitrary-loads switch ships.
- [ ] Tokens, keys, and secrets live in the Keychain with the tightest viable `kSecAttrAccessible` level, using `...ThisDeviceOnly` to exclude iCloud sync and backups.
- [ ] Secrets protecting money or identity carry a `SecAccessControl` with `.biometryCurrentSet`; asymmetric keys are generated in the Secure Enclave.
- [ ] No API key, client secret, or token appears in `Info.plist`, `.xcconfig`, source, or the binary; embedded third-party keys are fetched at runtime and stored in the Keychain.
- [ ] High-value endpoints pin the SPKI (SHA-256) after standard CA validation, with at least one backup pin and a kill-switch or short pin expiry.
- [ ] Background transfers use a uniquely identified background session with a delegate, file-based tasks, and a system completion handler that is always invoked; their secrets use `AfterFirstUnlockThisDeviceOnly`.
- [ ] Tests cover status-code branching, retry/backoff limits, decoding failures, Keychain round-trips, and pin acceptance/rejection, with the network mocked via `URLProtocol`.
