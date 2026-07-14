---
name: privacy-and-app-store-compliance
description: Governs the PrivacyInfo.xcprivacy manifest, required-reason API declarations, App Tracking Transparency consent, App Store Connect nutrition labels, and permission usage-description strings. Use when adding a Required Reason API, third-party SDK, or tracking feature, or when preparing an Apple app for App Store privacy review.
---

# Privacy and App Store Compliance

App Review rejects a build for privacy reasons before it ever reaches users, so treat the privacy manifest, tracking consent, nutrition labels, and usage strings as release-blocking deliverables that must be true, minimal, and mutually consistent. Declare only the data you actually collect, request only the permissions you actually use, and make the App Store Connect labels, the `PrivacyInfo.xcprivacy` manifest, and the running code tell the same story; any divergence is grounds for rejection under the App Review Guidelines.

## Privacy manifest (PrivacyInfo.xcprivacy)

Since May 1, 2024 Apple rejects uploads that use Required Reason APIs, collect data, or bundle privacy-impacting SDKs without a privacy manifest. The manifest is a property list named exactly `PrivacyInfo.xcprivacy`, added to each target's bundle (app, app extensions, and every framework that touches the listed APIs). It has four top-level keys: `NSPrivacyTracking` (Bool), `NSPrivacyTrackingDomains` (array of strings), `NSPrivacyCollectedDataTypes` (array), and `NSPrivacyAccessedAPITypes` (array).

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>NSPrivacyTracking</key>
  <false/>
  <key>NSPrivacyTrackingDomains</key>
  <array/>
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
</plist>
```

Rules that decide acceptance:

- Third-party SDKs on Apple's privacy-impacting SDK list (Firebase/`FirebaseAnalytics`, `Alamofire`, `RxSwift`, and ~80 others) must ship their own manifest *and* be code-signed by the author. An unsigned or manifest-less version of a listed SDK fails upload validation. Pin to a version the vendor has signed.
- Generate the aggregated view before submission: Xcode Organizer, right-click the archive, "Generate Privacy Report" produces a PDF that merges every target's manifest into the labels you must mirror in App Store Connect. Diff that PDF against your nutrition-label answers.
- The manifest is per-target and additive. If a framework you embed accesses `NSPrivacyAccessedAPICategoryDiskSpace`, that reason must appear in *its* manifest, not only the app's.

## Required-reason APIs

Five API categories require a declared reason code; calling them without an approved reason is an automatic rejection:

- `NSPrivacyAccessedAPICategoryFileTimestamp` — reasons `DDA9.1` (show timestamps to the user), `C617.1` (timestamps inside the app/group/CloudKit container), `3B52.1` (files in the app bundle). Covers `stat`, `NSFileManager` attribute reads, `URLResourceKey.contentModificationDateKey`.
- `NSPrivacyAccessedAPICategorySystemBootTime` — `35F9.1`, `8FFB.1` (measuring elapsed time via `systemUptime`/`mach_absolute_time`).
- `NSPrivacyAccessedAPICategoryDiskSpace` — `85F4.1` (display to user), `E174.1` (check free space before a write).
- `NSPrivacyAccessedAPICategoryActiveKeyboards` — `3EC4.1`, `54BD.1`.
- `NSPrivacyAccessedAPICategoryUserDefaults` — `CA92.1` (access values written by the same app), `1C8F.1` (App Group shared defaults).

Pick the narrowest accurate code. Reviewers cross-check that a generic `NSUserDefaults` use is not declared with a CloudKit reason. If no listed reason fits your use, you cannot use the API; restructure to avoid it.

## App Tracking Transparency

Any tracking — linking user/device data with data from other companies' apps, sites, or data brokers for ads or sharing with brokers — requires ATT consent (Guideline 5.1.2). Add `NSUserTrackingUsageDescription` to `Info.plist`, then call `ATTrackingManager.requestTrackingAuthorization` before reading the IDFA.

```swift
import AppTrackingTransparency
import AdSupport

