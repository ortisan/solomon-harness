# Android Common Pitfalls

Reject the Android-specific defects that compile cleanly but leak memory, drop frames, corrupt user data, or expose the app: unscoped coroutines, retained `Context`, unstable Compose inputs, main-thread I/O, missing Room migrations, over-exported components, and hardcoded secrets. This skill is the review checklist for native Kotlin/Compose code; each rule names the failure mode and the platform reason a reviewer must cite when blocking it. Versions below are the mid-2026 baseline (Kotlin 2.2.x, Compose BOM 2026.x with runtime 1.9, Room 2.8, Coroutines 1.10, Lifecycle 2.9, AGP 8.x, target SDK 36 / Android 16).

## Coroutine and lifecycle scoping

`GlobalScope` is a process-lifetime scope: any coroutine launched in it outlives the screen, captures whatever it touches, and cannot be cancelled. It defeats structured concurrency and is a leak by construction. Use the scope tied to the owner of the work.

```kotlin
// Reject: leaks the coroutine and its captured refs; survives rotation and
// back-navigation; an in-flight error can crash a dead screen.
GlobalScope.launch { repository.refresh() }

// ViewModel-owned work: cancelled automatically in onCleared().
viewModelScope.launch { repository.refresh() }
```

Flow collection must follow the UI lifecycle. A bare `lifecycleScope.launch { flow.collect {} }` keeps collecting while the app is backgrounded, wasting work and holding the collector (and the view it closes over) across `STOPPED`. Suspend collection below `STARTED`.

```kotlin
// View system / Fragment:
lifecycleScope.launch {
    repeatOnLifecycle(Lifecycle.State.STARTED) {
        viewModel.state.collect(::render)
    }
}

// Compose: collectAsStateWithLifecycle (lifecycle-runtime-compose 2.9.x) does
// the repeatOnLifecycle dance for you. Plain collectAsState does NOT.
val state by viewModel.state.collectAsStateWithLifecycle()
```

For background work that must outlive the UI (uploads, sync), use `WorkManager` with constraints, not a wider scope. Long-running coroutines belonging to the data layer get their own `CoroutineScope(SupervisorJob() + Dispatchers.Default)` owned by a singleton, cancelled explicitly, never `GlobalScope`.

## Context and Activity leaks

An `Activity` holds the entire view hierarchy. Any reference to it that outlives `onDestroy()` leaks the whole tree, and rotation creates a fresh Activity every time, so the leak compounds. Static fields, `object` singletons, long-lived callbacks, and handlers posting delayed messages are the usual culprits.

```kotlin
// Leak: a process-lifetime singleton pinning an Activity Context.
object ImageCache { var context: Context? = null }   // never store an Activity

// Anything outliving the Activity takes applicationContext.
@Singleton
class Repo @Inject constructor(@ApplicationContext private val ctx: Context)
```

Rules a reviewer enforces: never pass `Activity`/`Fragment`/`View`/`LifecycleOwner` into a constructor of an object that lives longer than them; use `applicationContext` for caches, DI singletons, and `WorkManager`; unregister listeners, `BroadcastReceiver`s, and sensor/location callbacks in the symmetric lifecycle callback; never use a non-static inner `Handler` or `Runnable` posted with delay (the implicit outer reference leaks the host). Wire LeakCanary 3.x into debug builds (`debugImplementation "com.squareup.leakcanary:leakcanary-android:3.0"`); a heap-dump leak trace in CI is a blocking finding, not noise.

## Compose stability and needless recomposition

Compose skips a composable only when every parameter is stable and unchanged. An unstable parameter forces recomposition on every parent pass even when the value is identical. Strong skipping mode (default since the Kotlin 2.0.20 Compose compiler) skips composables with unstable params when the instances are referentially or structurally equal, but it does not fix params that are genuinely new objects each frame.

```kotlin
// Unstable: List<T> is an interface, so the compiler cannot prove immutability.
@Composable fun Feed(items: List<Item>) { /* recomposes needlessly */ }

// Stable: kotlinx.collections.immutable 0.4.x is recognized by the compiler.
import kotlinx.collections.immutable.ImmutableList
@Composable fun Feed(items: ImmutableList<Item>) { /* skippable */ }

// State objects passed to children should be @Immutable / @Stable.
@Immutable
data class FeedUiState(val items: ImmutableList<Item>, val title: String)
```

Common recomposition rejects:

- Reading state too high in the tree. Read `state.value` at the lowest composable that needs it (or pass a lambda `() -> Value`) so recomposition is scoped, not whole-screen.
- Allocating a new lambda or object that is then used as a key, or a `Modifier` built inside the composable body each frame where a remembered one suffices.
- `LazyColumn`/`LazyRow` items without a stable `key`; without it, reordering re-runs and loses item state and scroll position. Always `items(list, key = { it.id })`.
- Derived values recomputed every recomposition instead of `derivedStateOf` / `remember(key)`.
- `Modifier.composed { }` (deprecated) for stateful modifiers; use `Modifier.Node` / `ModifierNodeElement`.

