---
name: release-and-play-delivery
description: Governs Android App Bundle builds, Play App Signing and upload-key handling, versionCode/versionName policy, Play Console track promotion with staged rollout, in-app updates, and Android vitals monitoring. Use when preparing an Android release, configuring CI signing, or promoting a build through internal, closed, open, or production tracks.
---

# Release and Play Delivery

Ship Android releases as signed App Bundles through Play App Signing, with the upload key injected from CI and never committed, version numbers derived deterministically, and every promotion gated by a staged rollout that watches Android vitals before it widens. Treat the production track as the last stop of a track ladder (internal to closed to open to production), make crash and ANR rates a release gate rather than a post-mortem, and wire in-app updates so users on broken builds can be moved forward without waiting for organic adoption.

## App Bundle (AAB) and build configuration

The Android App Bundle (`.aab`) is the only accepted publishing format on Google Play; APKs are not accepted for new apps or updates. You upload one bundle and Play generates and signs per-device split APKs (by ABI, screen density, and language), so the download is smaller than a universal APK. Build with the Android Gradle Plugin (AGP) 8.7+ on Gradle 8.9+ (AGP 9.0 if you are on the 2026 stable line), target a current `compileSdk`/`targetSdk` (API 35 is the Play submission floor in 2026), and always shrink release builds.

```kotlin
// app/build.gradle.kts
android {
    buildTypes {
        release {
            isMinifyEnabled = true            // R8 code shrink + obfuscation
            isShrinkResources = true          // strip unused resources
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            ndk { debugSymbolLevel = "FULL" }  // native symbols travel inside the AAB
        }
    }
    bundle {
        language { enableSplit = true }
        density  { enableSplit = true }
        abi      { enableSplit = true }
    }
}
```

`./gradlew bundleRelease` produces `app/build/outputs/bundle/release/app-release.aab`. The AAB itself is not directly installable; use `bundletool` (1.17+) to materialize and run APKs the way Play would, which is the only honest pre-upload smoke test:

```bash
bundletool build-apks --bundle=app-release.aab --output=app.apks \
  --connected-device --ks=upload-keystore.jks --ks-key-alias=upload
bundletool install-apks --apks=app.apks   # installs the device-specific split set
```

Enable `debugSymbolLevel = "FULL"` so native (C/C++/NDK) stack traces symbolicate in Play vitals; without it native crashes show raw addresses. The R8 mapping file is uploaded separately (see Crashlytics) or carried by the bundle for Play's own deobfuscation.

## Signing: Play App Signing and keystore handling

Play App Signing splits the trust into two keys. The **app signing key** is held by Google and is what end-user devices verify; once enrolled you can never export it, and losing it is no longer fatal because Google holds it. The **upload key** is yours: you sign the AAB with it, Google verifies the upload, strips your signature, and re-signs with the app signing key. The upload key is replaceable through Play Console if compromised (request an upload key reset), so it is the only key your CI ever touches.

The upload keystore is a credential, not source. Never commit `.jks`/`.keystore` files, `keystore.properties`, or passwords. In CI, store the keystore as a base64-encoded secret and the four signing values as separate secrets, decode at build time, and read them from the environment so they never land in a tracked file.

```kotlin
// app/build.gradle.kts — reads only from the environment; falls back to no signing locally
android {
    signingConfigs {
        create("release") {
            val ksPath = System.getenv("ANDROID_KEYSTORE_PATH")
            if (ksPath != null) {
                storeFile = file(ksPath)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS")
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
            }
        }
    }
    buildTypes { release { signingConfig = signingConfigs.getByName("release") } }
}
```

```yaml
# GitHub Actions: decode the keystore from a secret, export it, build, then it is gone with the runner
- run: echo "$KEYSTORE_BASE64" | base64 -d > "$RUNNER_TEMP/upload.jks"
  env: { KEYSTORE_BASE64: "${{ secrets.ANDROID_KEYSTORE_BASE64 }}" }
- run: ./gradlew bundleRelease
  env:
    ANDROID_KEYSTORE_PATH: ${{ runner.temp }}/upload.jks
    ANDROID_KEYSTORE_PASSWORD: ${{ secrets.ANDROID_KEYSTORE_PASSWORD }}
    ANDROID_KEY_ALIAS: ${{ secrets.ANDROID_KEY_ALIAS }}
    ANDROID_KEY_PASSWORD: ${{ secrets.ANDROID_KEY_PASSWORD }}
```

Add `*.jks`, `*.keystore`, and `keystore.properties` to `.gitignore`, and run a secret scanner (gitleaks/trufflehog) in CI so a fat-fingered commit fails the build. If you migrate an existing app, enroll via the PEPK tool to upload the legacy signing key once; from then on rotate only the upload key.

