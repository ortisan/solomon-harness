---
name: app-distribution-and-signing
description: Governs code-signing identities, provisioning profiles and entitlements, fastlane match/gym/pilot automation, build-number policy, TestFlight delivery, and macOS notarization for Apple platforms. Use when configuring release signing, automating a TestFlight or App Store upload, or troubleshooting a signing, provisioning, or notarization failure.
---

# App Distribution and Signing

Ship signed, notarized Apple builds through a reproducible pipeline where signing identities are shared across the team rather than minted per developer, build numbers increase monotonically, and every artifact is verified before it reaches App Store Connect. Treat code signing as a supply-chain boundary: the identity, the entitlements, and the provisioning profile together decide what the binary is allowed to do, so they belong in version control and CI, not in a developer's keychain.

Reference baseline (2026): Xcode 17.x, Swift 6.2, the iOS 26 / macOS 26 SDKs, `notarytool` (bundled since Xcode 13; `altool` notarization was removed in November 2023), and fastlane 2.227.x. `xcrun stapler`, `codesign`, and `spctl` ship with the Command Line Tools.

## Signing identities and certificates

Apple issues unified certificate types: `Apple Development` (run on device, debug) and `Apple Distribution` (App Store and Ad Hoc) for iOS/tvOS/watchOS/visionOS apps, plus `Developer ID Application` and `Developer ID Installer` for macOS software distributed outside the App Store. An account is capped at 2 active distribution certificates, which is exactly why each engineer should not generate their own — you exhaust the slots and CI cannot rebuild a profile.

- The private key lives only on the machine that created the CSR. Lose it and the certificate is useless; you revoke and reissue. This is the single most common reason a release stalls, and the reason a shared, encrypted identity store (fastlane match, below) exists.
- Authenticate CI and tooling with an App Store Connect API key (a `.p8` file plus Key ID and Issuer ID, generated under Users and Access > Integrations). It replaces an Apple ID + app-specific password, supports no interactive 2FA prompt, and is scoped by role. Download the `.p8` once; it cannot be retrieved again.
- Store the `.p8`, Key ID, and Issuer ID as CI secrets, never in the repo. Treat them as credentials with the same hygiene as a signing key.

## Provisioning profiles and entitlements

A provisioning profile binds an App ID, a certificate, entitlements, and (for development/Ad Hoc) a device list. The profile must contain a certificate whose private key is present at sign time, or signing fails with "no signing certificate found".

Entitlements are the capabilities the binary requests; they must be enabled on the App ID and present in the profile, or the App Store and the OS reject the app at install or review.

```xml
<!-- App.entitlements -->
<dict>
  <key>aps-environment</key>
  <string>production</string>                <!-- must be "production" for App Store/TestFlight -->
  <key>com.apple.security.application-groups</key>
  <array><string>group.com.example.app</string></array>
  <key>com.apple.developer.associated-domains</key>
  <array><string>applinks:example.com</string></array>
</dict>
```

- `aps-environment` set to `development` is the classic TestFlight push failure: the production push gateway silently drops tokens minted against the sandbox. App Store/TestFlight builds require `production`.
- macOS distribution requires the Hardened Runtime entitlements set (`com.apple.security.cs.*`) plus any exceptions the app genuinely needs (JIT, disabled library validation). Each exception you add weakens the runtime, so justify it.
- Ship a `PrivacyInfo.xcprivacy` privacy manifest. Since May 1, 2024 the App Store rejects apps that call required-reason APIs (file timestamps, `UserDefaults`, disk space, system boot time) without a declared reason, and that bundle a listed third-party SDK without its manifest and signature.

## Automatic vs manual signing

Automatic signing (`-allowProvisioningUpdates`) lets Xcode create and refresh profiles on demand; it is fine for local development but non-deterministic for releases because the profile can change under you. Manual signing with a pinned profile is the rule for anything that ships.

```bash
# CI archive with manual signing and an explicit export config
xcodebuild -workspace App.xcworkspace -scheme App \
  -configuration Release -archivePath build/App.xcarchive archive \
  CODE_SIGN_STYLE=Manual \
  PROVISIONING_PROFILE_SPECIFIER="match AppStore com.example.app" \
  CODE_SIGN_IDENTITY="Apple Distribution"

xcodebuild -exportArchive -archivePath build/App.xcarchive \
  -exportPath build/ipa -exportOptionsPlist ExportOptions.plist \
  -authenticationKeyPath "$PWD/AuthKey.p8" \
  -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID"
```

```xml
<!-- ExportOptions.plist -->
<dict>
  <key>method</key><string>app-store-connect</string>  <!-- replaces the old "app-store" -->
  <key>signingStyle</key><string>manual</string>
  <key>teamID</key><string>ABCDE12345</string>
  <key>provisioningProfiles</key>
  <dict><key>com.example.app</key><string>match AppStore com.example.app</string></dict>
</dict>
```

