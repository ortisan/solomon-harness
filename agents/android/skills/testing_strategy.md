---
name: testing-strategy
description: Governs the Android test pyramid across JVM unit tests, Compose and Robolectric component tests, and instrumented/screenshot tests, plus coroutine test dispatchers, Turbine, and Kover coverage gates. Use when writing or reviewing Android tests, choosing between unit, Compose, Robolectric, and instrumented coverage, or configuring CI test and coverage gates.
---

# Android Testing Strategy

Build the test suite as a pyramid: many fast JVM unit tests, a thinner band of Compose and Robolectric component tests, and a small set of instrumented end-to-end and screenshot tests, so most signal comes from tests that run in seconds without an emulator. Push every assertion to the lowest layer that can hold it, make coroutine and Flow code deterministic with test dispatchers, and gate merges on coverage and a green instrumented run on a managed device.

## The pyramid and where each tool belongs

- Unit (about 70%): pure JVM, run with `testDebugUnitTest`. JUnit4/JUnit5 + MockK + Turbine + Truth. ViewModels, use cases, mappers, repositories with fake data sources. No Android framework on the classpath beyond what Robolectric provides.
- Component/integration (about 20%): Compose UI tests with `createComposeRule`, and Robolectric tests for code that touches `Context`, resources, `SharedPreferences`, or Room. Still on the JVM, still in the `test` source set.
- Instrumented/E2E (about 10%): `androidTest` source set on a real or managed device. Espresso/Compose flows that cross process boundaries, Room migrations against real SQLite, WorkManager, navigation across screens. Slow and flaky-prone, so keep this band small and reserved for what genuinely needs a device.

Prefer hand-written fakes over mocks for your own interfaces (a `FakeUserRepository` backed by a `MutableStateFlow`); reserve MockK for third-party seams and verifying interactions. A test that mocks the class under test verifies nothing.

## Unit tests: JUnit, MockK, Truth

Stack as of 2026: JUnit 4.13.2 (the runner AndroidX Test still requires) or JUnit Jupiter 5.12.x via the `de.mannodermaus.android-junit5` plugin for the JVM source set, MockK 1.14.x, Truth 1.4.x. Use `relaxed = true` only for noisy collaborators; default to explicit stubs so an unexpected call fails loudly.

```kotlin
@Test
fun `price applies bulk discount above threshold`() {
    val rates = mockk<RateProvider>()
    every { rates.discountFor(quantity = 12) } returns 0.10
    val calc = PriceCalculator(rates)

    val total = calc.total(unitPrice = 5.00, quantity = 12)

    assertThat(total).isWithin(1e-9).of(54.00)
    verify(exactly = 1) { rates.discountFor(12) }
}
```

Use `coEvery`/`coVerify` for `suspend` functions, `slot<T>()` to capture arguments, and `mockkStatic`/`mockkObject` sparingly. Name tests with backtick sentences describing behavior, not method names.

## Coroutines and Flow: test dispatchers and Turbine

Never call `Thread.sleep`, `runBlocking`, or real `Dispatchers.IO` in a test. Use `kotlinx-coroutines-test` 1.10.x: `runTest` gives a virtual clock so delays resolve instantly, and a `MainDispatcherRule` swaps `Dispatchers.Main` so `viewModelScope` works off-device.

```kotlin
@OptIn(ExperimentalCoroutinesApi::class)
class MainDispatcherRule(
    val dispatcher: TestDispatcher = UnconfinedTestDispatcher(),
) : TestWatcher() {
    override fun starting(d: Description) = Dispatchers.setMain(dispatcher)
    override fun finished(d: Description) = Dispatchers.resetMain()
}
```

Pick the dispatcher deliberately. `UnconfinedTestDispatcher` runs new coroutines eagerly and is right for ViewModels exposing `StateFlow` via `stateIn(SharingStarted.WhileSubscribed(5_000))`, where you want emissions to land without manual pumping. `StandardTestDispatcher` queues coroutines until you call `advanceUntilIdle()` / `advanceTimeBy(ms)`, which you want when asserting intermediate states or ordering.

Test `Flow` and `StateFlow` with Turbine 1.2.x rather than collecting into a list; it enforces that every emission is consumed and that the flow completes or is cancelled.

```kotlin
@get:Rule val mainRule = MainDispatcherRule()

@Test
fun `loads profile then ready`() = runTest {
    val repo = FakeUserRepository(User(7, "Ada"))
    val vm = ProfileViewModel(repo)

    vm.state.test {
        assertThat(awaitItem()).isEqualTo(Loading)
        assertThat(awaitItem()).isEqualTo(Ready(User(7, "Ada")))
        cancelAndIgnoreRemainingEvents()  // StateFlow never completes
    }
}
```

For a hot `StateFlow` with a `WhileSubscribed` policy, `test {}` provides the active subscriber that keeps the upstream running. Use `expectNoEvents()` to assert quiescence and `awaitComplete()` for finite flows. Set `runTest(timeout = 10.seconds)` to fail fast on a deadlocked collector instead of hanging the suite.