## Versioning: versionCode and versionName

`versionCode` is an integer Play uses to order builds; every upload to a track must have a strictly higher `versionCode` than anything already there, and the ceiling is 2,100,000,000. `versionName` is the human string (`"4.12.0"`) shown to users and carries no ordering semantics. Derive `versionCode` deterministically from CI (monotonic build number or an encoded `MAJOR*10000 + MINOR*100 + PATCH`) so two builds never collide and a hotfix can always outrank the build it replaces.

```kotlin
android {
    defaultConfig {
        versionCode = (System.getenv("CI_BUILD_NUMBER") ?: "1").toInt()
        versionName = "4.12.0"
    }
}
```

With AABs there is exactly one `versionCode` per release. The legacy trick of multiplying `versionCode` per ABI (`x86` vs `arm64`) is obsolete and harmful: Play generates ABI splits from a single bundle, so per-ABI codes only fragment your update graph. Bump `versionName` per release and keep it in lockstep with your Git tag.

## Play Console tracks and staged rollout

Promote through four tracks, each widening the blast radius:

- **internal** — up to 100 named testers, available within minutes, skips most review. Use for every CI build.
- **closed** — invited testers or Google Groups (alpha); the place for QA and stakeholder sign-off.
- **open** — public opt-in beta, real-world device and locale coverage.
- **production** — all users; supports staged (percentage) rollout and managed publishing.

Closed and open tracks now require new personal-developer accounts to run a closed test with at least 12 testers for 14 days before production access unlocks, so budget that into the launch timeline. On production, never publish at 100% on day one. Start a staged rollout at 1-5%, hold while Android vitals settle, then step up (10% to 20% to 50% to 100%) over hours-to-days, watching the crash and ANR rates at each step. If a regression appears, **halt rollout** (freezes the percentage) or use Play's rollout halt to stop new devices receiving it; you cannot lower a percentage but you can halt and ship a fixed higher `versionCode`.

Automate uploads from CI with the Gradle Play Publisher plugin (`com.github.triplet.play` 3.12+) or fastlane `supply`, using a Google Cloud service account JSON (also a CI secret) scoped to the Play Developer API:

```kotlin
// build.gradle.kts (Gradle Play Publisher)
play {
    serviceAccountCredentials.set(file(System.getenv("PLAY_SERVICE_ACCOUNT_JSON")))
    track.set("internal")
    defaultToAppBundles.set(true)
    releaseStatus.set(ReleaseStatus.IN_PROGRESS)   // staged rollout
    userFraction.set(0.05)                          // 5%
}
```

```bash
./gradlew publishReleaseBundle      # uploads the AAB to the configured track
./gradlew promoteArtifact --from-track internal --promote-track production --release-status inProgress --user-fraction .10
```

Enable **managed publishing** for production so an approved release waits for your explicit "go", decoupling Play review from the moment users get the build.

## In-app updates

Use the Play In-App Update API (`com.google.android.play:app-update` and `app-update-ktx` 2.1+) to nudge or force users off stale builds without leaving the app. Two flows: **immediate** (full-screen, blocking — for critical or security fixes) and **flexible** (background download, then a prompt to restart — for routine updates). Drive the choice from the update priority you set when publishing (0-5) and from `clientVersionStalenessDays`.

```kotlin
val manager = AppUpdateManagerFactory.create(context)
val info = manager.appUpdateInfo.await()   // ktx suspend

val critical = info.updatePriority() >= 4 ||
    (info.clientVersionStalenessDays() ?: 0) >= 14
if (info.updateAvailability() == UpdateAvailability.UPDATE_AVAILABLE) {
    val type = if (critical) AppUpdateType.IMMEDIATE else AppUpdateType.FLEXIBLE
    if (info.isUpdateTypeAllowed(type)) {
        manager.startUpdateFlowForResult(info, type, activityResultLauncher, AppUpdateOptions.defaultOptions(type))
    }
}
```

For flexible updates, register an `InstallStateUpdatedListener`, and when `installStatus == DOWNLOADED` show a prompt that calls `manager.completeUpdate()` so the user controls the restart. Always re-check `appUpdateInfo` in `onResume` to resume an interrupted immediate flow; an immediate update that the user backgrounded must be re-prompted or the app stays on a known-bad version. In-app update priority can only be set at publish time (via the Publishing API), not retroactively, so decide it per release.

## Crash and vitals monitoring

