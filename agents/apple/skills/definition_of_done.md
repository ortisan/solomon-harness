# Apple Definition of Done

An Apple-platform change is done only when every gate below holds on a clean machine and in CI, not when the feature works once on the author's simulator. Treat the Definition of Done as a hard merge gate: tests green (Swift Testing, XCTest, and XCUITest), SwiftLint clean in strict mode, zero concurrency diagnostics under the Swift 6 language mode, a present and correct privacy manifest, a reproducible signed archive, an accessibility pass, no secrets in the tree, and the design decision persisted to project memory. Each gate maps to a concrete command with an exit code, so "it builds" is never the bar.

Baseline toolchain for these rules: Xcode 26 (Swift 6.2), targeting the iOS 26 / macOS 26 SDK family. Pin the toolchain in CI with `xcodes` or `DEVELOPER_DIR` so every run uses the same compiler; a green build on a newer local Xcode that fails the CI toolchain is not done.

## Test gates: Swift Testing, XCTest, XCUITest

Run the full suite through `xcodebuild` with a fixed destination so results are reproducible. Use a pinned simulator OS, not "latest".

```bash
xcodebuild test \
  -scheme App \
  -destination 'platform=iOS Simulator,name=iPhone 17,OS=26.0' \
  -resultBundlePath build/Result.xcresult \
  -enableCodeCoverage YES \
  -skipMacroValidation \
  | xcbeautify
```

- Swift Testing (bundled since Xcode 16, the default for new unit tests) uses `@Test`/`#expect`/`#require`, `@Suite`, parameterized cases, and traits. Prefer it for new logic; `#require` short-circuits like a precondition, `#expect` records and continues.

```swift
import Testing
@testable import App

@Suite struct PriceFormatterTests {
    @Test(arguments: [(0.0, "$0.00"), (1234.5, "$1,234.50")])
    func formats(_ input: Double, _ expected: String) throws {
        let vm = try #require(PriceFormatter(locale: .init(identifier: "en_US")))
        #expect(vm.string(input) == expected)
    }
}
```

- Keep legacy XCTest where it already exists or where Swift Testing has no equivalent (performance tests via `measure`, some UI hooks). The two frameworks run in the same test bundle and the same `xcodebuild test` invocation; do not rewrite passing XCTest just to convert it.
- XCUITest covers user flows. Gate flaky UI tests on idling, not `sleep`: wait on `expectation(for: exists, evaluatedWith: element)` or `element.waitForExistence(timeout: 5)`.
- Coverage is a signal, not a vanity number. Set a per-target floor (commonly 70-80% on the model/view-model layer; UI layers run lower) and fail the build when a change drops it. Parse `xccov view --report --json build/Result.xcresult` in CI rather than eyeballing the Xcode gutter.
- Async tests must not block the main actor or rely on wall-clock timing. Use `await confirmation { }` (Swift Testing) or `await fulfillment(of:)` (XCTest) instead of `Task.sleep`.

## Static analysis and lint: SwiftLint

`swiftlint` runs as a separate gate, not a build phase that silently warns. Use `--strict` so every warning is an error.

```bash
swiftlint lint --strict --config .swiftlint.yml
swiftlint analyze --strict --compiler-log-path build/xcodebuild.log   # whole-module analyzer rules
```

- The analyzer rules (`unused_declaration`, `unused_import`, `typesafe_array_init`) need a compiler log; produce it by capturing `xcodebuild build` output. Lint-only rules do not.
- Treat the SwiftLint config as code: pin the version (`.swiftlint.yml` plus a SwiftPM/Mint/Homebrew pin) so a developer's newer SwiftLint cannot pass locally while CI fails. Disable rules in the config with a reason comment, never with scattered `// swiftlint:disable` lines that outlive their cause.
- If the project uses `swift-format` instead, the equivalent gate is `swift format lint --strict --recursive Sources`. Pick one formatter/linter and enforce it; do not run two with conflicting rules.

## Swift 6 concurrency: zero warnings under the language mode

The build must compile under the Swift 6 language mode with complete concurrency checking and no data-race warnings. This is the gate that catches actor-isolation and `Sendable` bugs before they ship as intermittent crashes.

```
// Build settings
SWIFT_VERSION = 6.0
SWIFT_STRICT_CONCURRENCY = complete
SWIFT_TREAT_WARNINGS_AS_ERRORS = YES
```

For SwiftPM targets, set it per target so the gate is in source control:

```swift
.target(
    name: "App",
    swiftSettings: [
        .swiftLanguageMode(.v6),
        .treatAllWarnings(as: .error),
    ]
)
```

