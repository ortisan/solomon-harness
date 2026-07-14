---
name: scope-and-non-negotiables
description: Governs the default Android stack and version pins, SDK-level policy, MVVM/MVI architecture with Hilt, lifecycle-scoped concurrency, TDD requirements, and the boundary between native-Android work and the flutter, software_engineer, auth_engineer, and observability agents. Use when scoping a new Android task, choosing a library or SDK level, or deciding whether work belongs to the android agent or should be handed off.
---

# Scope and Non-Negotiables

Build native Android apps in Kotlin with Jetpack Compose as the default UI, MVVM/MVI over unidirectional data flow with Hilt for dependency injection, lifecycle-scoped Coroutines/Flow for async work, strict TDD, and R8 shrinking for every release. This skill fixes the working standard so reviewers reject deviations early: it pins the toolchain and versions, sets the minSdk/targetSdk/compileSdk policy, and draws the handoff lines to the flutter, backend, and auth specialists. When a request asks for cross-platform UI, server logic, or auth policy, do not absorb it; cede it to the owning agent.

## Default stack and versions (mid-2026)

Use the following unless the existing project pins something newer. Drive every version from a Gradle version catalog (`gradle/libs.versions.toml`), never inline literals in `build.gradle.kts`.

- Language: Kotlin 2.2.x with the K2 compiler. Use KSP (`com.google.devtools.ksp`, `2.2.0-2.0.x`) for annotation processing; KAPT is deprecated and roughly 2x slower, so do not introduce it.
- Build: Android Gradle Plugin 8.13+ (9.0 where the project is on it), Gradle Kotlin DSL, JDK 17 toolchain (`jvmToolchain(17)`).
- UI: Compose BOM (`androidx.compose:compose-bom`, 2026.x) so all Compose artifacts share a tested version set; Material 3 (`androidx.compose.material3`). The Compose compiler ships as the Kotlin plugin `org.jetbrains.kotlin.plugin.compose` since Kotlin 2.0; do not pin a separate `kotlinCompilerExtensionVersion`.
- DI: Hilt 2.57 (`com.google.dagger:hilt-android`), built on Dagger. Plain Dagger or manual service locators are not the default.
- Async: `kotlinx-coroutines` 1.10.x plus Flow.
- Jetpack: Navigation Compose 2.8.x with type-safe routes (`@Serializable` destinations); Room 2.7.x (KSP) for SQL storage; DataStore 1.1.x for preferences (never `SharedPreferences` in new code); WorkManager 2.10.x for deferrable background work; Retrofit 2.11/3.0 + OkHttp 5.x for networking, with `kotlinx-serialization` as the converter to avoid runtime reflection. Navigation 3 (`androidx.navigation3`) is still alpha; only adopt it on a greenfield module with a written rollback.
- Lifecycle-aware Compose collection comes from `androidx.lifecycle:lifecycle-runtime-compose` (`collectAsStateWithLifecycle`).

## SDK level policy

These three values are a policy decision, not a default to copy from a template. State them in the PR and justify any change.

- `compileSdk = 36` (Android 16). Always compile against the latest stable API so new lint, deprecations, and APIs are visible. Bump it the same sprint a new stable API lands.
- `targetSdk = 36`. This tracks Google Play's rolling requirement: Play blocks updates that target more than roughly one year behind the latest major release, and as of 2026 new apps and updates must target API 36. Raising `targetSdk` opts the app into new platform behavior, so pair the bump with a behavior-change audit (notification permission, foreground-service types, predictive back, and edge-to-edge are the usual breakers).
- `minSdk = 26` (Android 8.0) as the default floor: it reaches roughly 95% of active devices, gives notification channels, adaptive icons, and background execution limits without compat shims. Drop to 24 only with a data-backed reason; going below 24 is almost never justified in 2026. Enable `coreLibraryDesugaring` (`com.android.tools:desugar_jdk_libs`) so `java.time` and other APIs work below their native API level instead of forcing a higher `minSdk`.
- Edge-to-edge: with `targetSdk >= 35` the system draws edge-to-edge and ignores status/navigation bar color setters. Consume `WindowInsets` (via `Scaffold` or `Modifier.windowInsetsPadding`) rather than fighting the system bars.