## Robolectric

Robolectric 4.15.x runs Android framework code on the JVM via shadows, so Room, `Context`, resources, and `LayoutInflater` work in the `test` source set without an emulator. Use it for component tests where Compose alone is not enough but a device is overkill.

```kotlin
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApp::class)
class SettingsStoreTest {
    @Test fun `reads default theme`() {
        val ctx = ApplicationProvider.getApplicationContext<Context>()
        assertThat(SettingsStore(ctx).theme()).isEqualTo(Theme.System)
    }
}
```

Set `testOptions.unitTests.isIncludeAndroidResources = true` in Gradle so resources resolve. Pin `@Config(sdk = [...])` to the API levels you actually support; relying on the manifest `targetSdk` makes the test silently track SDK bumps. Robolectric is the engine Roborazzi and Compose Preview screenshot tests run on, so you often get it transitively.

## Compose UI tests

Use `createComposeRule()` for isolated composables and `createAndroidComposeRule<MainActivity>()` when you need a real activity, Hilt, or `rememberNavController`. Drive interaction through the semantics tree, not pixel coordinates. Add `Modifier.testTag("submit")` to anchor nodes whose visible text is volatile or localized.

```kotlin
@get:Rule val compose = createComposeRule()

@Test
fun `submit enables only when form valid`() {
    compose.setContent { AppTheme { LoginScreen() } }

    compose.onNodeWithTag("submit").assertIsNotEnabled()
    compose.onNodeWithText("Email").performTextInput("a@b.co")
    compose.onNodeWithTag("password").performTextInput("hunter2!")
    compose.onNodeWithTag("submit").assertIsEnabled().performClick()

    compose.onNodeWithTag("welcome").assertIsDisplayed()
}
```

Key rules:

- The rule auto-syncs with Compose's recomposition and the test clock, so no manual idling for normal state changes. For infinite or driven animations set `compose.mainClock.autoAdvance = false` and step with `mainClock.advanceTimeBy(ms)` to assert mid-animation frames deterministically.
- Use `waitUntil(timeoutMillis = 5_000) { compose.onAllNodesWithTag("row").fetchSemanticsNodes().size == 3 }` for async content; do not poll with sleeps.
- `useUnmergedTree = true` when a child node is collapsed into a parent's merged semantics (common with buttons wrapping text and icons).
- Expose state to UIAutomator/Espresso by setting `Modifier.semantics { testTagsAsResourceId = true }` once at the screen root so `testTag` maps to a resource id.
- Assert on `assertIsDisplayed`/`assertExists`, custom `SemanticsMatcher`, and `printToLog()` while debugging a failing selector.

## Espresso instrumentation

For View-based screens and cross-screen instrumented flows, use Espresso 3.6.x in `androidText` with `AndroidJUnitRunner`. Espresso auto-synchronizes with the main looper but not with your own async work; register an `IdlingResource` (or `IdlingRegistry`) for background loads instead of inserting waits.

```kotlin
@RunWith(AndroidJUnit4::class)
class CheckoutFlowTest {
    @get:Rule val activity = ActivityScenarioRule(CheckoutActivity::class.java)

    @Test fun completesPurchase() {
        onView(withId(R.id.card)).perform(typeText("4242"), closeSoftKeyboard())
        onView(withId(R.id.pay)).perform(click())
        onView(withText("Order confirmed")).check(matches(isDisplayed()))
    }
}
```

Disable system animations on the test device (`window`/`transition`/`animator` scale to 0) or instrumented runs flake. Use Espresso-Intents to stub outgoing intents and Espresso-Contrib for `RecyclerView` actions. For mixed View+Compose screens, Espresso and the Compose rule coexist in one test via `composeTestRule` bound to the same activity.

## Screenshot tests

Catch visual regressions without an emulator. As of 2026 there are three viable tools; pick one and standardize.

- Paparazzi 1.3.x (Cash App): renders Compose and Views entirely on the JVM, no device, fastest. Cannot run device-dependent code paths. Record with `./gradlew recordPaparazziDebug`, verify in CI with `verifyPaparazziDebug`.
- Roborazzi 1.4x.x (takahirom): runs on Robolectric, so it sees real resources and can drive interactions before capture; pairs with your existing Robolectric/Compose tests. `recordRoborazziDebug` / `verifyRoborazziDebug`.
- Compose Preview Screenshot Testing (AndroidX, `com.android.compose.screenshot` plugin): captures your existing `@Preview` functions from a `screenshotTest` source set. `updateDebugScreenshotTest` to bake references, `validateDebugScreenshotTest` to check. Lowest authoring cost when previews already exist.

```kotlin
@get:Rule val paparazzi = Paparazzi(deviceConfig = PIXEL_6, theme = "Theme.App")

@Test fun loginLightAndDark() {
    paparazzi.snapshot("light") { AppTheme(dark = false) { LoginScreen(state = ready) } }
    paparazzi.snapshot("dark")  { AppTheme(dark = true)  { LoginScreen(state = ready) } }
}
```

