# Jetpack Compose UI and Material 3

This skill governs how to build Compose UIs that recompose narrowly, hoist state correctly, and render correct Material 3 theming on Android. The stance: composables are pure, idempotent functions of state; keep them stateless and skippable, push mutable state up to a state holder, and treat every recomposition, side effect, and modifier order as something you justify rather than discover at runtime.

Targets here assume the Compose BOM (`androidx.compose:compose-bom`, 2026.x channel) to align all Compose artifacts, Kotlin 2.2.x with the `org.jetbrains.kotlin.plugin.compose` Gradle plugin, `material3` 1.4.x (Material 3 Expressive is stable), and `material3-adaptive` 1.2.x. Pin versions through the BOM and a version catalog; never mix Compose artifact versions by hand.

## Composition and recomposition model

A `@Composable` function emits UI as a side effect of being called and returns `Unit`. The runtime tracks which composables read which snapshot state (`State<T>`), and when a read value changes it re-invokes only the composables that read it — recomposition. Recomposition can run frequently, out of order, in parallel, and can be cancelled and restarted. Consequences you must design for:

- Composable bodies must be free of observable side effects (no network calls, no mutating shared vars, no `var i++` to count renders). Anything with a lifecycle goes in an effect API.
- Never rely on execution order between sibling composables; they may compose on different threads.
- Expensive work in the body runs on every recomposition unless wrapped in `remember`.

## State and state hoisting

State that drives UI must be snapshot state so reads are tracked:

```kotlin
var query by remember { mutableStateOf("") }   // by-delegate reads/writes .value
```

Hoist that state to the lowest common caller that needs it. A hoisted (stateless) composable takes the value plus an `onValueChange` lambda; it owns nothing, so it is reusable, testable, and previewable:

```kotlin
// Stateless: state down, events up (unidirectional data flow).
@Composable
fun SearchField(query: String, onQueryChange: (String) -> Unit, modifier: Modifier = Modifier) {
    OutlinedTextField(value = query, onValueChange = onQueryChange, modifier = modifier)
}

// Stateful route reads from the ViewModel and is the only place that knows about it.
@Composable
fun SearchRoute(viewModel: SearchViewModel) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()  // lifecycle-runtime-compose
    SearchField(query = state.query, onQueryChange = viewModel::onQueryChange)
}
```

Use `collectAsStateWithLifecycle()` (from `androidx.lifecycle:lifecycle-runtime-compose`), not `collectAsState()`, so collection stops in the background and respects `STARTED`. Screen-level UI state lives in the `ViewModel`; ephemeral, view-only state (scroll position, text-field focus, expanded/collapsed) stays in the composable.

## remember, rememberSaveable, derivedStateOf

- `remember { }` caches a value across recompositions of the same composition. It is lost on configuration change and process death.
- `rememberSaveable { }` additionally survives configuration changes and system-initiated process death by writing to the saved-instance `Bundle`. Use it for UI state the user would be annoyed to lose. Non-`Parcelable`/`Bundle`-able types need a custom `Saver` or `mapSaver`/`listSaver`.
- `derivedStateOf { }` produces a state whose value is computed from other state, and only triggers recomposition of readers when the computed result actually changes. Reach for it only when the inputs change more often than the output:

```kotlin
val listState = rememberLazyListState()
// Recomposes readers only when the boolean flips, not on every scroll pixel.
val showScrollToTop by remember {
    derivedStateOf { listState.firstVisibleItemIndex > 0 }
}
```

Wrapping a cheap, structurally-equal computation in `derivedStateOf` is overhead with no benefit — if a plain expression already recomputes only when its inputs change, do not add it.

## Stability and skippability

A composable is skippable when the runtime can prove that, if none of its inputs changed, its output cannot change — so it can skip re-running. This requires stable parameters. A type is stable when the compiler can rely on `equals`/public-property changes triggering recomposition: all primitives, `String`, function types, and `@Immutable`/`@Stable`-annotated types are stable; `List`, `Set`, `Map`, and other interfaces are unstable because the concrete implementation may be mutable.

```kotlin
@Immutable                                   // promise: public properties never change after construction
data class SearchUiState(
    val query: String,
    val results: ImmutableList<Article>,     // kotlinx.collections.immutable, stable; List is not
)
```

Strong skipping mode is the default since the Kotlin 2.0.20 Compose compiler. With it on, composables with unstable parameters become skippable too: stable params are compared by `equals`, unstable params by instance identity (`===`), and trailing lambdas are auto-remembered. The practical effect: passing a brand-new instance of an unstable type on every recomposition (`tags = listOf(...)` built inline, or a non-remembered object) still forces a re-run because `===` fails. So stability still matters — prefer `ImmutableList`/`persistentListOf`, mark domain models `@Immutable`, and for types you cannot annotate (third-party classes), list them in a stability configuration file:

```kotlin
// build.gradle.kts
composeCompiler {
    stabilityConfigurationFiles.add(rootProject.layout.projectDirectory.file("compose_stability.conf"))
    metricsDestination = layout.buildDirectory.dir("compose_metrics")   // verify skippability
    reportsDestination = layout.buildDirectory.dir("compose_metrics")
}
```

Inspect the generated `*-composables.txt` report to confirm hot composables are `restartable skippable`. Treat a non-skippable composable on a scroll or animation path as a defect.

## Side effects

Use the effect APIs, keyed correctly, for anything that must run as a managed effect of composition:

- `LaunchedEffect(key)` runs a suspending block in the composition's scope; it cancels and restarts when any `key` changes. Key it on the values it depends on — `LaunchedEffect(Unit)` runs once and never reacts, which is a common cause of stale data.
- `DisposableEffect(key)` for effects that need cleanup; register in the body, tear down in the mandatory `onDispose`.
- `rememberCoroutineScope()` to launch coroutines from non-composable callbacks like `onClick`, scoped to the composition.
- `rememberUpdatedState(value)` to read the latest value inside a long-lived effect without restarting it.
- `snapshotFlow { }` to turn snapshot state into a cold `Flow`; `produceState` to turn a `Flow`/callback into `State`.

```kotlin
LaunchedEffect(uiState.errorEvent) {                 // restarts per distinct error
    uiState.errorEvent?.let { snackbarHostState.showSnackbar(it.message) }
}

DisposableEffect(lifecycleOwner) {
    val observer = LifecycleEventObserver { _, e -> if (e == ON_RESUME) analytics.screen("search") }
    lifecycleOwner.lifecycle.addObserver(observer)
    onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
}

val scope = rememberCoroutineScope()
Button(onClick = { scope.launch { listState.animateScrollToItem(0) } }) { Text("Top") }
```

Never start a coroutine with `GlobalScope` or a hand-rolled `CoroutineScope(...)` inside a composable; it leaks past the composition's lifetime.

## Modifier order

Modifiers apply outside-in: each one wraps the result of the chain that follows, so order changes both layout and hit-testing. `padding` before `background` leaves the padded area unpainted; `padding` before `clickable` shrinks the ripple/touch target; `clip` must precede the thing it should clip.

```kotlin
Box(
    Modifier
        .padding(16.dp)        // outer margin, outside the background
        .clip(CardShape)
        .background(surface)
        .clickable { open() }  // ripple fills the clipped, padded box
        .padding(12.dp)        // inner content padding, inside the ripple
)
```

Accept a `modifier: Modifier = Modifier` parameter on every reusable composable, apply it first to the outermost element, and never hardcode size on a reusable component the caller cannot override. Defer state reads into lambda-based modifiers (`Modifier.offset { }`, `graphicsLayer { }`, `drawBehind { }`) so frequently-changing values relayout/redraw only the leaf instead of recomposing the subtree.

## Material 3, theming, and dynamic color

`MaterialTheme` exposes `colorScheme`, `typography`, and `shapes` through `LocalContentColor` and friends; read tokens via `MaterialTheme.colorScheme.primary`, never hardcoded `Color(0xFF...)`. Dynamic color (Material You) derives the scheme from the user's wallpaper and requires API 31+ (`Build.VERSION_CODES.S`); fall back to a brand scheme below that and for users who disable it.

```kotlin
@Composable
fun AppTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val supportsDynamic = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
    val context = LocalContext.current
    val colorScheme = when {
        supportsDynamic && darkTheme -> dynamicDarkColorScheme(context)
        supportsDynamic            -> dynamicLightColorScheme(context)
        darkTheme                  -> darkColorScheme()      // your brand fallback
        else                       -> lightColorScheme()
    }
    MaterialTheme(colorScheme = colorScheme, typography = AppTypography, content = content)
}
```

For the Material 3 Expressive system (`material3` 1.4.x) use `MaterialExpressiveTheme` with a `MotionScheme` to get the expressive shape, color, and spring-based motion tokens, plus components such as `ButtonGroup`, `FloatingToolbar`, and the expressive loading indicators. For multi-pane layouts on large screens and foldables, drive layout from `WindowSizeClass` and use `material3-adaptive` scaffolds (`NavigableListDetailPaneScaffold`) rather than branching on raw width. Use `Scaffold` for top bar, FAB, and snackbar slots so insets and overlaps are handled for you, and enable edge-to-edge with `enableEdgeToEdge()` plus `Modifier.windowInsetsPadding`/`safeDrawingPadding`.

## Lazy lists and stable keys

`LazyColumn`/`LazyRow`/`LazyVerticalGrid` compose only visible items. Always supply a stable, unique `key` per item; without it, the default is the index, so inserts/removals/reorders misattribute item state, lose scroll position, restart animations, and break `animateItem()`. Add `contentType` when the list is heterogeneous so the runtime reuses compositions across same-typed items.