```kotlin
android {
    compileSdk = 36
    defaultConfig {
        minSdk = 26
        targetSdk = 36
    }
    buildTypes {
        release {
            isMinifyEnabled = true      // R8: shrink + obfuscate
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }
    compileOptions { isCoreLibraryDesugaringEnabled = true }
    kotlin { jvmToolchain(17) }
}
```

## Architecture: MVVM/MVI with UDF and Hilt

Three layers (UI, domain, data) with dependencies pointing inward. The UI layer holds Composables and a `ViewModel`; the `ViewModel` exposes one immutable state object as a `StateFlow` and accepts user intents as function calls. State flows down, events flow up. No `LiveData` in new code, no mutable state leaking out of the `ViewModel`, no Android framework types (`Context`, `View`) in the domain or data layers.

```kotlin
@HiltViewModel
class SearchViewModel @Inject constructor(
    private val repo: SearchRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(SearchUiState())
    val state: StateFlow<SearchUiState> = _state.asStateFlow()

    fun onIntent(intent: SearchIntent) = when (intent) {
        is SearchIntent.QueryChanged -> search(intent.q)
    }

    private fun search(q: String) {
        viewModelScope.launch {                       // cancelled on ViewModel clear
            _state.update { it.copy(loading = true) }
            runCatching { repo.search(q) }
                .onSuccess { r -> _state.update { it.copy(loading = false, results = r) } }
                .onFailure { e -> _state.update { it.copy(loading = false, error = e.message) } }
        }
    }
}
```

```kotlin
@Composable
fun SearchRoute(vm: SearchViewModel = hiltViewModel()) {
    val state by vm.state.collectAsStateWithLifecycle()   // pauses below STARTED
    SearchScreen(state = state, onIntent = vm::onIntent)
}
```

`UiState` is a single immutable `data class`, not a bag of independent flows, so the screen never renders a half-updated state. Bind dependencies in Hilt `@Module`s with `@Binds`/`@Provides`; constructor-inject everything else.

## Concurrency: lifecycle-scoped Coroutines and Flow

Launch from a scope tied to a lifecycle: `viewModelScope` in a `ViewModel`, `lifecycleScope` for one-shot UI work. Never use `GlobalScope` or a bare `CoroutineScope()` you forget to cancel; both leak work past the screen and are an automatic review rejection. Collecting a hot Flow outside Compose must go through `repeatOnLifecycle` so collection stops in the background and a paused screen does not keep the upstream alive.

```kotlin
viewLifecycleOwner.lifecycleScope.launch {
    viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
        vm.state.collect(::render)   // auto-cancelled below STARTED, restarted on return
    }
}
```

Inject `CoroutineDispatcher`s (do not hardcode `Dispatchers.IO`) so tests can swap them. Use `flowOn` to move upstream work off the main thread, structured concurrency (`coroutineScope`/`supervisorScope`) for fan-out, and let cancellation propagate; catch `CancellationException` only to rethrow.

## TDD and the testing stack

Red, green, refactor is mandatory; no production code without a covering test. Unit tests: JUnit, MockK 1.14.x for mocks, Turbine 1.2.x for Flow assertions, `kotlinx-coroutines-test` (`runTest`, `StandardTestDispatcher`) for virtual time. Replace the main dispatcher with a rule so `viewModelScope` is deterministic.

```kotlin
@Test
fun emits_results_on_query() = runTest {
    val repo = mockk<SearchRepository>()
    coEvery { repo.search("kotlin") } returns listOf(item)
    val vm = SearchViewModel(repo)

    vm.state.test {                                   // Turbine
        assertThat(awaitItem()).isEqualTo(SearchUiState())   // initial state
        vm.onIntent(SearchIntent.QueryChanged("kotlin"))
        assertThat(awaitItem().loading).isTrue()
        assertThat(awaitItem().results).containsExactly(item)
        cancelAndIgnoreRemainingEvents()
    }
}
```

Compose UI tests use `createAndroidComposeRule` with semantics matchers (`onNodeWithText`, `onNodeWithTag`) on Robolectric or device. Add screenshot tests (Roborazzi or Paparazzi) for design-critical screens and Macrobenchmark + a Baseline Profile for startup and scroll jank. Mock every network and disk boundary; tests must not hit a real backend. Run unit, instrumentation, and lint in CI on every PR.

## In scope, out of scope, and handoffs

In scope: everything native-Android — Kotlin/Compose UI, the MVVM/MVI layers, Jetpack integration, Gradle/R8 build config, Play distribution, Android platform features (notifications, WorkManager, widgets, deep links), and the client side of platform APIs such as Credential Manager (`androidx.credentials`) for passkeys and Sign in with Google.

