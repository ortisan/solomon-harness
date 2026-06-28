# SwiftUI State and Architecture

Model SwiftUI state with the Observation framework (`@Observable`) as the default, drive the UI through one-way data flow from observable models into views and explicit intents back, and let SwiftUI own view identity so diffing stays correct and cheap. Reach for `ObservableObject`/`@Published` only when a deployment target below iOS 17 forces it; everything new in 2026 (iOS 26, Swift 6.2, Xcode 26) should use `@Observable`, `@State`, `@Bindable`, and `@Environment`.

## Observation framework versus ObservableObject

`@Observable` (the `Observation` module, iOS 17+/Swift 5.9+) replaces the `ObservableObject` + `@Published` + `@StateObject`/`@ObservedObject`/`@EnvironmentObject` stack. The decisive difference is granularity: an `ObservableObject` fires `objectWillChange` on *any* `@Published` write, so every view observing it re-renders even if it never reads the property that changed. `@Observable` tracks reads per property inside each `body`, so a view re-renders only when a field it actually used changes. On a list screen with many cells bound to one model this is the difference between O(cells) and O(1) invalidations per mutation.

```swift
import Observation

@Observable
final class ProfileModel {
    var name = ""
    var isLoading = false
    private(set) var posts: [Post] = []   // expose mutation through methods, keep writes one-way

    @ObservationIgnored var analytics: Analytics?   // not UI state; exclude from tracking
}
```

Rules and trade-offs:

- Declare models `final class`. `@Observable` is for reference types; value state stays in `@State` structs.
- There is no `@Published`. Every stored `var` is observed unless annotated `@ObservationIgnored`. Mark caches, injected services, and back-references with `@ObservationIgnored` so they do not invalidate views.
- There is no `objectWillChange` and no `willSet`-based publisher. For non-SwiftUI observers use `withObservationTracking(_:onChange:)`, which fires once for the next change to any property read in the closure (you re-register each cycle).
- `@Observable` does not bridge to `@AppStorage`/`@SceneStorage` or to Combine's `@Published`. Keep persisted scalars in `@AppStorage`; if a model needs a Combine pipeline, expose an `AsyncStream` or keep that one field on a small `ObservableObject`.
- Only drop to `ObservableObject` for iOS 16 or earlier targets, or when interoperating with code that subscribes to `objectWillChange`. Do not mix both protocols on one type.

## @State, @Binding, @Bindable, and @Environment

The property wrappers changed meaning with `@Observable`. Use this mapping and nothing else:

```swift
struct ProfileView: View {
    @State private var model = ProfileModel()       // OWNS the model; was @StateObject
    let userID: User.ID                               // plain input, immutable per identity

    var body: some View {
        @Bindable var model = model                   // local bindings into an @Observable
        Form {
            TextField("Name", text: $model.name)      // two-way binding to a model field
            Toggle("Loading", isOn: $model.isLoading)
            ChildView(model: model)                   // pass the reference; was @ObservedObject
        }
        .task(id: userID) { await model.load(userID) }
    }
}

struct CounterRow: View {
    @Binding var count: Int                            // borrows value state owned by a parent
}
```

- `@State` now owns *both* value types and `@Observable` reference models. SwiftUI instantiates the initial value once per view identity and keeps it across re-renders. Initialize it inline (`= ProfileModel()`); only use `init` + `State(initialValue:)` when the seed depends on a parameter, and accept that the value is captured at first appearance.
- A child that just reads/mutates an `@Observable` takes it as a plain `let model: ProfileModel`. No wrapper is needed because tracking flows through the reference. Use `@Bindable` (or `@Bindable var x = x` inside `body`) only to produce `$`-bindings into the model.
- `@Binding` stays for value-type state lent by a parent (`@Binding var count: Int`), and `$count` derives it.
- `@Environment` replaces `@EnvironmentObject` for `@Observable` models. Inject by type, read by type:

```swift
@Observable final class Session { var currentUser: User? }

WindowGroup { RootView().environment(Session()) }   // inject once at the root

struct AccountView: View {
    @Environment(Session.self) private var session   // type-keyed lookup; traps if not injected
    @Environment(\.dismiss) private var dismiss      // built-in key-path values still apply
}
```

  A missing `@Environment(Type.self)` injection is a runtime trap, not a compile error. For optional cross-cutting state use `@Environment(Type.self) private var session: Session?` so absence yields `nil`.

## MVVM and unidirectional data flow

