---
name: build-tooling-and-ci-gates
description: Governs Gradle version catalogs, convention plugins, KSP, R8 keep rules, ktlint/detekt static analysis, dependency verification, and branch-specific CI gates for Android builds. Use when configuring Gradle build logic, adding a dependency, wiring CI checks, or reviewing a release build's shrinking and signing setup.
---

# Build Tooling and CI Gates

Make the build reproducible, the dependency graph declarative, and the release path gated so that no unverified, un-shrunk, or unlinted artifact reaches a protected branch. Treat the Gradle build logic as production code: a single version catalog as the source of truth, convention plugins instead of copy-pasted module config, R8 full mode for every release, and a CI pipeline whose required checks differ by branch type.

## Gradle and version catalogs

Standardize on Gradle 8.14+ (or 9.x), AGP 8.11+, Kotlin 2.2.x with the K2 compiler, and the Kotlin DSL (`.gradle.kts`) for every script. Pin Gradle itself in `gradle/wrapper/gradle-wrapper.properties` with `distributionSha256Sum` so a tampered wrapper distribution fails verification, and commit `gradlew`/`gradlew.bat`.

Every version, library coordinate, and plugin id lives in `gradle/libs.versions.toml`. Modules reference `libs.*` accessors only; a literal version string in a `build.gradle.kts` is a review reject because it drifts from the catalog.

```toml
[versions]
agp = "8.11.0"
kotlin = "2.2.0"
ksp = "2.2.0-2.0.2"          # KSP version is <kotlin>-<ksp> and must track Kotlin exactly
hilt = "2.56.2"
composeBom = "2025.06.01"
coreKtx = "1.16.0"

[libraries]
androidx-core-ktx = { module = "androidx.core:core-ktx", version.ref = "coreKtx" }
compose-bom = { group = "androidx.compose", name = "compose-bom", version.ref = "composeBom" }
hilt-android = { module = "com.google.dagger:hilt-android", version.ref = "hilt" }
hilt-compiler = { module = "com.google.dagger:hilt-android-compiler", version.ref = "hilt" }
# Plugin artifacts exposed as deps so convention plugins can compileOnly them:
android-gradlePlugin = { module = "com.android.tools.build:gradle", version.ref = "agp" }
kotlin-gradlePlugin = { module = "org.jetbrains.kotlin:kotlin-gradle-plugin", version.ref = "kotlin" }

[bundles]
compose = ["androidx-compose-ui", "androidx-compose-material3"]

[plugins]
android-application = { id = "com.android.application", version.ref = "agp" }
kotlin-android = { id = "org.jetbrains.kotlin.android", version.ref = "kotlin" }
kotlin-compose = { id = "org.jetbrains.kotlin.plugin.compose", version.ref = "kotlin" }
ksp = { id = "com.google.devtools.ksp", version.ref = "ksp" }
hilt = { id = "com.google.dagger.hilt.android", version.ref = "hilt" }
```

Use the Compose BOM (`platform(libs.compose.bom)`) so all `androidx.compose.*` artifacts share one tested version set; never pin individual Compose artifact versions alongside the BOM. The Compose compiler is the `org.jetbrains.kotlin.plugin.compose` plugin (folded into Kotlin since 2.0); the old `composeOptions.kotlinCompilerExtensionVersion` block is gone and should be deleted on sight.

## Convention plugins

Once more than two or three modules exist, common `android { }` config belongs in a `build-logic` included build, not duplicated per module. Register it with `includeBuild("build-logic")` in `settings.gradle.kts`.

```kotlin
// build-logic/convention/src/main/kotlin/AndroidApplicationConventionPlugin.kt
class AndroidApplicationConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) = with(target) {
        with(pluginManager) {
            apply("com.android.application")
            apply("org.jetbrains.kotlin.android")
        }
        extensions.configure<ApplicationExtension> {
            compileSdk = 36                       // Android 16; track the latest stable SDK
            defaultConfig {
                minSdk = 24
                targetSdk = 36                    // Play requires the latest-but-one target each year
            }
            compileOptions {
                sourceCompatibility = JavaVersion.VERSION_17
                targetCompatibility = JavaVersion.VERSION_17
            }
        }
    }
}
```

A module then declares `plugins { id("myapp.android.application") }` and inherits the whole baseline. This keeps SDK levels, JVM target, lint config, and test wiring identical across modules and changeable in one file.

## Build types and product flavors

Two build types: `debug` (fast, no shrinking, `applicationIdSuffix = ".debug"` so it installs alongside release) and `release` (shrunk, signed, minified). Flavors carve out environment or product variants along an explicit `flavorDimensions`.

```kotlin
android {
    buildTypes {
        getByName("release") {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            signingConfig = signingConfigs.getByName("release")
        }
    }
    flavorDimensions += "environment"
    productFlavors {
        create("dev") {
            dimension = "environment"
            applicationIdSuffix = ".dev"
            buildConfigField("String", "BASE_URL", "\"https://dev.api.example.com\"")
        }
        create("prod") {
            dimension = "environment"
            buildConfigField("String", "BASE_URL", "\"https://api.example.com\"")
        }
    }
}
```

