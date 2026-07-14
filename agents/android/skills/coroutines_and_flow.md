---
name: coroutines-and-flow
description: Governs dispatcher selection, lifecycle-scoped coroutine launching, StateFlow versus SharedFlow choice, flowOn threading, cancellation, exception handling, and coroutine testing with Turbine and test dispatchers. Use when writing or reviewing asynchronous Kotlin code, Flow collection in Compose, or coroutine-based unit tests.
---

# Coroutines and Flow

Run every piece of asynchronous work inside a lifecycle-scoped coroutine so that cancellation is automatic, threading is explicit, and no collector outlives the UI that started it. Treat structured concurrency as the default: a coroutine that is not a child of a known scope is a leak, a flow collected on the main thread without a `flowOn` boundary is a jank source, and a `StateFlow`/`SharedFlow` chosen by habit instead of by hot/cold semantics is a bug waiting for a configuration change.

Target stack as of mid-2026: Kotlin 2.2.x with the K2 compiler, `org.jetbrains.kotlinx:kotlinx-coroutines-core` / `-android` / `-test` 1.10.2, `androidx.lifecycle:lifecycle-runtime-compose` and `lifecycle-viewmodel-ktx` 2.9.x, and `app.cash.turbine:turbine` 1.2.x for flow tests.

## Dispatchers and structured concurrency

Pick a dispatcher by the nature of the work, never at random:

- `Dispatchers.Main.immediate` for UI state updates and ViewModel orchestration. `immediate` skips a re-dispatch when already on the main thread, which matters for synchronous `StateFlow` updates.
- `Dispatchers.IO` for blocking I/O (Room, Retrofit's blocking calls, file/socket). It is an elastic pool capped at 64 threads by default; size up with `limitedParallelism(n)` for a specific resource rather than starving the shared pool.
- `Dispatchers.Default` for CPU-bound work (JSON parsing, sorting, image math), backed by a pool sized to the core count.
- Do not hardcode `Dispatchers.IO` inside a repository. Inject a dispatcher (`@IoDispatcher CoroutineDispatcher`) via Hilt so tests can swap a `TestDispatcher`. This is the single most important rule for testable async code.

```kotlin
class OrderRepository @Inject constructor(
    private val api: OrderApi,
    @IoDispatcher private val io: CoroutineDispatcher,
) {
    suspend fun fetch(id: String): Order = withContext(io) {
        api.getOrder(id) // blocking Retrofit call moved off the caller's thread
    }
}
```

Structured concurrency means a parent coroutine does not complete until its children do, and cancelling the parent cancels every child. `coroutineScope { }` propagates a child failure to siblings; `supervisorScope { }` isolates them. Use `coroutineScope` for "all must succeed" fan-out and `supervisorScope` when independent tasks should not take each other down.

## Lifecycle-scoped coroutines

Never launch from `GlobalScope` or a raw `CoroutineScope()` in Android code. Use the scopes the platform cancels for you:

- `viewModelScope` (cancelled in `onCleared()`) for work that outlives a single screen frame but dies with the ViewModel. It runs on `Dispatchers.Main.immediate` by default.
- `lifecycleScope` plus `repeatOnLifecycle(Lifecycle.State.STARTED)` for collecting flows in an Activity/Fragment, so collection stops in the background and restarts on return. A bare `lifecycleScope.launch { flow.collect { } }` keeps collecting while the screen is off and is a defect.

```kotlin
class OrderViewModel @Inject constructor(repo: OrderRepository) : ViewModel() {
    val state: StateFlow<UiState> = repo.observeOrders()
        .map(UiState::Loaded)
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = UiState.Loading,
        )
}
```

`SharingStarted.WhileSubscribed(5_000)` keeps the upstream alive for 5 seconds after the last collector leaves, which bridges a configuration change without re-running the query, then tears it down. Prefer it over `Eagerly` (never stops, leaks the upstream) and `Lazily` (never stops after first start).

## Cold vs hot, StateFlow vs SharedFlow

A cold flow (`flow { }`, Room `Flow` queries, Retrofit suspend wrapped in `flow`) re-executes its producer for every collector and runs nothing until collected. A hot flow (`StateFlow`, `SharedFlow`) exists independently of collectors and is shared.

- `StateFlow` is a hot flow with exactly one current value, `value` always readable, and `distinctUntilChanged` built in. It is the correct type for screen UI state. It always replays its latest value to a new collector, which is what survives a configuration change.
- `SharedFlow` is a hot flow for events with no conflation and a configurable `replay`/`extraBufferCapacity`. Use it for one-shot effects (navigate, show snackbar) where replaying the last value to a new subscriber would re-fire the event.

```kotlin
private val _events = MutableSharedFlow<UiEvent>(
    replay = 0,
    extraBufferCapacity = 1,
    onBufferOverflow = BufferOverflow.DROP_OLDEST,
)
val events: SharedFlow<UiEvent> = _events.asSharedFlow()

fun onSaved() {
    // tryEmit succeeds because of the buffer; never blocks the caller
    _events.tryEmit(UiEvent.NavigateBack)
}
```

Do not model navigation/toast events as `StateFlow`: its replay re-delivers the last event after rotation and you navigate twice. Do not model durable screen state as `replay = 0` `SharedFlow`: a collector that subscribes late renders nothing.

## Threading with flowOn

`flowOn` changes the dispatcher of the upstream operators only; it does not affect the collector. Put it directly above the operators that must run off the main thread, and keep the collection itself on Main so it can touch UI state.

```kotlin
fun search(query: String): Flow<List<Result>> = repository
    .rawRows(query)
    .map { it.toDomain() }     // CPU work
    .flowOn(Dispatchers.Default) // applies to rawRows + map only
```

A `flowOn` placed below an operator does not move that operator. Multiple `flowOn` calls create multiple boundaries; use one per logical stage.

## Collecting flows in Compose

Use `collectAsStateWithLifecycle()` from `androidx.lifecycle:lifecycle-runtime-compose`, not `collectAsState()`. The plain version keeps collecting while the app is backgrounded; the lifecycle-aware version stops at `STOPPED` and resumes at `STARTED`, which prevents wasted work and stale emissions driving recomposition off-screen.

```kotlin
@Composable
fun OrderScreen(viewModel: OrderViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    // render state
}
```

Consume one-shot events in a `LaunchedEffect` tied to the lifecycle, not by reading a `StateFlow` value, so events fire once:

```kotlin
val lifecycle = LocalLifecycleOwner.current.lifecycle
LaunchedEffect(Unit) {
    lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
        viewModel.events.collect { event -> /* navigate / snackbar */ }
    }
}
```

## Cancellation and timeouts

Cancellation is cooperative: a coroutine only stops at a suspension point. Long CPU loops that never suspend ignore cancellation. Call `ensureActive()` or `yield()` inside such loops. Never catch `CancellationException` and swallow it; rethrow it, or the structured-concurrency contract breaks and the parent never learns the child stopped.

```kotlin
try {
    doWork()
} catch (e: CancellationException) {
    throw e // mandatory: let cancellation propagate
} catch (e: IOException) {
    emit(UiState.Error(e))
}
```

For cleanup that must run even when cancelled, use `withContext(NonCancellable) { }`. For deadlines, prefer `withTimeout(2_000)` (throws `TimeoutCancellationException`) or `withTimeoutOrNull(2_000)` (returns `null`) over manual timer coroutines. Timeouts compose with structured concurrency and cancel the inner work automatically.

## Exception handling

In structured concurrency a child failure cancels the parent and all siblings by default. To isolate failures, build the scope on a `SupervisorJob` so one child's crash does not cancel the others:

```kotlin
private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
```

`viewModelScope` already uses a `SupervisorJob`, so a crash in one `launch` does not kill the ViewModel's other coroutines. A `CoroutineExceptionHandler` is the last-resort handler for uncaught exceptions in `launch` (it does nothing for `async`, where the exception surfaces at `await()`). Install it on the root scope, not on a child, because only a root handler is invoked.

```kotlin
val handler = CoroutineExceptionHandler { _, e ->
    Log.e("OrderVM", "uncaught", e)
    crashReporter.record(e)
}
viewModelScope.launch(handler) { riskyWork() }
```

Wrap recoverable per-step failures in `try/catch` (or `Result`) at the point of work; reserve `CoroutineExceptionHandler` for logging genuinely unexpected crashes. For flows, use the `catch { }` operator, which only catches upstream exceptions and must be placed above the collector.

## Testing with runTest, test dispatchers, and Turbine

Use `runTest { }` from `kotlinx-coroutines-test`. It runs on a `TestScope` whose virtual clock auto-advances past `delay()`, so a one-hour debounce test finishes in milliseconds. Choose the dispatcher deliberately:

- `StandardTestDispatcher` queues coroutines; nothing runs until you call `advanceUntilIdle()` or `runCurrent()`. Use it to assert intermediate states.
- `UnconfinedTestDispatcher` runs eagerly to the first suspension. Use it for simple "collect everything" tests.

Replace `Dispatchers.Main` in a JUnit rule so ViewModels using `Main.immediate` work under test:

```kotlin
class MainDispatcherRule(
    val dispatcher: TestDispatcher = UnconfinedTestDispatcher(),
) : TestWatcher() {
    override fun starting(d: Description) = Dispatchers.setMain(dispatcher)
    override fun finished(d: Description) = Dispatchers.resetMain()
}
```

Test flows with Turbine instead of collecting into a list, so you assert emissions in order and prove the stream completes or stays open:

```kotlin
@Test
fun emitsLoadingThenLoaded() = runTest {
    val vm = OrderViewModel(fakeRepo)
    vm.state.test {
        assertEquals(UiState.Loading, awaitItem())
        assertEquals(UiState.Loaded(orders), awaitItem())
        cancelAndIgnoreRemainingEvents() // StateFlow never completes
    }
}
```

Pass the rule's dispatcher into the code under test (constructor injection) so production and test share one clock. `awaitItem`, `awaitError`, `awaitComplete`, and `expectNoEvents` cover the cases; an unconsumed emission fails the test, catching accidental extra states.

## Common pitfalls

- Launching from `GlobalScope` or a hand-rolled `CoroutineScope()` with no cancellation owner. The work outlives the screen and leaks; reject in review.
- `lifecycleScope.launch { flow.collect { } }` without `repeatOnLifecycle(STARTED)`. It keeps collecting in the background and updates a destroyed view.
- `collectAsState()` instead of `collectAsStateWithLifecycle()` in Compose. Collection continues off-screen.
- One-shot events modeled as `StateFlow` (or `SharedFlow` with `replay > 0`). The event re-fires after rotation, causing double navigation.
- Catching `CancellationException` without rethrowing. It silently breaks structured cancellation and timeouts.
- Hardcoding `Dispatchers.IO` inside a repository instead of injecting a dispatcher, which makes the unit non-deterministic under `runTest`.
- `flowOn` placed below the operator it is meant to move, so the heavy work still runs on the collector's dispatcher.
- A CPU loop with no `ensureActive()`/`yield()` that ignores cancellation entirely.
- `SharingStarted.Eagerly` on a `stateIn` backed by a database query, keeping the upstream and its cursor alive forever.
- `CoroutineExceptionHandler` attached to a child coroutine (it is ignored) or expected to catch `async` failures (they surface at `await`).
- Tests that collect a flow into a `MutableList` with a manual `delay`, instead of Turbine; they are flaky and miss missing/extra emissions.

## Definition of done

- [ ] All async work runs in `viewModelScope` or `lifecycleScope`; no `GlobalScope` and no unscoped `CoroutineScope()`.
- [ ] Repositories and use cases inject their dispatcher (`@IoDispatcher`/`@DefaultDispatcher`); no hardcoded `Dispatchers.*` inside business logic.
- [ ] UI state is exposed as `StateFlow` via `stateIn(..., SharingStarted.WhileSubscribed(5_000), initial)`; one-shot effects use a `SharedFlow` with `replay = 0`.
- [ ] Compose collects with `collectAsStateWithLifecycle()`; flow collection in views uses `repeatOnLifecycle(Lifecycle.State.STARTED)`.
- [ ] Heavy upstream operators are isolated with a single correctly placed `flowOn`; collection stays on Main.
- [ ] `CancellationException` is always rethrown; timeouts use `withTimeout`/`withTimeoutOrNull`; cleanup that must survive cancellation uses `NonCancellable`.
- [ ] Independent concurrent tasks run under a `SupervisorJob`/`supervisorScope`; a root `CoroutineExceptionHandler` logs uncaught crashes; recoverable errors are handled with `try/catch` or the `catch { }` operator.
- [ ] Tests use `runTest`, a `MainDispatcherRule` with an injected `TestDispatcher`, and Turbine for flow assertions; the virtual clock drives all `delay`-based logic and no external service is hit live.