- Do not silence races with `@unchecked Sendable` or `nonisolated(unsafe)` to make the build pass. Each use is a manual promise that you have a lock or single-thread guarantee; a reviewer should reject one that has neither.
- UI types stay on `@MainActor`; move CPU or I/O work to actors or `Task.detached` and hop back. A `@Observable` view model touched from a background task without isolation is the most common race this gate catches.
- If a third-party dependency is not yet `Sendable`-clean, isolate it behind your own actor or a `@MainActor` wrapper rather than dropping the whole target back to the Swift 5 mode. Per-module opt-in (`.enableUpcomingFeature`) is acceptable for a dependency you do not control; the app target ships at `.v6`.

## Privacy manifest and required-reason APIs

A `PrivacyInfo.xcprivacy` file must be present in the app target and in every bundled SDK that Apple lists, and it must be accurate. App Store Connect rejects uploads that use a required-reason API without a declared reason, and the data-collection keys must match what the app actually does.

```xml
<dict>
  <key>NSPrivacyTracking</key><false/>
  <key>NSPrivacyTrackingDomains</key><array/>
  <key>NSPrivacyCollectedDataTypes</key>
  <array>
    <dict>
      <key>NSPrivacyCollectedDataType</key>
      <string>NSPrivacyCollectedDataTypeCrashData</string>
      <key>NSPrivacyCollectedDataTypeLinked</key><false/>
      <key>NSPrivacyCollectedDataTypeTracking</key><false/>
      <key>NSPrivacyCollectedDataTypePurposes</key>
      <array><string>NSPrivacyCollectedDataTypePurposeAppFunctionality</string></array>
    </dict>
  </array>
  <key>NSPrivacyAccessedAPITypes</key>
  <array>
    <dict>
      <key>NSPrivacyAccessedAPIType</key>
      <string>NSPrivacyAccessedAPICategoryUserDefaults</string>
      <key>NSPrivacyAccessedAPITypeReasons</key>
      <array><string>CA92.1</string></array>
    </dict>
  </array>
</dict>
```

- The required-reason categories are fixed: file-timestamp APIs, system boot time, disk space, active keyboard, and `UserDefaults`. If the code calls one (directly or through a dependency), the matching category with a valid reason code must appear, or the upload bounces.
- `NSPrivacyTrackingDomains` must list every domain you reach while tracking; if `NSPrivacyTracking` is `true` the array cannot be empty. SDKs Apple flags must also ship a signature (`.signature`) alongside their manifest, so prefer SDK versions that include both.
- Verify, do not assume. `Privacy Report` from a built `.xcarchive` (Xcode > Product > Archive > Generate Privacy Report) aggregates every bundled manifest into the PDF you submit; generate it and confirm it matches reality before release.

## Archive, signing, and notarization

A clean checkout must produce a signed, exportable archive non-interactively. Manual "it signs on my Mac" is not done.

```bash
xcodebuild archive \
  -scheme App -configuration Release \
  -archivePath build/App.xcarchive \
  -destination 'generic/platform=iOS' \
  CODE_SIGN_STYLE=Manual

xcodebuild -exportArchive \
  -archivePath build/App.xcarchive \
  -exportOptionsPlist ExportOptions.plist \
  -exportPath build/export
```

- Prefer cloud-managed signing assets (`xcodebuild ... -allowProvisioningUpdates` with an App Store Connect API key, or `fastlane match` with a read-only certificates repo) so secrets never sit on a developer laptop. CI signs with a temporary keychain it creates and deletes per run.
- macOS apps distributed outside the App Store must notarize and staple, not just sign:

```bash
xcrun notarytool submit build/export/App.zip --keychain-profile AC_NOTARY --wait
xcrun stapler staple build/export/App.app
codesign --verify --deep --strict --verbose=2 build/export/App.app
spctl --assess --type execute --verbose build/export/App.app
```

- Confirm the build is uploadable end to end with `xcrun altool`/`notarytool` or a TestFlight upload in CI, not only that the archive exists. A successful local archive that App Store Connect rejects for an entitlement or manifest mismatch has not met the gate.

## Accessibility

Accessibility is a checked gate, not a hope. Xcode's automated audit catches the common defects; manual VoiceOver covers what it cannot.

```swift
func testHomeAccessibility() throws {
    let app = XCUIApplication()
    app.launch()
    try app.performAccessibilityAudit()   // contrast, hit-region, clipped text, missing labels
}
```