Keep the view declarative and stateless beyond view-local UI flags; put domain state, validation, and async work in an `@Observable` model. Data flows down (model properties read in `body`), intents flow up (the view calls `async`/sync methods on the model). The view never mutates persisted domain state directly and never holds the source of truth for anything another screen needs.

```swift
@Observable
final class CheckoutModel {
    enum Phase { case idle, submitting, failed(String), done }
    private(set) var phase: Phase = .idle
    var address = Address()

    private let orders: OrderService            // injected dependency, not a singleton

    init(orders: OrderService) { self.orders = orders }

    @MainActor
    func submit() async {
        guard address.isValid else { phase = .failed("Invalid address"); return }
        phase = .submitting
        do { try await orders.place(address); phase = .done }
        catch { phase = .failed(error.localizedDescription) }
    }
}
```

```swift
struct CheckoutView: View {
    @State private var model: CheckoutModel
    init(orders: OrderService) { _model = State(initialValue: CheckoutModel(orders: orders)) }

    var body: some View {
        @Bindable var model = model
        Form {
            AddressFields(address: $model.address)
            Button("Place order") { Task { await model.submit() } }
                .disabled(model.phase == .submitting)
        }
    }
}
```

- Annotate the model (or its mutating methods) `@MainActor` so UI state is mutated on the main actor. With Swift 6 strict concurrency this is enforced; do background work in `nonisolated`/detached helpers and hop back to set published-equivalent fields.
- Represent screen state as one explicit `enum` (`idle`/`loading`/`loaded`/`failed`) rather than a tangle of `isLoading`/`error`/`data` booleans, so impossible combinations are unrepresentable.
- Do not duplicate the same source of truth in two models. Shared state lives in one `@Observable` injected via `@Environment` or passed by reference; views derive from it.

## View identity and diffing