func requestTracking() async {
    let status = await ATTrackingManager.requestTrackingAuthorization()
    switch status {
    case .authorized:
        let idfa = ASIdentifierManager.shared().advertisingIdentifier // real UUID
    case .denied, .restricted, .notDetermined:
        break // advertisingIdentifier stays all-zeros; do not track
    @unknown default:
        break
    }
}
```

- Without `.authorized`, `advertisingIdentifier` is `00000000-0000-0000-0000-000000000000`. Reading it does not bypass consent.
- The system prompt shows once per install and only while the app is `active`. Calling it from `applicationDidFinishLaunching` before the UI is foregrounded silently no-ops and leaves status `.notDetermined`. Request after onboarding, with an optional pre-prompt explaining value first.
- If `NSPrivacyTracking` is `true`, list every tracking endpoint in `NSPrivacyTrackingDomains`. On iOS 17+ the system blocks network connections to those domains until the user authorizes tracking, so a missing domain leaks data while consent is denied and a wrong domain breaks your own requests.
- You may not gate core app functionality on granting ATT, and may not offer incentives for consent (5.1.1). For attribution without the IDFA, use AdAttributionKit (the SKAdNetwork successor, iOS 17.4+).

## Privacy nutrition labels

Declared in App Store Connect under App Privacy, the labels render in three buckets: "Data Used to Track You", "Data Linked to You", and "Data Not Linked to You". For each of ~30 data types (contact info, identifiers, usage data, location, health, financial, etc.) you state whether you collect it, whether it is linked to identity, whether it is used for tracking, and the purposes (app functionality, analytics, product personalization, advertising). The labels must match what the binary actually does and what the `PrivacyInfo.xcprivacy` manifest declares. A network capture by the reviewer showing an undeclared identifier leaving the device is a hard rejection. Update the labels with every release whose data behavior changes; they are versioned with the app, not edited live.

## Permission usage-description strings

Every protected resource needs a purpose string in `Info.plist`. Requesting access without the matching key crashes the app on the spot (and the App Store static analyzer flags the missing key on upload). The common keys:

- `NSCameraUsageDescription`, `NSMicrophoneUsageDescription`
- `NSPhotoLibraryUsageDescription` (read), `NSPhotoLibraryAddUsageDescription` (write-only)
- `NSLocationWhenInUseUsageDescription`, `NSLocationAlwaysAndWhenInUseUsageDescription`
- `NSContactsUsageDescription`, `NSCalendarsFullAccessUsageDescription` (iOS 17+ split from write-only), `NSRemindersFullAccessUsageDescription`
- `NSFaceIDUsageDescription`, `NSBluetoothAlwaysUsageDescription`, `NSUserTrackingUsageDescription`, `NSHealthShareUsageDescription`

Purpose strings must be specific and truthful. "We need access to your photos" is rejected under 5.1.1; "Add a photo to your profile from your library" passes because it names the concrete benefit. For approximate-vs-precise location, request `.reducedAccuracy` by default and ask for one-shot full accuracy only when needed via `requestTemporaryFullAccuracyAuthorization(withPurposeKey:)`, backed by a `NSLocationTemporaryUsageDescriptionDictionary` entry.

```swift
let manager = CLLocationManager()
if manager.accuracyAuthorization == .reducedAccuracy {
    try? await manager.requestTemporaryFullAccuracyAuthorization(withPurposeKey: "Routing")
}
```

## Data minimization

The cheapest way to pass privacy review is to not collect the data. Prefer pickers that grant scoped, one-time access with no permission prompt:

- Photos: `PHPickerViewController` returns user-chosen images out of process and needs no `NSPhotoLibraryUsageDescription`. Only use the full `PHPhotoLibrary` API (and the usage string) when you genuinely need library-wide access; the limited-library prompt is the fallback, not the default.
- Contacts: `CNContactPickerViewController` returns a single user-selected contact with no `NSContactsUsageDescription` and no full-book access.
- Documents: `UIDocumentPickerViewController` / `fileImporter` for scoped file access instead of broad file-system entitlements.
- Process on device (Vision, Natural Language, Core ML, Speech with `requiresOnDeviceRecognition = true`) instead of shipping raw user content to a server.
- If you offer any third-party or social login, you must also offer an equivalent privacy-respecting option such as Sign in with Apple (Guideline 4.8), which can hide the real email via Private Email Relay; do not collect more than name and email at sign-up.

## App Review Guidelines that block release

- 5.1.1(i): a privacy policy URL is mandatory in App Store Connect and reachable in-app; it must list data collected, retention, and deletion.
- 5.1.1(v): apps that support account creation must offer in-app account deletion (not just deactivation, not "email us"), with the deletion entry point discoverable in the app.
- 5.1.2: no repurposing collected data, no tracking without ATT, honor the user's permission choices.
- 5.1.4 / Kids Category: no third-party analytics or advertising SDKs, no external links without a parental gate.
- 2.3.10 / metadata: screenshots and description must reflect actual functionality; no hidden or undocumented features.
- 3.1.1: digital goods consumed in-app must use In-App Purchase, not an external payment SDK.

## Common pitfalls

- Nutrition labels claim "Data Not Collected" while an embedded analytics SDK ships an identifier off-device; the reviewer's network capture rejects it.
- `requestTrackingAuthorization` called at launch before the app is foregrounded, so the prompt never shows and status stays `.notDetermined`; consent is silently never obtained.
- Reading `advertisingIdentifier` and assuming a value; it is all-zeros without ATT authorization, so attribution silently breaks.
- A Required Reason API used by an embedded framework but the reason declared only in the app's manifest, not the framework's, failing upload validation.
- An updated version of a listed third-party SDK that the vendor has not yet signed or shipped a manifest for; the build is rejected at upload, not review.
- Generic usage strings ("needs access to camera") rejected under 5.1.1; the string must name the concrete user-facing purpose.
- Account creation supported but no in-app deletion path, violating 5.1.1(v).
- `NSPrivacyTracking` true with an incomplete `NSPrivacyTrackingDomains` list, so on iOS 17+ either undeclared domains leak under denied consent or a misspelled domain blocks legitimate traffic.
- Requesting precise location at full accuracy when reduced accuracy plus a temporary upgrade would do, drawing a data-minimization rejection.
- Third-party login offered with no Sign in with Apple or equivalent, violating 4.8.

## Definition of done

- [ ] A `PrivacyInfo.xcprivacy` manifest exists in the app and in every embedded target that touches a Required Reason API or collects data, with accurate reason codes and data types.
- [ ] Every embedded SDK on Apple's privacy-impacting list is on a vendor-signed version that bundles its own manifest; upload validation passes.
- [ ] The Xcode-generated privacy report PDF matches the App Store Connect nutrition labels and the running binary's actual behavior.
- [ ] All tracking uses ATT: `NSUserTrackingUsageDescription` set, authorization requested while foregrounded after onboarding, IDFA read only when `.authorized`, and `NSPrivacyTrackingDomains` complete when `NSPrivacyTracking` is true.
- [ ] Every protected resource has a specific, truthful purpose string; no permission is requested that the feature set does not use.
- [ ] Photos/contacts/files use scoped pickers (`PHPickerViewController`, `CNContactPickerViewController`, document picker) wherever full access is not required; location defaults to reduced accuracy.
- [ ] A reachable privacy policy is linked in App Store Connect and in-app; account-creating apps expose an in-app account-deletion path.
- [ ] If any third-party login is offered, Sign in with Apple or an equivalent privacy option is also offered.
- [ ] Nutrition labels are reviewed and updated for any release whose data collection, linkage, tracking, or purpose changed.