- `performAccessibilityAudit()` (Xcode 15+) fails the test on insufficient contrast, dynamic-type clipping, hit regions under 44x44 pt, and unlabeled interactive elements. Scope it with an options set when a known platform control trips a false positive, with a comment, rather than deleting the call.
- Every actionable non-text element needs an `accessibilityLabel`; decorative images are hidden with `.accessibilityHidden(true)`. Group related views with `.accessibilityElement(children: .combine)` so VoiceOver reads a coherent unit.
- Verify Dynamic Type up to the largest accessibility size (`AX5`) without truncation or overlap; never hard-code font sizes that ignore the user's setting. Run one manual VoiceOver pass on the primary flow before sign-off; the audit does not judge whether the spoken order makes sense.

## Secret hygiene

No credential, API key, certificate, or `.p12` belongs in the repository or the app bundle.

- Keep configuration in `.xcconfig` files that are git-ignored for the secret values, inject keys at build time from CI environment variables, and store user secrets at runtime in the Keychain (`kSecAttrAccessibleWhenUnlockedThisDeviceOnly`), never `UserDefaults` or a plist.
- Run a secret scanner in CI and as a pre-commit hook: `gitleaks detect --redact --no-banner` (and `git-secrets` for AWS-pattern keys). A non-zero exit blocks the merge.
- Anything embedded in the app binary is extractable; a "secret" shipped in `Info.plist` or a string literal is already public. If a real secret must reach the device, it comes from a server after authentication, not from the bundle.

## Decision persistence

A non-trivial Apple change records the design decision in project memory before it is considered done, so the next agent sees why an architecture (for example SwiftData over Core Data, or actor isolation boundaries) was chosen. Persist it via the `solomon-memory` MCP `save_decision` tool (or `python agents/apple/main.py`), capturing the choice, the alternatives weighed, and the constraint that settled it. An undocumented architectural decision is an incomplete one.

## Common pitfalls

- "Tests pass" claimed from Xcode's UI while CI runs a different simulator OS or toolchain; pin the destination and `DEVELOPER_DIR`, and treat the CI result as authoritative.
- SwiftLint run without `--strict`, so warnings accumulate and the gate quietly erodes. Strict mode or it does not count.
- Swift 6 races silenced with `@unchecked Sendable` or `nonisolated(unsafe)` to turn the build green; this hides the data race instead of fixing it. Reject without a documented lock or single-thread guarantee.
- Privacy manifest copied from a template and never reconciled with actual API use, so a `UserDefaults` or file-timestamp call ships without its required reason and App Store Connect rejects the upload.
- Archive signs interactively on the author's machine but fails in CI because signing assets are not in source-controlled, automatable form.
- macOS app signed but not notarized/stapled, so Gatekeeper blocks it on first launch for end users.
- Accessibility "done" by glancing at the screen, with no `performAccessibilityAudit()` and no VoiceOver pass; unlabeled controls and AX5 truncation slip through.
- `Task.sleep`/`sleep` used to stabilize async or UI tests, producing flakiness that masks real timing bugs.
- API key committed in an `.xcconfig` value, `Info.plist`, or string literal "for now"; it is permanent once in history.

## Definition of done

- [ ] `xcodebuild test` is green for Swift Testing, XCTest, and XCUITest on a pinned simulator/OS, with no skipped or quarantined failing tests, and coverage at or above the agreed floor.
- [ ] `swiftlint lint --strict` and `swiftlint analyze --strict` (or the `swift format lint` equivalent) exit zero, with the linter version pinned.
- [ ] The app target builds under `SWIFT_VERSION = 6.0` with `SWIFT_STRICT_CONCURRENCY = complete` and warnings-as-errors, with no `@unchecked Sendable`/`nonisolated(unsafe)` added without a documented justification.
- [ ] `PrivacyInfo.xcprivacy` is present and accurate for the app and bundled SDKs; every required-reason API has a valid reason code, tracking domains are declared, and the archive's Privacy Report matches reality.
- [ ] A clean checkout produces a signed, exportable archive non-interactively; macOS builds outside the App Store are notarized and stapled, and `codesign --verify`/`spctl` pass.
- [ ] `performAccessibilityAudit()` passes, actionable elements have labels, and one manual VoiceOver + AX5 Dynamic Type pass on the primary flow is done.
- [ ] `gitleaks detect` (and pre-commit hook) exit clean; no keys, certificates, or `.p12` files are in the tree or bundle; runtime secrets live in the Keychain.
- [ ] The design decision is persisted to project memory via `save_decision` (choice, alternatives, deciding constraint).
