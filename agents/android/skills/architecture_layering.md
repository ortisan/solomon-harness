# Architecture Layering

Structure every Android feature as three layers — UI, domain, data — with a strictly unidirectional flow where state descends and events ascend, so each layer is independently testable and the ViewModel never touches Android UI types. Treat an immutable `UiState` exposed as `StateFlow`, a repository that owns the single source of truth, and a Hilt graph that draws the seams as non-negotiable; the domain layer stays a pure Kotlin module with no Android dependencies.

## Layer boundaries and dependency direction

Three layers, dependencies pointing inward only (UI -> domain -> data; the data layer never imports UI, the domain never imports `androidx.compose` or `android.*`):

- UI layer: Composables and a `ViewModel` (`androidx.lifecycle:lifecycle-viewmodel-compose` 2.9.x). Renders `UiState`, emits user events. No business rules.
- Domain layer (optional but preferred once a feature has real logic): plain Kotlin/JVM module, use cases (interactors), domain models, repository interfaces. Zero Android imports — enforce with a `:domain` Gradle module that only depends on `kotlinx-coroutines-core`. If it can run in a vanilla JUnit test with no Robolectric, the boundary is correct.
- Data layer: repository implementations, Room (2.7.x), Retrofit (3.0) / OkHttp, DataStore, `kotlinx.serialization`. Owns DTOs and mapping.

Keep the domain repository interface in `:domain` and its implementation in `:data`; the UI depends on the interface, Hilt binds the implementation. This is the seam that lets you swap a fake repository in tests without a single mock framework.

```kotlin
// :domain — pure Kotlin, no Android
interface OrderRepository {
    fun observeOrders(): Flow<List<Order>>      // single source of truth, hot
    suspend fun refresh(): Result<Unit>
}

class GetActiveOrders @Inject constructor(
    private val repo: OrderRepository,
) {
    operator fun invoke(): Flow<List<Order>> =
        repo.observeOrders().map { it.filter(Order::isActive) }
}
```

## MVVM vs MVI and unidirectional data flow

Both are valid; pick per feature, not per app dogma. The shared rule is UDF: state flows down as a single immutable object, events flow up as method calls or a sealed `Event`/`Action` type.

- MVVM (default for most screens): ViewModel exposes one `StateFlow<UiState>`; the UI calls named methods (`onRefresh()`, `onItemClick(id)`). Less ceremony, fine when the screen has a handful of interactions.
- MVI (reach for it on complex, highly interactive screens): a single `sealed interface Intent`, one reducer `(State, Intent) -> State`, side effects as a separate one-shot `Channel`/`SharedFlow`. The reducer is a pure function, which makes the state machine exhaustively testable and replayable. The cost is boilerplate; do not impose it on a static detail screen.

Never expose `MutableStateFlow` or `LiveData` publicly, and never push `UiState` back down from the UI — the UI only reads state and sends events. Two-way binding of mutable state across the boundary is the bug MVI/MVVM exist to prevent.

## ViewModel and immutable UiState

Model state as one immutable type (a `data class`, or a `sealed interface` when states are mutually exclusive: `Loading | Content | Error`). Expose it with `stateIn` so collection is lifecycle-safe and the latest value is cached.

```kotlin
sealed interface OrdersUiState {
    data object Loading : OrdersUiState
    data class Content(val orders: List<Order>, val refreshing: Boolean = false) : OrdersUiState
    data class Error(val message: String) : OrdersUiState
}

@HiltViewModel
class OrdersViewModel @Inject constructor(
    getActiveOrders: GetActiveOrders,
    private val repo: OrderRepository,
) : ViewModel() {

    private val refreshing = MutableStateFlow(false)

    val uiState: StateFlow<OrdersUiState> =
        combine(getActiveOrders(), refreshing) { orders, isRefreshing ->
            OrdersUiState.Content(orders, isRefreshing) as OrdersUiState
        }
            .catch { emit(OrdersUiState.Error(it.message ?: "Unknown error")) }
            .stateIn(
                scope = viewModelScope,
                started = SharingStarted.WhileSubscribed(5_000), // survive config change, stop when backgrounded
                initialValue = OrdersUiState.Loading,
            )

    fun onRefresh() = viewModelScope.launch {
        refreshing.value = true
        repo.refresh()
        refreshing.value = false
    }
}
```

Rules and the reasons behind them:

- `WhileSubscribed(5_000)`: the 5-second stop timeout keeps the upstream flow (and the DB query) alive across rotation and brief app switches, then tears it down to free resources. `Eagerly`/`Lazily` leak the collection; `WhileSubscribed(0)` restarts the query on every rotation.
- Collect in Compose with `collectAsStateWithLifecycle()` (`lifecycle-runtime-compose` 2.9.x), not `collectAsState()` — the former stops collecting in `STOPPED`, preventing work and crashes while the screen is off.
- Hoist navigation/snackbar as one-shot effects, not state. A `Channel<Event>(Channel.BUFFERED)` exposed as `receiveAsFlow()` (or a `SharedFlow` with `replay = 0`) avoids re-firing navigation after rotation. Putting `navigateTo` inside `UiState` re-triggers it on recomposition.
- ViewModel must not reference `Context`, `View`, `Activity`, or Compose types. If you need resources, pass string ids or inject a thin string provider; this keeps the ViewModel a JVM unit test.
- Pass `SavedStateHandle` into the constructor for process-death survival of small state (selected ids, query text), not for large lists.

## Hilt graph, scopes, and modules

Hilt 2.57 (with KSP, not kapt — KSP is roughly 2x faster and the supported path in 2026). Components form a scope hierarchy; bind each type at the narrowest scope that fits its lifetime.

- `@Singleton` (`SingletonComponent`): app-lifetime stateless singletons — Retrofit, OkHttp, Room database, DataStore, repositories.
- `@ViewModelScoped` (`ViewModelComponent`): per-ViewModel state holders.
- `@ActivityRetainedScoped`: survives config change but is per-activity.
- Unscoped (no annotation): a new instance per injection — use cases, mappers. Cheap and stateless; scoping them only pins memory.

Use `@Binds` in an `abstract class` module to wire an interface to its implementation (zero runtime overhead vs `@Provides`), and `@Provides` for types you do not own (Retrofit, Room):

```kotlin
@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {
    @Binds @Singleton
    abstract fun bindOrderRepository(impl: OrderRepositoryImpl): OrderRepository
}

@Module
@InstallIn(SingletonComponent::class)
object DataModule {
    @Provides @Singleton
    fun provideDb(@ApplicationContext ctx: Context): AppDatabase =
        Room.databaseBuilder(ctx, AppDatabase::class.java, "app.db").build()

    @Provides @Singleton
    fun provideOrderApi(retrofit: Retrofit): OrderApi = retrofit.create()
}
```

- Annotate the `Application` with `@HiltAndroidApp`, Activities/Fragments with `@AndroidEntryPoint`, ViewModels with `@HiltViewModel`; obtain them via `hiltViewModel()` in Compose.
- Inject `CoroutineDispatcher` with a qualifier (`@IoDispatcher`) rather than hardcoding `Dispatchers.IO`. This is the seam that lets tests inject a `StandardTestDispatcher` and control virtual time.
- Use `@Binds @IntoSet` / `@IntoMap` for plugin-style collections (analytics trackers, initializers). Use assisted injection (`@AssistedInject` + `@AssistedFactory`) when a dependency needs a runtime argument the graph cannot supply.
- Do not over-scope. A `@Singleton` holding per-screen state is a leak and a cross-screen data bleed; scope mutable state to the ViewModel.

## Repository and single source of truth

The repository is the only component that decides where data comes from, and it exposes one authoritative stream. The canonical 2026 pattern is offline-first: the Room table is the single source of truth, the network only writes into it, and the UI observes the DB.

```kotlin
class OrderRepositoryImpl @Inject constructor(
    private val api: OrderApi,
    private val dao: OrderDao,
    @IoDispatcher private val io: CoroutineDispatcher,
) : OrderRepository {

    override fun observeOrders(): Flow<List<Order>> =
        dao.observeAll().map { it.map(OrderEntity::toDomain) }   // DB is the source of truth

    override suspend fun refresh(): Result<Unit> = withContext(io) {
        runCatching {
            val remote = api.getOrders()             // DTOs
            dao.upsertAll(remote.map(OrderDto::toEntity))   // write-through; observers re-emit
        }
    }
}
```

- The read path returns a `Flow` from Room; the write path fetches and upserts. The UI never sees the network directly, so a successful refresh updates every screen observing that table at once. This is what "single source of truth" buys you.
- Return `Result<T>` or a domain `Either`/sealed error from suspend functions; do not let raw `IOException`/`HttpException` cross into the domain. Map them to typed domain errors at the repository edge.
- Move `withContext(io)` into the repository, not the ViewModel. The ViewModel stays dispatcher-agnostic and the rule "suspend functions are main-safe" holds at the boundary.
- For paging, expose `Pager`/`PagingData` and back it with `RemoteMediator` so Room remains the source of truth.

## DTO and domain mapping

Keep three model families and never let them merge: `Dto` (network/`kotlinx.serialization`, nullable, snake_case via `@SerialName`), `Entity` (Room `@Entity`, storage shape), and the domain model (clean Kotlin the UI and use cases speak). Map explicitly at each boundary.

```kotlin
@Serializable
data class OrderDto(
    @SerialName("order_id") val id: String,
    @SerialName("total_cents") val totalCents: Long? = null,
)

fun OrderDto.toEntity() = OrderEntity(
    id = id,
    totalCents = totalCents ?: 0L,   // null handling lives in the mapper, not the UI
)

fun OrderEntity.toDomain() = Order(id = id, total = Money(totalCents))
```

