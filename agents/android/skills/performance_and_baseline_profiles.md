---
name: performance-and-baseline-profiles
description: Governs frame-budget and jank measurement, Compose recomposition cost, Baseline Profile generation and Macrobenchmark validation, R8 full mode, LeakCanary, and StrictMode enforcement on Android. Use when investigating jank, slow cold start, or memory leaks, or when generating and validating a Baseline Profile for a release.
---

# Performance and Baseline Profiles

Performance on Android is a measured, regression-gated property, not a vibe: every frame must clear its hardware deadline and every cold start must stay fast, proven by instrumentation rather than asserted. The stance is to attach a number to each claim (frame overrun in ms, cold-start TTID/TTFD, recomposition counts), gate those numbers in CI with Macrobenchmark, and ship a Baseline Profile so users hit AOT-compiled code on the first launch. Treat jank, leaks, and slow startup as defects with reproductions and thresholds, not as polish to do later.

## Frame budget and jank metrics

A frame is janky when it misses the display's deadline, and the deadline is set by the refresh rate, not a fixed 16ms. At 60Hz the budget is 16.67ms, at 90Hz it is 11.11ms, at 120Hz it is 8.33ms. Modern devices run high-refresh by default, so design to the device's actual rate; a frame that is fine at 60Hz can be jank at 120Hz.

Instrument in-app jank with JankStats (`androidx.metrics:metrics-performance:1.0.0-beta02`, still beta but the supported API). It reads the platform `FrameMetrics` on API 24+ and falls back gracefully below that, and it lets you attach UI state so a janky frame is attributable to a screen.

```kotlin
val jankStats = JankStats.createAndTrack(window) { frame ->
    if (frame.isJank) {
        Log.w("Jank", "dur=${frame.frameDurationUiNanos / 1_000_000.0}ms states=${frame.states}")
    }
}
// Tag the current screen so jank is attributable.
val state = PerformanceMetricsState.getHolderForHierarchy(view).state
state?.putState("screen", "feed")
```

In Macrobenchmark, `FrameTimingMetric` is the source of truth for CI: it reports `frameDurationCpuMs` and, on API 31+, `frameOverrunMs` (how far past the deadline a frame ran; positive means jank) at P50/P90/P95/P99. Gate on P99 `frameOverrunMs <= 0` for the critical journey; a regression there is a real, user-visible stutter.

## Compose performance and stability

The dominant Compose cost is unnecessary recomposition. Compose skips a composable only when all its parameters are stable and unchanged. With the Compose compiler now versioned and applied through the Kotlin Gradle plugin (`org.jetbrains.kotlin.plugin.compose`, Kotlin 2.x), strong skipping mode is on by default (since compiler 2.0.20): composables with unstable parameters become skippable and lambdas are auto-remembered. It is a safety net, not a substitute for stable types.

- Prefer `@Immutable`/`@Stable` data and immutable collections. A `List<T>` parameter is unstable because the type does not guarantee immutability; use `kotlinx.collections.immutable` (`ImmutableList`, `persistentListOf`) or wrap in an `@Immutable` holder so the compiler can mark the composable skippable.
- For third-party or generated classes you cannot annotate, add a stability configuration file: `composeCompiler { stabilityConfigurationFile = rootProject.layout.projectDirectory.file("stability_config.conf") }` listing fully qualified class names to treat as stable.
- Use `derivedStateOf` when a frequently-changing state (scroll offset) feeds a rarely-changing boolean (showButton); reading the raw state recomposes on every pixel, the derived state recomposes only on the transition.
- Defer state reads to the latest phase. Pass lambdas (`Modifier.offset { IntOffset(x, 0) }`, `graphicsLayer { }`) instead of reading state in composition, so animation runs in layout/draw and skips recomposition entirely.
- Provide stable `key`s in `LazyColumn`/`LazyRow` items so reordering moves items instead of rebuilding them.

Measure, do not guess. Layout Inspector shows per-composable recomposition and skip counts live; a count that climbs while the screen is idle is the bug. Composition tracing (add `androidx.tracing:tracing-perfetto:1.0.0` and `androidx.tracing:tracing-perfetto-binary`) names every composable in a Perfetto trace so you see which subtree recomposed and how long it took.

## Baseline Profiles and Macrobenchmark

Without a profile, a fresh install runs interpreted/JIT code until ART compiles hot paths in the background, so the first runs are the slowest exactly when the user is judging the app. A Baseline Profile is an AOT hint, shipped in the APK/AAB and applied by `androidx.profileinstaller:profileinstaller:1.4.x`, that pre-compiles the critical user journey. It typically cuts cold start by 20-40% and removes most first-run scroll jank.

Generate it with the `androidx.baselineprofile` Gradle plugin (1.3.x) and a generator module:

```kotlin
@RunWith(AndroidJUnit4::class)
class BaselineProfileGenerator {
    @get:Rule val rule = BaselineProfileRule()

    @Test
    fun generate() = rule.collect(
        packageName = "com.example.app",
        includeInStartupProfile = true,   // also emit a startup profile for DEX layout
    ) {
        pressHome()
        startActivityAndWait()
        device.findObject(By.res("feed")).fling(Direction.DOWN)
        device.waitForIdle()
    }
}
```

Validate the win with Macrobenchmark (`androidx.benchmark:benchmark-macro-junit4:1.3.x`) on a real device or a userdebug emulator, comparing compilation modes:

```kotlin
@RunWith(AndroidJUnit4::class)
class StartupBenchmark {
    @get:Rule val rule = MacrobenchmarkRule()

    @Test
    fun coldStartupWithProfile() = rule.measureRepeated(
        packageName = "com.example.app",
        metrics = listOf(StartupTimingMetric()),
        iterations = 10,
        startupMode = StartupMode.COLD,
        compilationMode = CompilationMode.Partial(BaselineProfileMode.Require),
    ) {
        pressHome()
        startActivityAndWait()
    }
}
```

Run the same test with `CompilationMode.None()` to see the worst case and `CompilationMode.Full()` for the ceiling; the profile should land close to Full. Macrobenchmark requires `<profileable>` (or `debuggable` off) on the target and a non-debuggable build to give meaningful numbers. The `includeInStartupProfile` output additionally drives DEX layout (`startup` profile), packing startup classes into the primary DEX so fewer pages are faulted in at launch.

## Startup classes: cold, warm, hot

- Cold start: process does not exist; the system forks Zygote, creates `Application`, then the first `Activity`. Slowest and the one to optimize. Target sub-500ms TTID on mid-tier hardware.
- Warm start: process alive, activity recreated. Hot start: activity already resident, just brought forward; should be near-instant.

`StartupTimingMetric` reports `timeToInitialDisplayMs` (TTID, first frame drawn) and `timeToFullDisplayMs` (TTFD). TTFD only appears if you call `reportFullyDrawn()` (via `Activity.reportFullyDrawn()` or `ReportDrawn` in Compose) once content the user actually waits for, such as the loaded feed, is on screen; without it you optimize the skeleton instead of the real wait.

Keep `Application.onCreate` and first-activity work minimal: no disk or network on the main thread, no eager DI graph warmup. Use `androidx.startup:startup-runtime` (`Initializer`) to order and lazily defer component initialization instead of a monolithic `Application`. Avoid a splash that hides slow init; use the `androidx.core:core-splashscreen` API and remove its keep-condition the moment first content is ready.

## R8 full mode

`isMinifyEnabled = true` plus `isShrinkResources = true` on release is mandatory; the only question is keep rules. R8 full mode is the default since AGP 8.0 (`android.enableR8.fullMode=true`), and it optimizes more aggressively than ProGuard-compat: assumed-no-side-effect, stronger inlining and class merging, value propagation. It also makes wrong or missing keep rules fail more visibly, which is the point.

```kotlin
buildTypes {
    release {
        isMinifyEnabled = true
        isShrinkResources = true
        proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
    }
}
```

- Keep only what reflection, JNI, or serialization actually needs (`-keep class ... { *; }` is a smell; narrow it). Most modern libraries ship `consumer-rules.pro`, so do not blanket-keep their packages.
- Reflection-driven JSON (Gson, reflective Moshi) needs keep rules or codegen; prefer codegen (Moshi `@JsonClass(generateAdapter = true)`, kotlinx.serialization) so R8 can shrink freely.
- Always preserve and archive the `mapping.txt` per release and upload it to Play; deobfuscate stack traces with R8 `retrace`. A crash report against an obfuscated, unarchived mapping is unreadable.
- Verify the shrunk release build in CI, not just debug; full-mode optimizations have surfaced reflection bugs that never appear in the unminified build.

## Memory leaks: LeakCanary

A leaked `Activity`, `Fragment`, `View`, or `ViewModel` holds bitmaps and view trees, raising GC pressure and causing jank and eventual OOM. Add LeakCanary (`com.squareup.leakcanary:leakcanary-android:2.14`, or 3.x) to the `debugImplementation` configuration only; it auto-installs, watches destroyed objects, and dumps a leak trace with the exact reference chain and the culprit highlighted.

Common roots it catches: a `Context` captured by a static or singleton, a non-static inner class or lambda outliving its host, an unregistered listener/`BroadcastReceiver`, a coroutine launched on a leaked scope. For non-Android objects (a cache entry, a disposed presenter) call `AppWatcher.objectWatcher.expectWeaklyReachable(obj, "reason")`. Treat a LeakCanary notification as a failing test; for CI, the `leakcanary-android-instrumentation` `FailTestOnLeak`/`LeakAssertions.assertNoLeaks()` turns leaks into UI-test failures.