Commit golden PNGs to the repo (or Git LFS for large sets), pin a single rendering host so anti-aliasing is reproducible, and run a tiny allowed pixel delta rather than exact equality to absorb font-hinting noise. Snapshot the meaningful states (loading, empty, error, RTL, large font scale, dark theme), not one happy-path frame.

## Running in CI and coverage gates

- JVM tests (unit, Robolectric, Paparazzi/Roborazzi verify) run on any runner: `./gradlew testDebugUnitTest verifyPaparazziDebug`. These are the fast gate on every PR.
- Instrumented tests need a device. Prefer Gradle Managed Devices over self-managed emulators: define a headless ATD (Automated Test Device, `google-atd`/`aosp-atd`) image in Gradle and run `./gradlew pixel6Api34DebugAndroidTest`. ATD images strip the launcher and Play Store and run roughly 2x faster. Firebase Test Lab is the alternative for real-hardware matrices.
- Shard instrumented runs with `numManagedDeviceShards` (or `numShards`/`shardIndex` on the runner) to keep wall-clock down, and always set animation scales to 0 on the image.
- Use `@HiltAndroidTest` with a `HiltTestRunner` (`AndroidJUnitRunner` subclass returning `HiltTestApplication`) and `HiltAndroidRule` to inject fakes into instrumented tests.

Coverage: use Kotlinx Kover 0.9.x (Kotlin-aware, handles inline functions and coroutines correctly where JaCoCo miscounts) and fail the build below threshold.

```kotlin
kover {
    reports {
        verify {
            rule { minBound(80) }                    // overall line coverage
            rule {
                groupBy = GroupingEntityType.CLASS
                filters { excludes { classes("*_Factory", "Hilt_*", "*.databinding.*") } }
                minBound(85)                          // domain/use-case layer held higher
            }
        }
    }
}
```

Exclude generated code (Hilt, DataBinding, `*_Factory`, `*JsonAdapter`) so the number reflects real logic, and treat coverage as a floor, not a target: a covered line with no assertion is worthless. Gate the merge on `koverVerify` plus a green `testDebugUnitTest` and managed-device `connectedCheck`.

## Common pitfalls

- `runBlocking` or real dispatchers in a unit test: real delays make the suite slow and time-dependent. Use `runTest` with the virtual clock and a `TestDispatcher`.
- Wrong test dispatcher: `StandardTestDispatcher` with no `advanceUntilIdle()` makes a ViewModel emit nothing; `UnconfinedTestDispatcher` hides ordering bugs. Choose per case.
- Collecting a `StateFlow` into a list instead of Turbine, so dropped or extra emissions pass silently; and forgetting `cancelAndIgnoreRemainingEvents()` for a never-completing flow.
- Mocking the class under test, or `relaxed = true` everywhere, so unexpected calls return defaults and the test asserts nothing real.
- Compose tests selecting by coordinates or brittle text instead of `testTag`/semantics, and missing `useUnmergedTree` on merged nodes.
- Animations left running: nondeterministic Compose frames or Espresso flake. Control `mainClock` or zero out system animation scales.
- `Thread.sleep` to wait for async UI instead of `waitUntil` or an `IdlingResource`.
- Heavy instrumented E2E tests for logic that a JVM unit test covers, inverting the pyramid and ballooning CI time.
- Screenshot goldens rendered on a different host than CI, producing perpetual false diffs; or exact-pixel comparison with no tolerance.
- Coverage counting generated Hilt/DataBinding code, inflating the percentage while real branches stay untested.

## Definition of done

- [ ] New or changed logic has JVM unit tests; the pyramid stays unit-heavy and instrumented tests are reserved for device-dependent paths.
- [ ] Coroutine/Flow code is tested with `runTest`, a `MainDispatcherRule`, the dispatcher chosen deliberately, and `StateFlow`/`Flow` asserted via Turbine with all emissions consumed.
- [ ] Own collaborators use fakes; MockK is limited to third-party seams and interaction checks, with no mocking of the unit under test.
- [ ] Compose screens have tests driving the semantics tree with `testTag` anchors, controlled animation clock, and `waitUntil` for async content.
- [ ] Robolectric covers `Context`/resource/Room-touching logic on the JVM; instrumented Espresso/Compose tests cover real cross-screen and migration flows with animations disabled and Hilt fakes injected.
- [ ] Screenshot tests (Paparazzi, Roborazzi, or Compose Preview) cover loading/empty/error/dark/RTL/large-font states, with goldens committed and a pixel-delta tolerance on a pinned host.
- [ ] CI runs `testDebugUnitTest` and screenshot verification on every PR and a managed-device instrumented run before merge, with sharding and zeroed animation scales.
- [ ] Kover (or JaCoCo) enforces a coverage floor, excludes generated code, holds the domain layer to a higher bound, and blocks the merge when unmet.