- A single shared model reused as DTO + entity + UI state couples your wire format and your database schema to your screens; a backend rename or a column change then ripples into Composables. Mapping functions absorb that change in one file.
- Mappers are pure functions — the easiest thing in the codebase to unit test, and where you assert null/default/enum-fallback handling. Put unknown-enum and missing-field defaults here.
- Keep mappers as top-level extension functions in the data layer (or a small injected `Mapper` when they need dependencies like a clock or locale).

## Testability seams

The layering exists to produce these seams; a review should confirm each is present.

- Domain in plain JUnit: use cases and mappers test with no Android, no Robolectric, milliseconds per test.
- ViewModel with `StateFlow` + Turbine 1.2.x: assert the exact state sequence. Inject a fake repository (a hand-written `class FakeOrderRepository : OrderRepository`), not a mock, for state-machine clarity. Reserve MockK 1.14.x for verifying interactions/side effects.

```kotlin
@Test
fun emits_loading_then_content() = runTest {
    val vm = OrdersViewModel(GetActiveOrders(fakeRepo), fakeRepo)
    vm.uiState.test {
        assertEquals(OrdersUiState.Loading, awaitItem())
        fakeRepo.emit(listOf(order))
        assertEquals(OrdersUiState.Content(listOf(order)), awaitItem())
        cancelAndIgnoreRemainingEvents()
    }
}
```

- Dispatcher control: because the dispatcher is injected, pass `StandardTestDispatcher(testScheduler)` and drive time with `runTest` + `advanceUntilIdle()`. Set `Dispatchers.setMain` via a JUnit `MainDispatcherRule` so `viewModelScope` uses the test scheduler.
- Repository tests: Room provides an in-memory DB (`Room.inMemoryDatabaseBuilder`) and Retrofit pairs with OkHttp `MockWebServer` 5.x — assert the write-through path updates the observed flow.
- Compose UI: `createComposeRule()` with a hoisted state and a fake ViewModel; the Composable takes `UiState` + lambdas, so you can render every state (loading/content/error) without the real graph.

## Common pitfalls

- ViewModel importing `android.content.Context`, `View`, or Compose types — forces Robolectric and breaks the boundary. Inject abstractions instead.
- Exposing `MutableStateFlow`/`LiveData` publicly, letting the UI mutate state and destroying UDF.
- `collectAsState()` instead of `collectAsStateWithLifecycle()`, so the screen keeps collecting and doing work while stopped.
- `stateIn(..., SharingStarted.Eagerly)` (or `WhileSubscribed(0)`) — leaks collection or restarts the DB query on every rotation. Use `WhileSubscribed(5_000)`.
- Navigation/snackbar modeled as part of `UiState`, re-firing on recomposition and after rotation. Use a one-shot `Channel`/`SharedFlow(replay = 0)`.
- One shared data class serving as DTO, Room entity, and UI state — couples wire format and schema to the screen.
- `withContext(Dispatchers.IO)` hardcoded in the ViewModel instead of an injected, qualified dispatcher — untestable timing and a misplaced threading concern.
- Over-scoping mutable state to `@Singleton`, causing cross-screen data bleed and leaks; scope it to the ViewModel.
- Repository leaking `HttpException`/`IOException` into the domain instead of mapping to typed errors.
- Network treated as the source of truth with the DB as a cache, so screens disagree after a partial refresh. The DB is the single source of truth; the network writes through it.
- `runBlocking` in ViewModel tests instead of `runTest` with an injected test dispatcher, producing flaky timing.

## Definition of done

- [ ] Feature split into UI / domain / data with dependencies pointing inward; the domain has zero Android imports and compiles as a plain Kotlin module.
- [ ] State is one immutable `UiState` exposed as `StateFlow` via `stateIn(WhileSubscribed(5_000))`; no public mutable holder.
- [ ] UI collects with `collectAsStateWithLifecycle()`; navigation and transient messages are one-shot effects, not state.
- [ ] ViewModel references no `Context`/`View`/Compose types and survives config change (and process death via `SavedStateHandle` where needed).
- [ ] Repository interface lives in the domain, implementation in the data layer, bound with Hilt `@Binds`; the DB (Room) is the single source of truth and the network writes through it.
- [ ] Distinct DTO, entity, and domain models with explicit, unit-tested pure mapper functions handling nulls/defaults.
- [ ] Hilt types bound at the narrowest correct scope; dispatchers injected via qualifiers, never hardcoded.
- [ ] Tests cover use cases/mappers in plain JUnit, ViewModel state sequences with Turbine + a fake repository and a test dispatcher, and the repository write-through path with in-memory Room / `MockWebServer`.