## StrictMode

StrictMode catches accidental main-thread I/O and lifecycle leaks in debug before they reach a profiler. Enable it early in `Application.onCreate`, debug builds only, and make violations loud.

```kotlin
if (BuildConfig.DEBUG) {
    StrictMode.setThreadPolicy(
        StrictMode.ThreadPolicy.Builder()
            .detectDiskReads().detectDiskWrites().detectNetwork()
            .penaltyLog()
            .build())
    StrictMode.setVmPolicy(
        StrictMode.VmPolicy.Builder()
            .detectActivityLeaks()
            .detectLeakedClosableObjects()
            .detectLeakedRegistrationObjects()
            .penaltyLog()
            .build())
}
```

Use `penaltyDeath()` in instrumentation runs to fail the build on a violation; keep `penaltyLog()` for interactive debug so the app stays usable. Never ship StrictMode in release. Whitelist genuinely unavoidable main-thread reads with `permitDiskReads()` around the narrowest possible block rather than disabling the detector.

## Perfetto and system traces

When a number says "slow" but not "why," capture a system trace. Use Perfetto (the System Tracing quick-settings tile, `record_android_trace`, or `adb shell perfetto`) and open it in `ui.perfetto.dev`; the legacy systrace is retired. Look at the main thread for long slices, the `Choreographer#doFrame` track for missed deadlines, `RenderThread` for GPU-bound draws, and binder transactions for IPC stalls.

Add your own slices so spans are named, not anonymous:

```kotlin
import androidx.tracing.trace

trace("loadFeed") {
    val page = repository.fetchPage()   // shows as a named slice in Perfetto
    render(page)
}
```

`androidx.tracing:tracing-ktx` slices are cheap and safe to keep in release (they no-op unless tracing is active). Combine with composition tracing (above) to see Compose work inside the same timeline. Drive reproducible traces from Macrobenchmark with `PerfettoTrace` capture so the trace and the metric come from the same run.

## Common pitfalls

- Treating 16ms as the budget on a 120Hz device; the real deadline is 8.33ms and the app stutters while every average looks fine. Gate on `frameOverrunMs` per the device rate.
- Optimizing the average frame or average startup. Users feel P99 and cold start; gate those, not the mean.
- A Baseline Profile generated but never validated by Macrobenchmark, or measured on a `debuggable` build, so the reported win is noise.
- Running Macrobenchmark on a debug build; JIT and debug overhead make the numbers meaningless. It must target a non-debuggable, profileable build.
- `List`/`Set`/`Map` parameters in composables left unstable, defeating skipping; reviewer should require immutable collections or a stability config entry.
- Reading rapidly-changing state (scroll offset) directly in composition instead of `derivedStateOf` or a deferred lambda, recomposing every frame.
- `reportFullyDrawn()` never called, so TTFD is missing and the slow real content is invisible to the metric.
- Blanket `-keep class com.thirdparty.** { *; }` rules that defeat R8 shrinking; keep the minimum and prefer codegen serialization.
- `mapping.txt` not archived or uploaded, leaving release crash traces undecodable.
- LeakCanary added to `implementation` instead of `debugImplementation`, shipping its overhead to production.
- StrictMode left out, or `penaltyDeath` shipped in release, crashing real users.

## Definition of done

- [ ] Critical-journey jank is measured with `FrameTimingMetric`; CI gates P99 `frameOverrunMs` (or P95 `frameDurationCpuMs`) against the device refresh rate, and JankStats is wired with per-screen state in debug.
- [ ] Compose hot screens have zero idle recompositions in Layout Inspector; list/collection parameters are immutable or covered by a stability config; `derivedStateOf` and deferred lambdas are used for high-frequency state.
- [ ] A Baseline Profile (with startup profile) is generated for the main journey, shipped via `profileinstaller`, and validated by a Macrobenchmark comparing `None`/`Partial`/`Full` on a non-debuggable build, with the measured cold-start improvement recorded.
- [ ] `StartupTimingMetric` reports both TTID and TTFD; `reportFullyDrawn()`/`ReportDrawn` marks real content; cold-start TTID meets the agreed target on mid-tier hardware; `Application.onCreate` does no main-thread I/O.
- [ ] Release builds run R8 full mode with resource shrinking, the narrowest possible keep rules, codegen serialization, and an archived, Play-uploaded `mapping.txt`.
- [ ] LeakCanary runs in `debugImplementation`; known leak classes are covered by `LeakAssertions.assertNoLeaks()` in instrumentation tests; no open leaks on the main flows.
- [ ] StrictMode thread and VM policies are enabled in debug only, with `penaltyDeath` in instrumentation runs and no StrictMode in release.
- [ ] At least one Perfetto/system trace of the slow path is captured with named `trace { }` slices (and composition tracing for Compose) and attached to any performance investigation.
