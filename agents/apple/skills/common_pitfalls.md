---
name: common-pitfalls
description: Governs the review checklist for Apple-platform defects that compile but fail at runtime, covering retain cycles, main-actor isolation violations, force-unwraps, unjustified Sendable suppression, missing privacy manifests, broad ATS exceptions, and Keychain misuse. Use when reviewing Swift or SwiftUI changes for memory leaks, concurrency races, crashes, or App Review rejection risk.
---

# Common Pitfalls

Reject the Apple-platform failure modes that compile cleanly but crash, leak, freeze the UI, or get the app rejected from App Review. This skill is the checklist a reviewer applies to Swift/SwiftUI changes: retain cycles, main-actor isolation violations, force-unwraps, ignored Sendable/concurrency diagnostics, a missing or wrong privacy manifest, broad ATS exceptions, Keychain misuse, and main-thread blocking. Each rule states the failure and the reason, with the current Swift 6.2 / Xcode 17 / iOS 26 behavior, so "it builds" is never the bar.

## Memory: retain cycles and capture lists

A retain cycle is two reference types holding strong references to each other, so neither deallocates and `deinit` never runs. The two recurring sources are closures that capture `self` strongly and delegate properties declared `strong` instead of `weak`.

```swift
// WRONG: the closure retains self, self retains the cancellable that owns the closure.
class Loader: ObservableObject {
    var cancellable: AnyCancellable?
    func start() {
        cancellable = publisher.sink { value in
            self.update(value)   // strong capture -> cycle
        }
    }
}

// RIGHT: break the cycle at the capture point.
cancellable = publisher.sink { [weak self] value in
    guard let self else { return }   // promote to strong for the call, drop after
    self.update(value)
}
```

Rules a reviewer enforces:

- Any escaping closure stored on an object (`Timer`, `URLSession` completion held in a property, Combine `sink`, `NotificationCenter` token-less observer) that references `self` must use `[weak self]` unless the closure provably outlives nothing. Non-escaping closures (`map`, `filter`, `forEach`) do not capture beyond the call and do not need it; adding `[weak self]` there is noise.
- Delegate and parent back-references are `weak var delegate:`. A `strong` delegate is the classic UIKit/coordinator cycle.
- Closure-based `Timer.scheduledTimer` retains its target until invalidated. Invalidate in `deinit` is too late because `deinit` never runs while the timer holds `self`; invalidate on the lifecycle event (`onDisappear`, `viewWillDisappear`).
- `Task { }` started from a class captures `self` strongly for the task's lifetime. A long-running `Task` (a `for await` loop over an `AsyncStream`) must use `[weak self]` or be stored and cancelled in `deinit`/`onDisappear`, or it pins the object alive.

Verify with Instruments. Use the Leaks and Allocations instruments and the Xcode Memory Graph Debugger ("Debug Memory Graph" button); purple runtime-issue badges flag cycles. With SwiftUI `@Observable`, watch view models retained by long-lived `Task`s past view teardown.

## Concurrency: main-actor isolation and the main thread

Swift 6 language mode (default for new targets in Xcode 16+, and what this project should adopt) turns data races into compile errors via actor isolation and `Sendable` checking. The failures to reject:

- UI mutation off the main actor. All `UIView`/`UIViewController`/`NSView` and SwiftUI view updates are `@MainActor`. Touching them from a background context is a crash or undefined rendering. In Swift 6 mode this is usually a compile error; do not silence it by sprinkling `@MainActor` casts.

```swift
// WRONG: network callback delivers on a background thread, mutates UI directly.
URLSession.shared.dataTask(with: url) { data, _, _ in
    self.label.text = String(decoding: data!, as: UTF8.self)  // off-main UI + force-unwrap
}.resume()

// RIGHT: hop to the main actor explicitly; do parsing off-main.
let (data, _) = try await URLSession.shared.data(from: url)
let text = String(decoding: data, as: UTF8.self)
await MainActor.run { self.label.text = text }   // or mark the method @MainActor
```