Variants multiply: two flavors x two build types yields `devDebug`, `devRelease`, `prodDebug`, `prodRelease`. Wire CI to the exact variant (`assembleProdRelease`, `testProdDebugUnitTest`) rather than the catch-all `assemble`, which builds every combination and wastes minutes. Keep the release signing key out of the repo; inject it from a CI secret or a Gradle property, never a checked-in keystore.

## KSP

KSP2 has replaced KAPT for annotation processing; KAPT runs the Java apt stub generator and is roughly 2x slower. Hilt, Room, and Moshi all ship KSP processors. Apply `alias(libs.plugins.ksp)` and use the `ksp(...)` configuration:

```kotlin
plugins {
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}
dependencies {
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)            // not kapt(...)
}
```

The KSP version string is `<kotlin>-<ksp>` and must match the Kotlin plugin version exactly; a mismatch fails configuration with a hard version error. Generated sources land in `build/generated/ksp/`; do not commit them.

## R8 and keep rules

R8 is the only shrinker (the legacy ProGuard plugin is removed) and full mode is the AGP 8 default. Full mode is more aggressive about optimization and assumes nothing is reached by reflection unless a keep rule says so, so reflection-based code breaks silently in release while debug works. The fix order is: prefer compile-time codegen (kotlinx.serialization, Moshi/Room KSP) that needs no keep rules; only when a library genuinely reflects, add a narrow rule.

```proguard
# proguard-rules.pro — keep only what is reached reflectively, never -keep class **
-keepattributes Signature, RuntimeVisibleAnnotations, AnnotationDefault, InnerClasses, EnclosingMethod

# Retrofit service interfaces are looked up reflectively at runtime
-keep,allowobfuscation,allowshrinking interface retrofit2.Call
-keep,allowobfuscation,allowshrinking class kotlin.coroutines.Continuation

# Models deserialized by reflection (avoid by using @Serializable / @JsonClass codegen instead)
-keepclassmembers class com.example.api.dto.** { <fields>; }
```

Most third-party libraries now ship consumer keep rules via `consumer-proguard-files`, so you usually only keep your own reflected models. Verify every release variant actually runs: build `assembleProdRelease`, install it, and exercise serialization and DI paths. Keep the generated `mapping.txt` per release for crash deobfuscation and upload it to your crash reporter.

## Static analysis: ktlint and detekt

Run both. ktlint (1.6.x) enforces the official Kotlin style and auto-formats; detekt (1.23.8; 2.0 is in alpha) catches code smells, complexity, and potential bugs that formatting does not. Apply them through Gradle plugins so they run identically locally and in CI.

```kotlin
// build-logic, applied to every module
plugins {
    id("org.jlleitschuh.gradle.ktlint") version "12.3.0"
    id("io.gitlab.arturbosch.detekt") version "1.23.8"
}
detekt {
    buildUponDefaultConfig = true
    config.setFrom(rootProject.files("config/detekt/detekt.yml"))
    autoCorrect = false                 // CI never auto-fixes; it only reports
}
```

Set thresholds and enforce them: detekt `maxIssues: 0` on the build-failure threshold, complexity guards such as `LongMethod` at 60 lines and `CyclomaticComplexMethod` at 15, and `ktlintCheck` (not `ktlintFormat`) in CI so unformatted code fails rather than being silently rewritten. Run `detektMain`/`detektTest` to use type resolution, which finds bugs the source-only pass misses. Wire `dependencies { detektPlugins(...) }` for the Compose rule set (`io.nlopez.compose.rules:detekt`) to catch unstable Compose parameters and misuse of `remember`.

## Dependency verification

Turn on Gradle's dependency verification so a swapped or poisoned artifact fails the build instead of shipping. Generate the metadata once and commit it:

```bash
./gradlew --write-verification-metadata sha256,pgp help
```

This produces `gradle/verification-metadata.xml` with a checksum and, where available, a trusted PGP key per dependency. Prefer `pgp` with `sha256` as the fallback; pure-checksum entries must be regenerated on every legitimate upgrade, which trains reviewers to rubber-stamp diffs. Combine this with a Renovate or Dependabot config that opens upgrade PRs, and a Gradle dependency-locking or `failOnVersionConflict()` resolution strategy so transitive versions cannot float. The verification file is part of the supply-chain boundary: changes to it get the same review scrutiny as a new dependency.

## CI pipeline (GitHub Actions)

One workflow, separate jobs so failures are isolated and parallel. Use Temurin JDK 21, `gradle/actions/setup-gradle@v4` (which caches the Gradle user home and configuration cache), and the maintained `reactivecircus/android-emulator-runner@v2` for instrumented tests with KVM hardware acceleration.