Android vitals in Play Console is the source of truth Google uses to rank and (above thresholds) demote your app. Watch the **user-perceived crash rate** and **user-perceived ANR rate**; the bad-behavior thresholds are **1.09%** for crashes and **0.47%** for ANRs (the fraction of daily-active users who saw at least one crash/ANR). Crossing them risks reduced Play visibility and a Play Console warning, so treat them as a hard rollout gate, not an aspiration. ANRs (5+ seconds of blocked main thread) are usually disk or network I/O on the UI thread or lock contention; profile with the Macrobenchmark library and the Perfetto trace, never with `Thread.sleep` workarounds.

Add Firebase Crashlytics for real-time, deobfuscated crash and ANR reporting that arrives faster and richer than vitals:

```kotlin
plugins {
    id("com.google.gms.google-services")
    id("com.google.firebase.crashlytics")    // 3.x
}
android {
    buildTypes {
        release {
            configure<CrashlyticsExtension> {
                mappingFileUploadEnabled = true     // auto-upload R8 mapping for deobfuscation
                nativeSymbolUploadEnabled = true     // symbolicate NDK crashes
            }
        }
    }
}
```

Set a stable, non-PII user identifier (`FirebaseCrashlytics.getInstance().setUserId(hashedId)`), attach release keys (build flavor, `versionName`), and log breadcrumbs around risky paths. Enforce mapping-file upload on every release build so production stack traces are not obfuscated noise. Crashlytics and Android vitals are complementary: Crashlytics gives you the fast, detailed signal during a staged rollout; vitals is what Play actually measures you against, so reconcile the two before widening.

## Release checklist

Run this gate before promoting to production:

1. `versionCode` strictly greater than the live build; `versionName` matches the Git tag.
2. Release built from a clean tagged commit, `isMinifyEnabled`/`isShrinkResources` on, R8 rules verified against a `bundletool`-installed split set on a real device.
3. AAB signed with the upload key from CI env vars; no keystore, password, or service-account JSON in the repo; secret scanner green.
4. Native debug symbols and R8 mapping present (in the AAB and/or uploaded to Crashlytics).
5. Internal and closed track validated; closed-test tenure requirement satisfied if your account needs it.
6. Staged rollout configured (start 1-5%), managed publishing on, rollback plan = halt + higher `versionCode` hotfix.
7. In-app update priority set for the release; immediate-flow resume tested.
8. Crashlytics dashboards and Android vitals watch in place with crash < 1.09% and ANR < 0.47% as the promotion gate.

## Common pitfalls

- Committing the keystore, `keystore.properties`, or the Play service-account JSON; reject any PR that adds `*.jks`/`*.keystore` or hardcodes signing passwords. These belong in CI secrets read from the environment.
- Trying to upload an APK, or signing the AAB with the app signing key. New uploads must be AABs signed with the upload key; Google holds the app signing key.
- Reusing or lowering a `versionCode`, or per-ABI `versionCode` multipliers on an App Bundle; Play rejects duplicates and the multiplier hack fragments updates.
- Shipping production at 100% immediately, with no staged rollout and no vitals watch, so a regression hits the whole base before you see it.
- Forgetting `debugSymbolLevel = "FULL"` and mapping upload, leaving native and obfuscated crashes unsymbolicated in vitals and Crashlytics.
- Treating a synced upload key as unrecoverable; it is resettable via Play Console, unlike the app signing key.
- An immediate in-app update flow that is never re-checked in `onResume`, leaving users stranded on a known-bad build after they background the prompt.
- Doing disk or network I/O on the main thread and discovering the ANR only after the 0.47% threshold demotes the listing.

## Definition of done

- [ ] Release artifact is an AAB built with `isMinifyEnabled`/`isShrinkResources`, validated through `bundletool` on a physical device, and `compileSdk`/`targetSdk` meet the current Play floor.
- [ ] Signing uses Play App Signing; the upload key and all passwords come from CI environment secrets, nothing key-related is tracked in Git, and a secret scanner gates the build.
- [ ] `versionCode` is monotonic and CI-derived with no per-ABI multipliers; `versionName` is human-readable and tied to the Git tag.
- [ ] Promotion follows internal to closed to open to production, with production using a staged rollout that starts at 1-5% and a documented halt-and-hotfix rollback.
- [ ] In-app updates are wired with priority/staleness-driven immediate vs flexible flows and an `onResume` re-check for interrupted immediate updates.
- [ ] Native debug symbols and the R8 mapping file are uploaded; Crashlytics reports deobfuscated, symbolicated crashes and ANRs with a stable non-PII user id.
- [ ] Android vitals are monitored and crash rate < 1.09% and ANR rate < 0.47% are enforced as the gate before each rollout step widens.
- [ ] The release checklist is completed and the decision plus version is logged to project memory.