- `@MainActor` on a whole type when only the UI surface needs it. Annotate the view model or view layer, and keep pure compute (`Codable` decode, math, file parsing) off the main actor so it runs on the cooperative thread pool. Marking everything `@MainActor` reintroduces main-thread blocking through the back door.
- Long or synchronous work inside a `@MainActor` method. `await` does not move CPU-bound work off the main actor; it only suspends. Move heavy work to a non-isolated `async` function or a detached task: `await Task.detached { ... }.value` for genuinely independent CPU work, but prefer a non-`@MainActor` actor or free function so priority and cancellation propagate.
- `Task { @MainActor in ... }` used to "fix" an isolation warning without understanding ordering. Tasks are not FIFO; if order matters use an `actor` or an `AsyncStream`.

The hard rule: never block the main thread. No synchronous network I/O, no `Data(contentsOf: remoteURL)`, no `DispatchSemaphore.wait()` on main, no large synchronous file reads or `JSONDecoder` over multi-MB payloads on the main actor, no synchronous Core Data fetches on the view context for large result sets. The watchdog terminates an app that blocks the main thread for ~20 s at launch or during system events (exception code `0x8badf00d`); even 100 ms drops frames at 120 Hz ProMotion (each frame is 8.3 ms). Profile with the Time Profiler and the Hangs/Hitches instrument in Instruments; the Main Thread Checker (on by default in debug) catches UIKit/AppKit calls made off-main.

## Sendable and concurrency warnings are errors, not noise

In Swift 6 mode, `Sendable` violations are diagnostics you must resolve, not suppress. Migrating a target to Swift 6 by adding `-warnings-as-errors`-style suppression or scattering `@unchecked Sendable` defeats the model.

- A type shared across actor/task boundaries must be `Sendable`. Value types of `Sendable` members are inferred `Sendable`. Reference types must be immutable-with-`let`, an `actor`, or `@MainActor`-isolated to qualify.
- `@unchecked Sendable` is a manual promise that you serialize access yourself (a lock, a queue). Reject it unless the diff shows the synchronization (e.g. an `os_unfair_lock` / `NSLock` guarding every mutable field). An unjustified `@unchecked Sendable` is a hidden data race.
- Do not silence "non-sendable type crossing actor boundary" by capturing into a `nonisolated(unsafe)` variable. That keyword is an escape hatch for known-safe globals (a `let` constant computed once), not a way to pass mutable state between threads.
- `@preconcurrency import` is acceptable as a temporary bridge to a module not yet audited for concurrency; it is a TODO, not a resolution. Flag it if it hides a real cross-actor mutation.

## Force-unwrapping and unsafe optionals

Every `!` is a potential `EXC_BAD_INSTRUCTION` crash. Reject force-unwraps on any value the code did not just create and prove non-nil on the same line.

```swift
// WRONG: each ! is a crash site on bad input or a renamed asset.
let url = URL(string: userInput)!
let image = UIImage(named: "hdr")!
let first = items.first!

// RIGHT: handle absence explicitly.
guard let url = URL(string: userInput) else { return .failure(.badURL) }
let image = UIImage(named: "hdr") ?? .placeholder
guard let first = items.first else { return }
```

- Banned in practice: force-unwrapping `URL(string:)`, JSON/`Codable` results, `as!` downcasts on values you do not control, `try!`, dictionary subscripts, `Array.first/.last`, and IBOutlet chains beyond the outlet itself.
- Implicitly unwrapped optionals (`var x: Foo!`) are force-unwraps deferred to first access. Limit them to IBOutlets and two-phase init where the framework guarantees the value; never for model data.
- `as!` is a typed force-unwrap. Use `as?` with a `guard`. `try!` is acceptable only for a literal that cannot fail (a hardcoded regex `NSRegularExpression`, a bundled resource that is part of the build); document why.
- A `precondition`/`fatalError` for a genuine programmer error is fine and clearer than `!` because it carries a message; use it deliberately, not as a default.

## Privacy manifest and required-reason APIs

Since May 1, 2024, App Store submissions that use a covered API or include a listed third-party SDK must ship a privacy manifest, `PrivacyInfo.xcprivacy`, or App Review rejects the upload (ITMS-91053 / ITMS-91061). This is the most common avoidable rejection.