Hand off rather than absorb:

- Cross-platform / single shared mobile UI codebase belongs to the **flutter** agent. If the product is one shared Flutter app, the android agent owns only the native pieces (platform channels, native modules, Play release plumbing), not the shared UI. Do not rebuild a Flutter screen in Compose to "make it native" without an explicit product decision.
- Server APIs, business logic, and database design belong to the backend specialist (**software_engineer** and the relevant data/ml agents). The android agent consumes contracts; it does not define them.
- Authentication and authorization policy — OAuth 2.0/OIDC flows, token issuance and validation, passkey/WebAuthn server ceremonies, session and MFA design — belong to **auth_engineer**. The android agent integrates the client (Credential Manager, token storage in the Keystore-backed `EncryptedSharedPreferences`/DataStore) against that contract.
- Logging/metrics/tracing backends and dashboards belong to **observability**; the android agent instruments the app (OpenTelemetry Android, structured events) but does not own the pipeline.
- Shared business logic may live in Kotlin Multiplatform; that is a cross-agent decision. Even when logic is KMP, the Android UI stays native Compose under this agent.

## Common pitfalls

- `targetSdk` left stale to dodge behavior changes: Play eventually blocks the update, and the app misses required permission and security changes. Bump deliberately, audit the behavior changes.
- `minSdk` pushed up (28/29) to avoid writing compat code; it silently drops millions of devices. Use desugaring and AndroidX compat instead, and justify the floor with distribution data.
- `GlobalScope.launch` or an uncancelled custom scope: work outlives the screen and leaks. Use `viewModelScope`/`lifecycleScope`.
- Collecting a hot Flow with a plain `lifecycleScope.launch { flow.collect {} }` and no `repeatOnLifecycle` (or `collectAsStateWithLifecycle` in Compose): upstream keeps running in the background.
- Exposing `MutableStateFlow`/`MutableLiveData` publicly, or several independent flows instead of one `UiState`: callers mutate state and screens render inconsistent snapshots.
- KAPT added for a new library when KSP is available: slower builds and a deprecated path.
- Hardcoded `Dispatchers.IO` inside a `ViewModel`/repository, making the unit untestable and the main dispatcher unswappable.
- Release build with `isMinifyEnabled = false` or missing keep rules, so R8 either does not run or strips classes used via reflection (Retrofit/Gson). Prefer `kotlinx-serialization` to minimize reflective keep rules.
- New code on `SharedPreferences` or `LiveData` instead of DataStore and `StateFlow`.
- Android framework types (`Context`, `View`, `Cursor`) reaching into domain/data layers, breaking testability and layering.
- Reimplementing a shared Flutter screen or an auth/backend concern inside the Android app instead of handing it to the owning agent.

## Definition of done

- [ ] UI is Jetpack Compose + Material 3; any View/XML use is justified (existing screen or a Compose gap) in the PR.
- [ ] Architecture is MVVM/MVI with three layers, a single immutable `UiState` per screen exposed as a read-only `StateFlow`, unidirectional data flow, and Hilt constructor injection; no public mutable state, no `LiveData` in new code.
- [ ] All async work runs in a lifecycle-scoped coroutine (`viewModelScope`/`lifecycleScope`); hot flows are collected via `collectAsStateWithLifecycle` or `repeatOnLifecycle`; dispatchers are injected.
- [ ] `compileSdk`/`targetSdk` are the current stable (36 in 2026) with a behavior-change audit; `minSdk` is 26 (or a data-justified value) with `coreLibraryDesugaring` enabled.
- [ ] Versions come from `libs.versions.toml`; build uses Kotlin 2.2 K2, KSP (not KAPT), and JDK 17.
- [ ] TDD followed: unit tests (JUnit, MockK, Turbine, coroutines-test) and Compose UI tests cover new logic and screens, all external I/O mocked, run green in CI with lint.
- [ ] Release build has `isMinifyEnabled = true`, `isShrinkResources = true`, correct R8 keep rules, and verified ProGuard mapping; startup/jank checked with a Baseline Profile and Macrobenchmark where it matters.
- [ ] Cross-platform UI, backend, and auth-policy work has been routed to flutter, the backend specialist, and auth_engineer respectively rather than implemented here; the design decision is logged to project memory.