Use automatic signing in Xcode Cloud (it manages cloud signing itself) and for developer machines; use manual, match-managed profiles everywhere a build is published.

## Build number and version management

Two keys drive every release. `CFBundleShortVersionString` (`MARKETING_VERSION`, e.g. `2.4.0`) is the user-facing version. `CFBundleVersion` (`CURRENT_PROJECT_VERSION`, the build number) must be unique and strictly increasing for a given marketing version — App Store Connect rejects re-uploading the same `(version, build)` pair with no useful error beyond "redundant binary upload".

- Derive the build number from CI, not by hand. Common deterministic sources: the CI run number, `git rev-list --count HEAD`, or one past the latest TestFlight build.
- `agvtool` requires `VERSIONING_SYSTEM = apple-generic`; with it, `agvtool new-version -all 412` rewrites every target.

```ruby
# fastlane: never collide with what TestFlight already has
build = latest_testflight_build_number(version: get_version_number) + 1
increment_build_number(build_number: build)
```

## fastlane: match, gym, pilot

fastlane is the standard automation. `match` solves identity sharing, `gym` (alias `build_app`) builds and exports the `.ipa`, `pilot` (alias `upload_to_testflight`) ships to TestFlight, and `deliver` (`upload_to_app_store`) ships metadata and the binary to review.

`match` stores one shared certificate and its profiles in an encrypted git repo (or S3/Google Cloud Storage), so every developer and CI runner reconstructs the same identity instead of minting their own. CI runs `readonly` so it never tries to create new certificates.

```ruby
# Fastfile
lane :beta do
  app_store_connect_api_key(
    key_id: ENV["ASC_KEY_ID"], issuer_id: ENV["ASC_ISSUER_ID"],
    key_filepath: "AuthKey.p8"
  )
  match(type: "appstore", readonly: is_ci, app_identifier: "com.example.app")
  increment_build_number(
    build_number: latest_testflight_build_number(app_identifier: "com.example.app") + 1
  )
  build_app(scheme: "App", export_method: "app-store-connect")
  upload_to_testflight(
    skip_waiting_for_build_processing: true,   # don't block the runner on Apple-side processing
    groups: ["beta-testers"]
  )
end
```

- Run `match nuke` only as a deliberate, coordinated action: it revokes the shared certificate and invalidates every profile and live build's ability to be rebuilt. Recovering means every machine re-fetches.
- Encrypt the match repo with a strong passphrase delivered as a CI secret (`MATCH_PASSWORD`). The repo holds private keys; a leak is a full signing compromise.
- Pin the fastlane version in the `Gemfile` and commit `Gemfile.lock`. A floating fastlane breaks builds when an Apple-side API or plugin shifts.

## App Store Connect and TestFlight

TestFlight is the beta channel and the staging gate before public release. Internal testers (up to 100, members of your team) get builds immediately with no review; external testers (up to 10,000 across groups) require a one-time Beta App Review per significant build. A processed build expires 90 days after upload.

- Set `ITSAppUsesNonExemptEncryption` in Info.plist (or answer export compliance once per version) so processing does not stall waiting on the encryption question.
- Use phased release for App Store rollouts (7-day ramp to 100%) so a regression hits a fraction of users before you pause it.
- Reserve expedited review for genuine emergencies; abusing it gets future requests deprioritized.
- Automate metadata, screenshots, and the privacy nutrition label through `deliver`/`upload_to_app_store` so the store listing is reviewable in git, not edited by hand in the web UI.

## Notarization for macOS

Any macOS app distributed outside the App Store must be signed with a Developer ID identity, built with the Hardened Runtime, and notarized, or Gatekeeper blocks it on first launch. Notarization is Apple's automated malware scan; stapling attaches the resulting ticket so the check passes offline.

```bash
# Sign with hardened runtime, secure timestamp, and no debug entitlement
codesign --force --options runtime --timestamp \
  --sign "Developer ID Application: Example Inc (ABCDE12345)" \
  --entitlements App.entitlements MyApp.app

# Store API-key credentials once, then submit and wait for the verdict
xcrun notarytool store-credentials "AC_NOTARY" \
  --key AuthKey.p8 --key-id "$ASC_KEY_ID" --issuer "$ASC_ISSUER_ID"
ditto -c -k --keepParent MyApp.app MyApp.zip
xcrun notarytool submit MyApp.zip --keychain-profile "AC_NOTARY" --wait

xcrun stapler staple MyApp.app                 # attach the ticket; staple the .dmg/.pkg you ship
spctl -a -vvv -t exec MyApp.app                # must report "accepted, source=Notarized Developer ID"
```

