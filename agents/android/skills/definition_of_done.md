# Android Definition of Done

An Android change is done only when every gate below holds in CI on a clean checkout, not when it builds on the author's machine. Treat the Definition of Done as an executable contract: one Gradle verification command must pass before review, the release build must shrink and start, accessibility must be exercised, no secret may enter history, and the design decision must be written to project memory. A green local `assembleDebug` is not done.

## The gate as one command

Make the gate runnable so it is reproducible and CI-enforceable. Wire a single aggregate task and require it in the merge check.

```kotlin
// build.gradle.kts (root) — fail fast, run the whole gate
tasks.register("verify") {
    group = "verification"
    dependsOn(
        ":app:testReleaseUnitTest",        // JVM unit tests against the release variant
        ":app:lintRelease",                // Android Lint, release config
        ":app:ktlintCheck",                // formatting
        ":app:detekt",                     // static analysis
        ":app:koverVerify",                // coverage thresholds
        ":app:pixel8Api36DebugAndroidTest",// instrumented tests on a managed device
        ":app:assembleRelease",            // R8 release build must succeed
    )
}
```

Pin the toolchain in `gradle/libs.versions.toml` and the wrapper, so the gate is identical everywhere. As of mid-2026 a current baseline is Kotlin 2.2.0, AGP 8.11, Gradle 8.14, `compileSdk = 36` / `targetSdk = 36` (Android 16), JDK 17 toolchain, Compose BOM `2025.06.00`. Floating versions ("8.+") make the gate non-deterministic and are a review reject.

## Unit and instrumented tests green

Unit tests run on the JVM (JUnit5 or JUnit4, MockK 1.14.x, Turbine 1.2.1 for Flow). Instrumented and Compose UI tests run on a device. In CI use Gradle Managed Devices so there is no flaky emulator setup:

```kotlin
// app/build.gradle.kts
android {
    testOptions {
        managedDevices.localDevices {
            create("pixel8Api36") {
                device = "Pixel 8"
                apiLevel = 36
                systemImageSource = "aosp-atd"  // ATD images are headless, faster, CI-friendly
            }
        }
    }
}
```

Required, not optional:

- Coroutines/Flow tested deterministically: inject a `TestDispatcher`, drive virtual time, and assert emissions with Turbine's `test { awaitItem() }` rather than sleeping. A `Thread.sleep` in a test is a reject.
- Compose UI tested through `createAndroidComposeRule`, querying by semantics (`onNodeWithText`, `onNodeWithContentDescription`, `onNodeWithTag`), never by pixel position.
- Coverage enforced by Kover 0.9.x with a verify rule (for example 80% line coverage on the domain layer), so "I added tests" is measured, not asserted:

```kotlin
kover {
    reports {
        verify {
            rule {
                minBound(80)  // fails koverVerify below threshold
            }
        }
    }
}
```

- All network and external services mocked (MockWebServer for Retrofit/OkHttp, fakes for repositories). A test that hits a real endpoint is non-hermetic and fails the gate by definition.
- Zero ignored or flaky tests merged. `@Ignore` without a tracked issue is a reject; retried flakes are bugs, not noise.

## ktlint and detekt clean, Lint clean

Three distinct tools, all required to pass with zero new findings:

- ktlint 1.6.x (via the `org.jlleitschuh.gradle.ktlint` 12.x plugin) enforces the official Kotlin style. `ktlintCheck` must be clean; `ktlintFormat` fixes most issues mechanically.
- detekt 1.23.x finds complexity, potential bugs, and code smells. Configure with a committed `config/detekt/detekt.yml`, enable type resolution (`detektMain` with classpath) so rules like `UnusedPrivateMember` and coroutine rules actually fire, and set `buildUponDefaultConfig = true`.
- Android Lint (`lintRelease`) catches platform issues static analysis of pure Kotlin misses: missing `contentDescription`, hardcoded strings, leaked `Context`, unsupported API levels, insecure `WebView` settings.

Manage legacy debt with a baseline file, never by disabling the rule globally:

```kotlin
android {
    lint {
        warningsAsErrors = true
        baseline = file("lint-baseline.xml")  // freezes existing debt; new findings fail
        checkReleaseBuilds = true
    }
}
```

A new warning suppressed inline with `@Suppress` and no justification comment is a reject; the point of the gate is that new code does not add debt.

## R8 release build succeeds

The release variant must build with shrinking, obfuscation, and resource shrinking on. R8 full mode is the AGP 8 default; do not disable it.

```kotlin
buildTypes {
    release {
        isMinifyEnabled = true
        isShrinkResources = true
        proguardFiles(
            getDefaultProguardFile("proguard-android-optimize.txt"),
            "proguard-rules.pro",
        )
    }
}
```

What "succeeds" means here:

- The minified APK/AAB actually assembles and the keep rules are correct. Reflection, Gson/Moshi models, and anything named in the manifest or JNI need explicit keep rules; a wrong rule does not fail the build, it crashes at runtime. So the gate must run instrumented smoke tests against a minified variant (a `benchmark`/`release`-like build type with `isMinifyEnabled = true` and `isDebuggable = true`), not only `debug`.
- `mapping.txt` is retained and uploaded for every release so production crash stack traces deobfuscate. A shipped build without an archived mapping file is not done.
- New consumer rules for library modules are reviewed; over-broad `-keep class ** { *; }` defeats shrinking and is a reject.

## Baseline profile current

A baseline profile (AOT-compiled hot paths) cuts cold start and scroll jank materially. It must be regenerated when the critical-path UI changes, or it silently goes stale.