```kotlin
LazyColumn(state = listState) {
    items(items = articles, key = { it.id }, contentType = { "article" }) { article ->
        ArticleRow(article, modifier = Modifier.animateItem())
    }
}
```

Pass a stable, immutable list (`ImmutableList`) to keep the list lambda skippable, and hoist `rememberLazyListState()` if you read scroll position or scroll programmatically. Do not nest a scrollable `LazyColumn` inside a vertically scrolling parent of the same axis; it throws or measures with infinite constraints.

## Previews

Build with stateless composables so previews need no ViewModel or DI. Drive sample data through a `PreviewParameterProvider`, and use the multipreview annotations to render variants without hand-writing each `@Preview`:

```kotlin
class ArticleProvider : PreviewParameterProvider<Article> {
    override val values = sequenceOf(Article("1", "Short"), Article("2", "A much longer headline"))
}

@PreviewLightDark          // light + dark
@PreviewFontScales         // default through largest accessibility scale
@Composable
private fun ArticleRowPreview(@PreviewParameter(ArticleProvider::class) article: Article) {
    AppTheme { Surface { ArticleRow(article) } }
}
```

`@PreviewScreenSizes`, `@PreviewDynamicColors`, and a custom multipreview annotation (a single `@Preview`-annotated annotation class you reuse) cover form factors and theming. Previews validate font scaling, dark mode, and RTL early; keep providers small so the preview pane stays responsive.

## Common pitfalls

- `mutableStateOf` not wrapped in `remember`: the state resets to its initial value on every recomposition and never appears to change. Reviewer should reject.
- `LaunchedEffect(Unit)` (or `true`) where the effect depends on a changing value; it runs once and ignores later changes. Key it on the dependency.
- Using `collectAsState()` instead of `collectAsStateWithLifecycle()`, leaving flows collecting while the screen is backgrounded.
- Passing `List`/`Set`/`Map` parameters and inline-building them each recomposition; identity changes break `===` skipping. Use `ImmutableList`/`persistentListOf` or `@Immutable` models.
- `LazyColumn` items without a `key`, so item state and scroll position jump on insert/remove and `animateItem` glitches.
- Reading high-frequency state (scroll offset, animation value) at a high level in the tree, recomposing a large subtree instead of deferring the read into a `graphicsLayer`/`offset { }` lambda.
- Hand-rolled `CoroutineScope` or `GlobalScope` inside a composable instead of `rememberCoroutineScope()`; it leaks and outlives the composition.
- Hardcoded `Color`, `dp` typography, or `Color(0xFF...)` instead of `MaterialTheme` tokens, which breaks dark mode and dynamic color.
- Calling `dynamicLightColorScheme`/`dynamicDarkColorScheme` without an API 31 guard, crashing on older devices.
- `derivedStateOf` wrapped around a cheap value that already changes only with its inputs: pure overhead.
- Side effects in the composable body (counting renders, mutating shared state, I/O), which run unpredictably and out of order.
- Modifier order bugs: `padding` before `background`/`clickable` shrinking paint or touch targets; missing `clip` so a shape does not actually clip.

## Definition of done

- [ ] Screen state is hoisted to a `ViewModel`; leaf composables are stateless, take `state` plus event lambdas, and accept a `modifier: Modifier = Modifier` applied to the outer element.
- [ ] Flows are read with `collectAsStateWithLifecycle()`; all `mutableStateOf` is wrapped in `remember`/`rememberSaveable`, with `rememberSaveable` for state that must survive config change and process death.
- [ ] Hot composables are `restartable skippable` per the Compose compiler metrics report; UI state models are `@Immutable` and use `ImmutableList` (or are covered by a stability configuration file).
- [ ] Effects use the correct API (`LaunchedEffect`/`DisposableEffect`/`rememberCoroutineScope`/`snapshotFlow`) keyed on their real dependencies; no `GlobalScope` or hand-built scopes, and `DisposableEffect` always has `onDispose`.
- [ ] `derivedStateOf` is used only where inputs change more often than the output; no plain cheap expressions are wrapped in it.
- [ ] All colors, type, and shapes come from `MaterialTheme` tokens; dynamic color is API-31-guarded with a brand fallback; edge-to-edge insets are handled via `Scaffold`/window-inset modifiers.
- [ ] Lazy lists supply a stable unique `key` (and `contentType` when heterogeneous) and receive an immutable item list.
- [ ] Composables have previews using `@PreviewParameter` and multipreview annotations covering light/dark, font scales, and relevant screen sizes; large-screen layouts branch on `WindowSizeClass` via adaptive scaffolds.
- [ ] Compose UI tests (`createComposeRule`, semantics matchers) cover the stateless composables; no test depends on real DI or network.