- Hardened Runtime is mandatory for notarization; a build without `--options runtime` is rejected. So is a binary carrying the `get-task-allow` entitlement (that is a debug build).
- Notarization requires a secure timestamp (`--timestamp`); offline signing without one fails.
- On failure, fetch the machine-readable report: `xcrun notarytool log <submission-id> --keychain-profile "AC_NOTARY"`. It names the exact unsigned or wrongly-signed nested binary.
- Staple the artifact users actually download (the `.dmg` or `.pkg`), not only the inner `.app`, so the ticket survives distribution.

## Xcode Cloud

Xcode Cloud is Apple's first-party CI. It manages signing in the cloud (no match needed for its own builds) and runs custom logic through executable scripts in a `ci_scripts/` directory at the repo root: `ci_post_clone.sh`, `ci_pre_xcodebuild.sh`, `ci_post_xcodebuild.sh`. Builds expose `CI_*` environment variables.

```bash
#!/bin/sh
# ci_scripts/ci_pre_xcodebuild.sh — stamp the Apple-assigned build number
set -euo pipefail
cd "$CI_PRIMARY_REPOSITORY_PATH"
agvtool new-version -all "$CI_BUILD_NUMBER"
```

- The scripts must be marked executable (`chmod +x`) and committed, or Xcode Cloud skips them silently.
- Useful variables: `CI_BUILD_NUMBER`, `CI_BRANCH`, `CI_TAG`, `CI_XCODEBUILD_ACTION`, `CI_PRIMARY_REPOSITORY_PATH`. Branch and tag rules on the workflow decide what triggers a build, archive, and TestFlight delivery.
- Xcode Cloud bills compute hours against your plan; gate expensive archive/test workflows to release branches and tags rather than every push.

## Distribution checklist

- Identities and profiles come from `match` (or an equivalent shared, encrypted store); no developer-minted distribution certificate is in the release path.
- Marketing version and build number are set deterministically by CI; the `(version, build)` pair is new to App Store Connect.
- Entitlements match the App ID, `aps-environment` is `production`, and a `PrivacyInfo.xcprivacy` manifest is present and accurate.
- The archive is exported with manual signing and a pinned profile; `codesign --verify --strict` and an entitlements dump are clean.
- macOS artifacts are Developer ID-signed with Hardened Runtime, notarized, stapled, and pass `spctl -a`.
- Export compliance is answered; screenshots, metadata, and the privacy label are current via `deliver`.

## Common pitfalls

- Per-developer distribution certificates that exhaust the 2-slot cap and leave CI unable to rebuild a profile. Use a shared match store.
- `aps-environment` left at `development` in a TestFlight/App Store build, so production push silently fails.
- Re-uploading the same `(version, build)` pair; App Store Connect rejects it. Build number must strictly increase per marketing version.
- Automatic signing in the release pipeline, so the profile changes non-deterministically between builds. Pin it.
- A missing or stale `PrivacyInfo.xcprivacy`, or a bundled SDK without its manifest, causing a required-reason-API rejection at review.
- macOS app signed without `--options runtime` or `--timestamp`, or still carrying `get-task-allow`; notarization rejects all three.
- Stapling the inner `.app` but shipping an unstapled `.dmg`, so users behind a firewall hit a Gatekeeper block.
- Committing the `.p8` API key or the match passphrase to the repo. Both are signing-grade secrets.
- Using `altool` for notarization (removed in 2023) instead of `notarytool`.
- `ci_scripts` files not marked executable, so Xcode Cloud skips version stamping without warning.

## Definition of done

- [ ] Signing identities and provisioning profiles are sourced from a shared, encrypted store (`match` or equivalent); CI runs `readonly` and no per-developer distribution cert is in the release path.
- [ ] Release builds use manual signing with a pinned profile and export via `ExportOptions.plist`; `codesign --verify --strict` passes and the entitlements dump matches the App ID.
- [ ] `MARKETING_VERSION` and the build number are set by CI from a deterministic source; the uploaded `(version, build)` pair is unique on App Store Connect.
- [ ] `aps-environment` is `production` for App Store/TestFlight, and a correct `PrivacyInfo.xcprivacy` (plus SDK manifests) is present; required-reason APIs are declared.
- [ ] App Store Connect access uses a `.p8` API key stored as a CI secret; no Apple ID password or key material is in the repo.
- [ ] macOS artifacts are Developer ID-signed with Hardened Runtime and a secure timestamp, notarized with `notarytool`, stapled, and verified with `spctl -a` reporting a Notarized Developer ID source.
- [ ] TestFlight delivery is automated (`upload_to_testflight`), export compliance is answered, and external-test builds account for Beta App Review and the 90-day expiry.
- [ ] Metadata, screenshots, and the privacy label are managed as code through `deliver`/`upload_to_app_store`.
- [ ] Xcode Cloud (if used) has executable `ci_scripts`, gates expensive workflows to release branches/tags, and stamps `CI_BUILD_NUMBER`.