Verify with the Compose compiler stability report (`-P plugin:androidx.compose.compiler.plugins.kotlin:reportsDestination=...`) and the Layout Inspector recomposition counts; a hot composable recomposing on unrelated state changes is a defect.

## Main-thread blocking and jank

The main (UI) thread renders frames and dispatches input. At 60 Hz the frame budget is 16.7 ms; at 90 Hz, 11.1 ms; at 120 Hz, 8.3 ms. Any synchronous I/O, database, network, JSON, bitmap decode, or heavy compute on it drops frames, and a block beyond 5 s on input dispatch produces an ANR.

```kotlin
// Reject: Room/Retrofit/file/Gson on the main thread.
fun load() { val rows = dao.getAllBlocking() }   // freezes the frame

// suspend functions hop dispatchers explicitly; Room/Retrofit suspend funcs
// already move off the main thread, but custom work must not.
suspend fun load(): List<Row> = withContext(Dispatchers.IO) { heavyParse() }
```

Enforce a debug `StrictMode` policy that catches accidental main-thread I/O early:

```kotlin
StrictMode.setThreadPolicy(
    StrictMode.ThreadPolicy.Builder()
        .detectDiskReads().detectDiskWrites().detectNetwork()
        .penaltyLog().penaltyDeath().build()
)
```

A reviewer rejects `runBlocking` on the main thread, `Thread.sleep` in UI code, `.collect`/`Flow` terminal ops without a dispatcher for CPU work, and `Dispatchers.Main` chosen for anything but UI updates. Profile suspect paths with Macrobenchmark (`FrameTimingMetric`) and the Android Studio profiler; a P90 frame over budget is a finding.

## Room schema and migrations

Bumping `@Database(version = ...)` without a migration path makes Room throw `IllegalStateException` on launch for every existing user. The only "fix" that hides it, `fallbackToDestructiveMigration()`, silently wipes the user's data on upgrade. Both are blocking in review.

```kotlin
@Database(
    entities = [User::class],
    version = 2,
    exportSchema = true,                 // schema JSON checked into VCS
    autoMigrations = [AutoMigration(from = 1, to = 2)],
)
abstract class AppDatabase : RoomDatabase()
```

Required controls:

- `exportSchema = true` and the schema directory wired in Gradle (`room.schemaLocation`), with the generated JSON committed. Without it, auto-migrations and migration tests cannot run.
- Use `@AutoMigration` for additive/renaming changes; supply `@DeleteColumn`/`@RenameColumn`/`@DeleteTable` spec classes for destructive ones so Room generates correct SQL instead of guessing.
- Write a `MigrationTestHelper` instrumentation test that opens the old schema, runs the migration, and asserts the data survives. An untested migration is an untested data-loss path.
- `fallbackToDestructiveMigration()` is permitted only for caches the app can rebuild, never for user-authored data, and never silently.

## Exported components and IPC surface

Since Android 12 (API 31) any `<activity>`, `<service>`, or `<receiver>` with an `<intent-filter>` must declare `android:exported` explicitly; the build fails otherwise. Default every component to `false` and export only what other apps genuinely need. An over-exported component lets any installed app launch your screens, trigger your services, or feed crafted Intents.

```xml
<!-- Export only with a deliberate reason; gate with a signature permission
     when only your own apps should call it. -->
<activity android:name=".DeepLinkActivity" android:exported="true">
    <intent-filter android:autoVerify="true"> ... </intent-filter>
</activity>

<service android:name=".SyncService"
         android:exported="false"
         android:permission="com.example.permission.SYNC" />
```

Reviewer rejects: exported `ContentProvider` without `android:permission` or path-level `<path-permission>`; exported components that trust Intent extras without validation (intent redirection, deep-link parameter injection); `android:exported="true"` added just to silence the manifest-merger error; deep links with `autoVerify` but no published Digital Asset Links file. Treat every exported surface as an untrusted input boundary and validate accordingly.

## Hardcoded secrets

`BuildConfig` fields, resource strings, and constants are compiled verbatim into the APK and extracted in seconds with `apktool` or `jadx`. R8/ProGuard obfuscation renames symbols; it is not encryption and does not hide string literals. API keys, OAuth client secrets, signing credentials, and tokens in source are a leak the moment the build ships.

- Keep build-time values (non-secret keys, flavor config) in a git-ignored `local.properties` or `secrets.properties`, surfaced via the `secrets-gradle-plugin`, never committed.
- True secrets (third-party API secrets, anything that authorizes spend) belong on a backend the app calls; the client receives short-lived, scoped tokens.
- Use Play App Signing so the upload/signing key never lives in the repo or CI logs; store CI credentials in the CI secret store, not `gradle.properties`.
- Runtime credentials and tokens go in `EncryptedSharedPreferences` / Jetpack Security or the Android Keystore, never plain `SharedPreferences` or files.
- Add a secret scanner (gitleaks, or GitHub secret scanning) to CI; a matched key is a blocking finding and requires rotation, not just removal from `HEAD`.