```yaml
name: android-ci
on:
  pull_request:
  push:
    branches: [main, develop]
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  static-analysis:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: '21' }
      - uses: gradle/actions/setup-gradle@v4
      - run: ./gradlew ktlintCheck detektMain lintProdRelease

  unit-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: '21' }
      - uses: gradle/actions/setup-gradle@v4
      - run: ./gradlew testProdDebugUnitTest assembleProdDebug

  instrumented-test:
    runs-on: ubuntu-latest
    timeout-minutes: 40
    strategy:
      matrix: { api-level: [30, 34] }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: '21' }
      - uses: gradle/actions/setup-gradle@v4
      - name: Enable KVM
        run: |
          echo 'KERNEL=="kvm", GROUP="kvm", MODE="0666", OPTIONS+="static_node=kvm"' | sudo tee /etc/udev/rules.d/99-kvm4all.rules
          sudo udevadm control --reload-rules && sudo udevadm trigger --name-match=kvm
      - uses: reactivecircus/android-emulator-runner@v2
        with:
          api-level: ${{ matrix.api-level }}
          arch: x86_64
          script: ./gradlew connectedProdDebugAndroidTest

  release:
    if: github.ref == 'refs/heads/main'
    needs: [static-analysis, unit-test, instrumented-test]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: '21' }
      - uses: gradle/actions/setup-gradle@v4
        with: { dependency-graph: generate-and-submit }
      - run: ./gradlew assembleProdRelease
        env: { KEYSTORE_PASSWORD: ${{ secrets.KEYSTORE_PASSWORD }} }
```

Dependency verification runs implicitly on every Gradle invocation once `verification-metadata.xml` exists, so each job above also fails on a poisoned artifact. Enable hardware KVM acceleration as shown; without it the emulator falls back to software rendering and instrumented jobs time out.

### Gates by branch type

Codify these as GitHub branch-protection required checks, not as etiquette:

- `feature/*` and PRs into `develop`: `static-analysis` (ktlint, detekt, lint) and `unit-test` (unit tests + `assembleProdDebug`) must be green. Instrumented tests run but may be advisory if the team accepts emulator flakiness.
- `develop` (integration branch): all of the above plus `instrumented-test` green on every matrix API level. No merge on red.
- `release/*` and `main`: every job including the `release` job's `assembleProdRelease` must pass, the R8-shrunk artifact must build, and `verification-metadata.xml` must be unchanged or reviewed. `main` is the only branch that produces a shippable artifact.

## Common pitfalls

- A literal dependency version in a module `build.gradle.kts` instead of `libs.*`; it drifts from the catalog and defeats single-source upgrades.
- KSP version not matching the Kotlin version exactly; configuration fails or, worse, processes against the wrong compiler API.
- Per-module duplication of `android { }` config instead of a convention plugin; SDK and JVM levels diverge silently across modules.
- Pinning individual Compose artifact versions next to the Compose BOM, producing an untested mix.
- Release crash from R8 full mode stripping a reflected class, masked because only `debug` is tested in CI; always run `assembleProdRelease` and exercise it.
- Broad `-keep class ** { *; }` rules that disable shrinking wholesale to "fix" one crash, ballooning the APK and hiding the real reflective dependency.
- `ktlintFormat` in CI instead of `ktlintCheck`, so the pipeline rewrites code and reports green on input that was never actually clean.
- Instrumented tests run without KVM, timing out and being marked "flaky" then disabled.
- Dependency verification metadata regenerated blindly on every upgrade with no PGP trust, so review becomes a rubber stamp.
- Signing keystore or its password committed to the repo rather than injected from a CI secret.
- CI running `assemble`/`test` (all variants) rather than the specific `prodRelease`/`prodDebugUnitTest` task, multiplying build time.

## Definition of done

- [ ] Kotlin DSL throughout; all versions, libraries, and plugin ids live in `gradle/libs.versions.toml` and modules reference `libs.*` only.
- [ ] Gradle wrapper pins `distributionSha256Sum`; `gradle/verification-metadata.xml` is committed with PGP-plus-sha256 entries and treated as a reviewed supply-chain boundary.
- [ ] Shared module config is a `build-logic` convention plugin; no copy-pasted `android { }` blocks.
- [ ] Build types (`debug`/`release`) and `flavorDimensions`-scoped flavors are defined; release sets `isMinifyEnabled`, `isShrinkResources`, signing from a secret, and a kept `mapping.txt`.
- [ ] Annotation processing uses KSP (not KAPT) with a Kotlin-matched version; generated sources are git-ignored.
- [ ] R8 runs in full mode; keep rules are narrow and justified, codegen is preferred over reflection, and the release variant is built and smoke-tested.
- [ ] `ktlintCheck` and `detektMain` run in CI with a zero-issue failure threshold and explicit complexity limits; CI never auto-formats.
- [ ] GitHub Actions workflow runs static analysis, unit tests, instrumented tests on a KVM-accelerated emulator matrix, lint, and `assembleProdRelease`, scoped to specific variants.
- [ ] Branch-protection required checks differ by branch type as documented, and `main`/`release/*` cannot merge without the full gate including the R8 release build.