- `PrivacyInfo.xcprivacy` is a property list in the app/framework bundle declaring `NSPrivacyTracking`, `NSPrivacyTrackingDomains`, `NSPrivacyCollectedDataTypes`, and `NSPrivacyAccessedAPITypes` with a reason code for each required-reason API.
- Required-reason API categories that demand a declared reason: file timestamp (`stat`, `NSFileModificationDate`), system boot time (`systemUptime`, `mach_absolute_time`), disk space (`NSFileSystemFreeSize`), active keyboard list, and `UserDefaults`. Using `UserDefaults` with no declared reason (`CA92.1` for app-group access by the app itself) is a frequent rejection.

```xml
<key>NSPrivacyAccessedAPITypes</key>
<array>
  <dict>
    <key>NSPrivacyAccessedAPIType</key>
    <string>NSPrivacyAccessedAPICategoryUserDefaults</string>
    <key>NSPrivacyAccessedAPITypeReasons</key>
    <array><string>CA92.1</string></array>
  </dict>
</array>
```

- Listed "commonly used" third-party SDKs (Firebase, Alamofire, and the rest of Apple's published list) must ship their own manifest and, for the ~100 listed SDKs, a code signature; an outdated SDK version without one blocks the build. Pin SDK versions known to include the manifest.
- `NSPrivacyTracking = true` requires `NSUserTrackingUsageDescription` and the App Tracking Transparency prompt before any cross-app tracking; declaring tracking domains without the ATT flow is a rejection.
- Any data-access `Info.plist` usage string (`NSCameraUsageDescription`, `NSLocationWhenInUseUsageDescription`, `NSPhotoLibraryUsageDescription`) must be present and specific; a missing string crashes on first access, a vague string ("we need access") gets rejected. Keep these consistent with the manifest's `NSPrivacyCollectedDataTypes` and the App Store Connect privacy "nutrition label".

## App Transport Security exceptions

ATS requires TLS 1.2+ for all `URLSession`/`NSURLConnection` traffic by default. Broad opt-outs are both a security regression and an App Review risk that requires written justification.

- `NSAllowsArbitraryLoads = true` disables ATS for the entire app. Reject it. Apple requires a justification at review and will reject vague ones; it is rarely defensible in a shipping app.
- Scope any exception to the exact domain via `NSExceptionDomains`, and prefer fixing the server (enable TLS 1.2+, valid certificate, forward secrecy) over an exception.

```xml
<key>NSAppTransportSecurity</key>
<dict>
  <key>NSExceptionDomains</key>
  <dict>
    <key>legacy.internal.example.com</key>
    <dict>
      <key>NSExceptionMinimumTLSVersion</key>
      <string>TLSv1.2</string>
      <key>NSIncludesSubdomains</key>
      <false/>
    </dict>
  </dict>
</dict>
```

- `NSAllowsArbitraryLoadsInWebContent` for `WKWebView` and `NSAllowsLocalNetworking` for local/LAN dev are narrow, justified escapes; full arbitrary loads are not.
- For high-value endpoints, add certificate or public-key pinning via `URLSessionDelegate`'s `urlSession(_:didReceive:completionHandler:)` evaluating `SecTrust`, but pin to the SPKI hash with a backup pin so a rotation does not brick the app.

## Keychain and secret storage

`UserDefaults` and plist files are plaintext in the app container; never store tokens, passwords, or keys there. Use the Keychain (Security framework, or a vetted wrapper) and pick the right accessibility and protection.

```swift
let query: [String: Any] = [
    kSecClass as String: kSecClassGenericPassword,
    kSecAttrService as String: "com.example.app.tokens",
    kSecAttrAccount as String: "refresh_token",
    kSecValueData as String: tokenData,
    // Most restrictive that still fits the use case:
    kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
]
SecItemDelete(query as CFDictionary)            // avoid errSecDuplicateItem
let status = SecItemAdd(query as CFDictionary, nil)
guard status == errSecSuccess else { throw KeychainError.unhandled(status) }
```

- Default to `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`. `...ThisDeviceOnly` keeps the secret out of iCloud Keychain and encrypted backups; the non-`ThisDeviceOnly` variants migrate to a new device, which is wrong for device-bound tokens. `kSecAttrAccessibleAlways` is deprecated; reject it.
- For secrets that must be present in the background (a sync token), use `...AfterFirstUnlockThisDeviceOnly`, not `Always`.
- Gate high-value secrets behind biometrics with `SecAccessControl` (`kSecAttrAccessControl`, flags `.biometryCurrentSet` or `.userPresence`) so adding a fingerprint/face invalidates the item. Pair with `LAContext`; handle the `LAError` cases (`.userCancel`, `.biometryLockout`, `.biometryNotEnrolled`) rather than force-unwrapping the result.
- Do not hardcode API keys, signing secrets, or credentials in source, `Info.plist`, or the asset catalog; they ship in the binary and are trivially extracted. Use a backend, Keychain, or build-time injection that does not land in the bundle.
- `SecItemAdd` returns `errSecDuplicateItem` on an existing item; update with `SecItemUpdate` or delete-then-add. Always check the `OSStatus`; a silently failed write means the token was never stored.

## Common pitfalls

- Escaping closure or long-lived `Task` stored on an object capturing `self` strongly: a retain cycle that keeps view models alive after teardown. Use `[weak self]`.
- `strong` delegate or parent back-reference instead of `weak`: the classic coordinator/UIKit cycle.
- UI mutation (`label.text`, SwiftUI state) from a network/background callback: crash or corrupted rendering off the main actor. Hop with `await MainActor.run` or mark `@MainActor`.
- Whole type marked `@MainActor` so `Codable` decode and CPU work run on the main thread, dropping frames; keep compute off-main.
- Synchronous I/O on the main thread (`Data(contentsOf:)` on a remote URL, `DispatchSemaphore.wait()`, large `JSONDecoder` on the view context): watchdog kill `0x8badf00d` or hitches at 120 Hz.
- `@unchecked Sendable` or `nonisolated(unsafe)` added to silence a Swift 6 diagnostic with no visible lock or serialization: a hidden data race.
- `@preconcurrency import` left as a permanent fix instead of a tracked TODO over an unaudited cross-actor mutation.
- Force-unwrap on external input (`URL(string:)!`, `Codable` result, `as!`, `try!`, `.first!`): `EXC_BAD_INSTRUCTION` on bad data.
- Implicitly unwrapped optional (`var model: Foo!`) used for model state rather than IBOutlets/two-phase init.
- Missing `PrivacyInfo.xcprivacy` or an undeclared required-reason API (`UserDefaults`, file timestamp, boot time, disk space): App Review rejection ITMS-91053.
- Third-party SDK without its own privacy manifest/signature, or a missing `Info.plist` usage string: rejection or first-access crash.
- `NSAllowsArbitraryLoads = true` instead of a domain-scoped `NSExceptionDomains` entry: app-wide TLS opt-out and a review block.
- Tokens or keys in `UserDefaults`, a plist, the asset catalog, or hardcoded in source: plaintext secrets extractable from the bundle.
- Keychain item with `kSecAttrAccessibleAlways` or a non-`ThisDeviceOnly` accessibility for a device-bound token, or an unchecked `OSStatus` so the write silently fails.

## Definition of done

- [ ] No new strong-capture cycles: escaping closures, stored `Task`s, and timers that reference `self` use `[weak self]` or are invalidated/cancelled on the lifecycle event; delegates are `weak`. Verified in the Memory Graph Debugger with no leaks.
- [ ] All UI access is on the main actor; the target builds clean in Swift 6 language mode with the Main Thread Checker enabled and no isolation warnings silenced.
- [ ] No `@unchecked Sendable`, `nonisolated(unsafe)`, or `@preconcurrency import` without a visible synchronization mechanism or a tracked follow-up.
- [ ] No force-unwraps, `as!`, or `try!` on external or model data; IUOs limited to IBOutlets/two-phase init.
- [ ] No synchronous network or large file/JSON work on the main thread; CPU-bound work runs off the main actor. Time Profiler/Hangs instrument shows no main-thread hangs over one frame.
- [ ] `PrivacyInfo.xcprivacy` is present with reasons for every required-reason API used; bundled SDKs ship their manifests; `Info.plist` usage strings exist and match the App Store privacy details.
- [ ] ATS is on with no app-wide `NSAllowsArbitraryLoads`; any exception is domain-scoped and justified.
- [ ] Secrets live in the Keychain with the most restrictive `...ThisDeviceOnly` accessibility that fits, high-value items gated by `SecAccessControl`/biometrics; no credentials in `UserDefaults`, plists, the asset catalog, or source; every `SecItem*` `OSStatus` is checked.