## Configuration changes and state preservation

A configuration change (rotation, dark mode, locale, font scale, window resize, fold/unfold) destroys and recreates the Activity by default. State that lives only in the Activity or in a plain `remember` is lost. Suppressing recreation with `android:configChanges` to "fix" this is the wrong tool: it skips resource reloading, hides layout and resource bugs, and breaks correct multi-window/foldable behavior.

```kotlin
// Survives rotation AND process death (Bundle-backed).
var query by rememberSaveable { mutableStateOf("") }

// ViewModel survives config change; SavedStateHandle survives process death,
// so transient UI state and important inputs both survive a low-memory kill.
class SearchViewModel(private val handle: SavedStateHandle) : ViewModel() {
    val query: StateFlow<String> = handle.getStateFlow("query", "")
}
```

Enforce: hold screen state in a `ViewModel`, not the Activity/Fragment; use `rememberSaveable` for UI state that must survive rotation; route data that must survive process death through `SavedStateHandle` (it persists when the OS kills a backgrounded process and the user returns). Test process death with developer-options "Don't keep activities" or `adb shell am kill`; a screen that loses the user's input on return is a defect. Reach for `android:configChanges` only for genuinely custom redraw cases (e.g. a video surface), with state still preserved by the mechanisms above.

## Common pitfalls

- `GlobalScope.launch` anywhere in app code: an uncancellable, leaking coroutine. Use `viewModelScope`, a lifecycle scope, or `WorkManager`.
- Collecting a `Flow` with `lifecycleScope.launch { collect {} }` or plain `collectAsState`, so collection runs in the background and pins the view. Use `repeatOnLifecycle(STARTED)` or `collectAsStateWithLifecycle`.
- A singleton, static field, or non-static `Handler`/`Runnable` holding an `Activity`/`View`/`Fragment`, leaking the whole view tree on every rotation.
- Passing `List`/`Set`/`Map` interface types or non-`@Immutable` data classes into composables, forcing recomposition; use `ImmutableList`/`persistentListOf` and stability annotations.
- `LazyColumn` items without a stable `key`, losing item state and scroll position on data change.
- Room/Retrofit/file/JSON/bitmap work on the main thread; `runBlocking` or `Thread.sleep` on the UI thread, dropping frames or triggering ANRs.
- Bumping the Room database version with no `Migration`/`@AutoMigration`, crashing on upgrade, or papering over it with `fallbackToDestructiveMigration()` on user data.
- Untested migrations and `exportSchema = false`, leaving the upgrade path unverified.
- `android:exported="true"` added only to satisfy the API 31 manifest requirement, exposing components and trusting Intent extras without validation.
- Exported `ContentProvider` or `Service` with no permission gate; deep links with `autoVerify` and no asset-links file.
- API keys, OAuth secrets, or signing credentials in `BuildConfig`, resources, or committed `gradle.properties`; assuming R8 obfuscation protects them.
- Holding screen state in the Activity instead of a `ViewModel`, or using `android:configChanges` to dodge recreation and hiding resource/layout bugs.
- State that survives rotation but not process death because it skips `rememberSaveable`/`SavedStateHandle`.

## Definition of done

- [ ] No `GlobalScope`; all coroutines are owned by `viewModelScope`, a lifecycle scope, an explicitly cancelled data-layer scope, or `WorkManager`.
- [ ] Every UI flow collection uses `repeatOnLifecycle(STARTED)` or `collectAsStateWithLifecycle`; nothing collects while backgrounded.
- [ ] No long-lived object references an `Activity`/`View`/`Fragment`/`LifecycleOwner`; singletons use `applicationContext`; listeners and receivers are unregistered symmetrically; LeakCanary runs in debug with no reported leaks.
- [ ] Composable parameters are stable: immutable collections (`kotlinx.collections.immutable`) and `@Immutable`/`@Stable` state classes; lazy lists supply stable `key`s; the compiler stability report shows the hot composables as skippable.
- [ ] No blocking I/O, network, DB, parse, or `runBlocking`/`Thread.sleep` on the main thread; debug `StrictMode` with `penaltyDeath` passes; P90 frame time is within the device's refresh budget under Macrobenchmark.
- [ ] Every Room version bump has an `@AutoMigration` or `Migration`, `exportSchema = true` with committed schema JSON, and a passing `MigrationTestHelper` test; no destructive fallback on user data.
- [ ] Every manifest component declares `android:exported` deliberately, defaulting to `false`; exported components validate Intent input and gate sensitive IPC with permissions; deep links ship an asset-links file.
- [ ] No secrets in `BuildConfig`, resources, or committed Gradle files; build-time config comes from a git-ignored source, runtime tokens from Keystore/`EncryptedSharedPreferences`, signing via Play App Signing; a CI secret scanner passes.
- [ ] Screen state lives in a `ViewModel`; `rememberSaveable` covers rotation and `SavedStateHandle` covers process death, verified with "Don't keep activities"; `android:configChanges` is used only where justified, with state still preserved.