```kotlin
// build.gradle.kts — androidx.baselineprofile 1.3.x
plugins { id("androidx.baselineprofile") }
// Generator module uses macrobenchmark to exercise startup + key journeys,
// emitting app/src/main/generated/baselineProfiles/baseline-prof.txt
```

Enforce currency at runtime and in CI:

- Use `ProfileVerifier.getCompilationStatusAsync()` in a Macrobenchmark test to assert the profile is present and compiled (`RESULT_CODE_COMPILED_WITH_PROFILE`), so a missing or skipped profile fails rather than degrading quietly.
- Regenerate the profile when navigation, the startup sequence, or a primary screen changes; a PR that reshapes the hot path but ships an old `baseline-prof.txt` is incomplete.
- Track cold-startup `timeToInitialDisplay` with Macrobenchmark and reject regressions beyond an agreed budget (for example > 10% slower than the branch baseline).

## Accessibility checked

Accessibility is a functional requirement, not a polish pass. Verify it mechanically and with assistive tech:

- Every non-text interactive or informative element has a meaningful `contentDescription`; decorative elements pass `contentDescription = null` deliberately. Missing descriptions are caught by `lintRelease`.
- Touch targets are at least 48x48dp. In Compose, rely on `minimumInteractiveComponentSize()` or `Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp)`; small custom icon buttons are the usual offender.
- Text contrast meets WCAG AA (4.5:1 for body text). Verify with the Accessibility Scanner app on key screens.
- Turn on automated a11y assertions in instrumented tests so regressions fail the build:

```kotlin
import androidx.test.espresso.accessibility.AccessibilityChecks

@BeforeClass @JvmStatic
fun enableA11yChecks() {
    AccessibilityChecks.enable().setRunChecksFromRootView(true)
}
```

- For Compose, expose stable test tags as resource ids (`Modifier.semantics { testTagsAsResourceId = true }` at the root) and add `stateDescription`/`role` to custom controls so TalkBack announces them correctly.
- A manual TalkBack pass of the new flow is part of done for any UI change; screen-reader order and focus traps are not caught by static tools.

## No secrets committed

Keys, tokens, and keystores never enter the repository or its history:

- API keys live in `local.properties` (gitignored) or CI secrets, injected via the Secrets Gradle Plugin or `BuildConfig` fields, never as string literals in code or `strings.xml`. A literal key in source is an immediate reject and a key-rotation event.
- The release `keystore` and its passwords are not committed; signing uses Play App Signing with credentials from CI environment variables.
- Run a secret scanner in pre-commit and CI (gitleaks 8.x or `detect-secrets`) so the gate blocks a leak before merge:

```yaml
# .pre-commit-config.yaml
- repo: https://github.com/gitleaks/gitleaks
  rev: v8.21.2
  hooks: [{ id: gitleaks }]
```

- If a secret ever lands, rotating the credential is mandatory; scrubbing history alone is insufficient because the value is already exposed.

## Decisions persisted to memory

Per project rules, a meaningful design choice is not done until it is recorded. Persist the decision (architecture pick, dependency addition, migration, accessibility or security trade-off) to the SurrealDB memory backend through the `solomon-memory` MCP `save_decision` tool, and log a handoff for the next agent. An undocumented architectural change that only lives in the diff fails this gate; the rationale must be retrievable later.

## Common pitfalls

- "Works on my machine": the gate passed locally on `debug` but CI runs the release/minified variant and instrumented tests fail. Run the same aggregate task CI runs.
- Treating ktlint as the whole story and skipping detekt and `lintRelease`; each catches a different class of defect.
- `isMinifyEnabled = false` left on for release "to avoid R8 issues", shipping a bloated, un-obfuscated app and hiding the keep-rule bugs until production.
- No archived `mapping.txt`, so release crashes are undecodable.
- Stale baseline profile after a navigation rewrite, quietly regressing startup with no failing test.
- Accessibility reduced to adding `contentDescription`, while touch targets stay below 48dp and TalkBack focus order is broken.
- Secret scanning run only in CI, so the key is already in local history by the time it is caught; pre-commit must run too.
- Flaky instrumented tests retried until green instead of fixed; the flake is the bug.
- Coverage asserted in the PR description but not enforced by `koverVerify`, so it drifts down over time.
- Design decision left in the diff only, never written to project memory, so the next agent re-litigates it.

## Definition of done

- [ ] A single aggregate `verify` task passes in CI on a clean checkout, with pinned toolchain versions (no floating `+` versions).
- [ ] JVM unit tests and instrumented/Compose tests are green on a Gradle Managed Device; coroutines use a `TestDispatcher`, no `Thread.sleep`, all external services mocked.
- [ ] `koverVerify` enforces the agreed coverage threshold; no `@Ignore` or retried flakes merged.
- [ ] `ktlintCheck`, `detekt` (with type resolution), and `lintRelease` (`warningsAsErrors`, baselined debt) report zero new findings; no unjustified `@Suppress`.
- [ ] The R8 release build assembles with `isMinifyEnabled`/`isShrinkResources` on, smoke tests run against a minified variant, and `mapping.txt` is archived.
- [ ] The baseline profile is regenerated for hot-path changes and `ProfileVerifier` confirms it is compiled; cold-start budget not regressed.
- [ ] Accessibility verified: meaningful `contentDescription`, >= 48dp touch targets, AA contrast, `AccessibilityChecks` enabled in tests, and a manual TalkBack pass of new flows.
- [ ] No secrets in source or history; keys injected from `local.properties`/CI, keystore excluded, gitleaks runs in pre-commit and CI, any exposed key rotated.
- [ ] The design decision and a handoff are persisted to the SurrealDB memory backend via the `solomon-memory` MCP tools.
- [ ] Conventional Commit message and Git Flow branch; PR description states what was verified, not just what changed.