SwiftUI re-evaluates `body` and diffs the result against the previous tree using *identity*. Get identity wrong and you get lost `@State`, animations that snap, or wasted re-renders. Two kinds exist: structural identity (an element's position in the view-tree, the default) and explicit identity (`.id(_:)` or `ForEach` element ids).

- In `ForEach`, give stable, unique ids tied to the data's identity (`Identifiable`, or `id: \.uuid`). Never key on array index or on a value that changes (`id: \.self` on mutable strings), which makes SwiftUI destroy and recreate rows, dropping their state and animations.
- Changing `.id(value)` deliberately resets a subtree and its `@State` — useful to force a clean reload, harmful if applied accidentally to a value that changes every render.
- Prefer `if`/`switch` over erasing to `AnyType`. `AnyView` discards structural identity and defeats SwiftUI's diffing and animation; use it only when the branch count is genuinely dynamic, and measure first.
- Keep `body` pure and cheap. It can run many times per second; the 60 Hz/120 Hz frame budget is ~16ms/~8ms. Do no I/O, no sorting of large arrays, and no allocation of services in `body`. Precompute in the model and read the result.
- Split large views into smaller `View` structs so each subtree diffs independently and only the parts whose inputs changed re-render. Small structs are free; SwiftUI flattens them.
- Use `Equatable` conformance plus `EquatableView`/`.equatable()` sparingly, only on a hot subtree whose inputs are expensive to diff, after profiling with Instruments' SwiftUI template (look at "View body" and "Update" durations).

## NavigationStack with value-based routes

Use `NavigationStack` (iOS 16+) with a value-typed path, not the deprecated `NavigationView`. Routes are `Hashable` values; the destination is resolved by type. This makes navigation data, so you can deep-link, restore, and programmatically pop by mutating the path array.

```swift
enum Route: Hashable {
    case itemDetail(Item.ID)
    case settings
}

struct AppView: View {
    @State private var path: [Route] = []     // typed path; index/replace/pop by editing the array

    var body: some View {
        NavigationStack(path: $path) {
            List(store.items) { item in
                NavigationLink(value: Route.itemDetail(item.id)) { ItemRow(item) }
            }
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .itemDetail(let id): ItemDetailView(id: id)
                case .settings:           SettingsView()
                }
            }
        }
    }
}
```

- Pass identifiers (`Item.ID`) in routes, not whole model objects, so the destination loads fresh state and the route stays cheap to hash and restore.
- Use a typed `[Route]` when one screen has a closed set of destinations; use the type-erased `NavigationPath` only when a stack mixes several unrelated route types. `NavigationPath` is `Codable` when its elements are, which enables state restoration.
- Register one `navigationDestination(for:)` per route type at the stack root; declaring it inside a lazily-built row (e.g. inside `ForEach` content) means it may not be installed before the push and the navigation silently fails.
- For multi-column layouts use `NavigationSplitView` with a selection binding; the same value-route pattern applies to its detail column.
- Programmatic flows mutate `path`: `path.append(.settings)` to push, `path.removeLast()` to pop, `path.removeAll()` to pop to root. Keep `path` in an `@Observable` router when several views or deep-link handlers must drive navigation.

## Dependency injection and previews

Inject dependencies through initializers (for models a view owns) and `@Environment` (for cross-cutting services). Avoid global singletons; they hide coupling and make previews and tests unreliable. Define typed environment values with the `@Entry` macro (Xcode 16+), which removes the old `EnvironmentKey` boilerplate:

```swift
extension EnvironmentValues {
    @Entry var apiClient: APIClient = .live      // default; override per subtree for tests/previews
}

// production
RootView().environment(\.apiClient, .live)
// preview / test
RootView().environment(\.apiClient, .mock)
```

Previews use the `#Preview` macro and should run on injected mocks so they never hit the network and render deterministically. Share preview fixtures with `PreviewModifier` (iOS 18+) so heavy sample data is built once and cached across previews.

```swift
#Preview("Loaded") {
    CheckoutView(orders: .mock)
        .environment(Session.previewLoggedIn)
}

#Preview("Failure", traits: .sizeThatFitsLayout) {
    let model = CheckoutModel(orders: .failing)
    return CheckoutView(model: model)   // seed a specific phase to preview each state branch
}
```

- Provide a protocol (or a struct of closures) per service with `.live` and `.mock` instances; inject `.mock` in previews and tests, `.live` in the app entry point.
- Render every meaningful state (empty, loading, loaded, error) as its own named `#Preview`. Previews that only show the happy path miss the states most likely to break.
- Keep models constructible without side effects so a preview/test can instantiate one and set its fields directly; do not start network calls in `init`.

## Common pitfalls

- Using `@StateObject`/`@ObservedObject`/`@EnvironmentObject` with an `@Observable` type. They do not track it correctly; `@Observable` uses `@State`, plain `let`, and `@Environment`.
- Leaving an injected service or back-reference as a tracked `var` on an `@Observable` model, so unrelated writes invalidate every observing view. Mark non-UI fields `@ObservationIgnored`.
- `ForEach` keyed by array index or by `\.self` on mutable values; rows lose `@State` and animations as the collection changes. Key by stable identity.
- Wrapping branches in `AnyView` and wondering why animations break and re-renders spike. Prefer `if`/`switch`; reserve `AnyView` for truly dynamic, measured cases.
- Doing work in `body` (sorting, formatting large data, allocating a service, network calls). `body` runs on every invalidation; move work into the model.
- Reading `@Environment(Service.self)` without injecting it at the root — a runtime trap. Inject at the app root or type the property as optional.
- Declaring `navigationDestination(for:)` inside lazily-built content instead of at the stack root, causing pushes to do nothing.
- Putting whole model objects inside `Hashable` routes; pass ids and load in the destination.
- Mutating UI state off the main actor under Swift 6 strict concurrency. Annotate the model or its methods `@MainActor`.
- Two screens each holding their own copy of the same source of truth, which drift out of sync. Centralize shared state in one injected `@Observable`.

## Definition of done

- [ ] New models use `@Observable`; `ObservableObject` appears only where a sub-iOS-17 target or Combine interop demands it, never mixed on one type.
- [ ] View state wrappers follow the current mapping: `@State` owns models and value state, `@Bindable` produces model bindings, plain `let` passes models down, `@Environment(Type.self)` injects shared models.
- [ ] Non-UI fields on observable models are `@ObservationIgnored`; UI state mutations run on `@MainActor`.
- [ ] Each screen exposes one explicit state `enum`; data flows down and intents flow up through model methods, with no duplicated sources of truth.
- [ ] `ForEach` keys on stable identity; no `AnyView` on hot paths; `body` does no I/O or heavy work; large views are split into independently-diffing subviews.
- [ ] Navigation uses `NavigationStack` (or `NavigationSplitView`) with `Hashable` value routes carrying ids, one root `navigationDestination(for:)` per route type, and a path that can be restored.
- [ ] Dependencies are injected via initializers and `@Entry` environment values with `.live`/`.mock` variants; no service singletons reached from views.
- [ ] `#Preview`s cover empty/loading/loaded/error states on mock dependencies and never perform network I/O.
- [ ] Re-render hot spots were profiled with the Instruments SwiftUI template before adding `Equatable`/`.id` optimizations.
