---
name: swiftdata-and-persistence
description: Governs SwiftData model design with @Model, ModelContainer and ModelActor concurrency, #Predicate and FetchDescriptor querying, VersionedSchema migration plans, Core Data interop, and CloudKit sync constraints. Use when designing or reviewing local persistence, a schema migration, background data import, or iCloud sync on Apple platforms.
---

# SwiftData and Persistence

SwiftData is the default local persistence layer for new Apple apps targeting iOS 17 and later, and Core Data is the fallback you reach for only when you need an API SwiftData does not yet expose. Model the schema as code, version it from day one, do all mutation through a `ModelContext` bound to a known actor, and treat the on-device store as the source of truth so the UI works offline and syncs opportunistically.

## Choosing SwiftData vs Core Data (2026)

SwiftData ships on iOS 17+, iPadOS 17+, macOS 14+, watchOS 10+, tvOS 17+, and visionOS 1+. It is built on top of the Core Data stack (an `NSPersistentContainer` lives underneath), so the two interoperate against the same SQLite store. Baseline by OS: iOS 18 added `#Index`, `#Unique`, and history tracking (`DefaultHistory`); iOS 26 added class inheritance for `@Model` types. Build with Swift 6.2 / Xcode 26 and turn on strict concurrency checking.

- Default to SwiftData for new code: less boilerplate, `@Query` drives SwiftUI directly, schema is the Swift type.
- Stay on or drop to Core Data when you need `NSFetchedResultsController` with sectioned diffing, `NSBatchUpdateRequest` / `NSBatchDeleteRequest` at scale, fine-grained `NSMergePolicy` conflict handling, or `NSPersistentCloudKitContainer` sharing — SwiftData does not expose these as of 2026.
- Do not mix UI frameworks pointlessly: if the app is UIKit/AppKit-only, Core Data is still a defensible choice; SwiftData's payoff is highest with SwiftUI.

## Modeling with @Model

```swift
import SwiftData

@Model
final class Trip {
    #Unique<Trip>([\.name, \.startDate])          // app-level uniqueness (iOS 18+)
    #Index<Trip>([\.startDate], [\.name, \.startDate])

    var name: String
    var startDate: Date
    @Attribute(.externalStorage) var coverPhoto: Data?   // store large blobs out of the row
    @Relationship(deleteRule: .cascade, inverse: \LodgingReservation.trip)
    var lodging: [LodgingReservation] = []
    @Transient var isSelected: Bool = false               // never persisted

    init(name: String, startDate: Date) {
        self.name = name
        self.startDate = startDate
    }
}
```

- `@Model` requires a `final class` (reference semantics; SwiftData tracks identity). Stored properties must be persistable or `@Transient`.
- `@Attribute(.externalStorage)` keeps binary data outside the SQLite row; apply it to anything over roughly 100 KB so fetches stay cheap. `@Attribute(.unique)` enforces uniqueness in the local store but is incompatible with CloudKit (see below) — prefer `#Unique` plus app-side checks when you sync.
- Always set the `inverse:` on one side of a relationship and let SwiftData infer the other; declaring it on both sides creates an ambiguous graph. Pick the delete rule deliberately: `.cascade` deletes children, `.nullify` orphans them.
- Give every non-optional property a default value or initialize it in `init`. This is required for CloudKit and makes lightweight migration possible.

## Containers, contexts, and the main actor

```swift
@main
struct TravelApp: App {
    let container: ModelContainer = {
        let config = ModelConfiguration(schema: Schema([Trip.self]), isStoredInMemoryOnly: false)
        return try! ModelContainer(for: Trip.self, migrationPlan: TripMigrationPlan.self,
                                   configurations: config)
    }()

    var body: some Scene {
        WindowGroup { ContentView() }
            .modelContainer(container)   // injects container.mainContext into the environment
    }
}
```

- One `ModelContainer` per store for the app's lifetime; creating extra containers against the same URL corrupts coordination. Use `isStoredInMemoryOnly: true` for previews and unit tests so each run is isolated and disposable.
- `container.mainContext` is `@MainActor`-bound and is what `@Query` and `@Environment(\.modelContext)` read. Mutate it only on the main actor.
- Autosave is on by default and flushes on UI lifecycle events; still call `try context.save()` explicitly before a flow you must guarantee is durable (handing an ID to a background task, app termination). Set `context.autosaveEnabled = false` only when you batch many writes and save once.

## Querying: @Query, #Predicate, FetchDescriptor

```swift
struct TripList: View {
    @Query(filter: #Predicate<Trip> { $0.startDate > .now },
           sort: \Trip.startDate, order: .forward)
    private var upcoming: [Trip]
    var body: some View { List(upcoming) { Text($0.name) } }
}
```

For imperative fetches outside SwiftUI use `FetchDescriptor`:

```swift
var descriptor = FetchDescriptor<Trip>(
    predicate: #Predicate { $0.lodging.isEmpty == false && $0.name.localizedStandardContains(term) },
    sortBy: [SortDescriptor(\.startDate, order: .reverse)]
)
descriptor.fetchLimit = 50
descriptor.relationshipKeyPathsForPrefetching = [\.lodging]   // avoid N+1 fault-ins
let trips = try context.fetch(descriptor)
let total = try context.fetchCount(descriptor)                // count without materializing
```

- `#Predicate` compiles to a store query, so it accepts only operations SwiftData can translate: comparisons, `&&`/`||`/`!`, `contains`, `localizedStandardContains`, `count`, optional flattening. It cannot call arbitrary Swift functions, computed properties, or `@Transient` fields — those force an in-memory `filter` over the full table.
- Set `fetchLimit` for any list that can grow; prefetch relationships you will read in a loop. Use `fetchCount` for badges and pagination instead of fetching and counting in Swift.
- Make `@Query` parameters reactive by passing them through an `init`; a predicate captured once never updates when the search term changes.

## Concurrency and ModelActor

`ModelContext` and `PersistentModel` are not `Sendable`. Never pass a model instance or a context across an actor boundary; pass the `Sendable` `PersistentIdentifier` and re-fetch on the target context.

```swift
@ModelActor
actor TripStore {
    func importTrips(_ payloads: [TripDTO]) throws -> [PersistentIdentifier] {
        let inserted = payloads.map { dto -> Trip in
            let trip = Trip(name: dto.name, startDate: dto.startDate)
            modelContext.insert(trip)
            return trip
        }
        try modelContext.save()
        return inserted.map(\.persistentModelID)   // hand IDs back, not the objects
    }
}

let store = TripStore(modelContainer: container)         // its own background context
let ids = try await store.importTrips(decoded)
let trip = container.mainContext.model(for: ids[0]) as? Trip   // re-resolve on main actor
```

- `@ModelActor` synthesizes a private `modelContext` on the actor's executor and a `modelContainer` property. Use it for decoding, bulk import, and any write that would otherwise block the main actor.
- Resolve a `PersistentIdentifier` on a context with `context.model(for:)`. A model fetched on one context is invalid on another; re-fetch, do not capture.
- Save in reasonable batches (for example every 500–1000 inserts) for large imports to bound memory and transaction size, then `modelContext.save()`.

## Schema migration: VersionedSchema and MigrationPlan

Pin every shipped schema as a `VersionedSchema` and connect them with a `SchemaMigrationPlan`. This is the difference between an additive change that migrates silently and one that throws on launch for every existing user.

```swift
enum TripSchemaV1: VersionedSchema {
    static var versionIdentifier = Schema.Version(1, 0, 0)
    static var models: [any PersistentModel.Type] { [Trip.self] }
    @Model final class Trip { var name: String = ""; var startDate: Date = .now }
}

enum TripSchemaV2: VersionedSchema {
    static var versionIdentifier = Schema.Version(2, 0, 0)
    static var models: [any PersistentModel.Type] { [Trip.self] }
    @Model final class Trip {
        @Attribute(.unique) var name: String = ""       // new constraint => needs a custom stage
        @Attribute(originalName: "startDate") var departs: Date = .now   // rename stays lightweight
    }
}

enum TripMigrationPlan: SchemaMigrationPlan {
    static var schemas: [any VersionedSchema.Type] { [TripSchemaV1.self, TripSchemaV2.self] }
    static var stages: [MigrationStage] { [v1toV2] }

    static let v1toV2 = MigrationStage.custom(
        fromVersion: TripSchemaV1.self, toVersion: TripSchemaV2.self,
        willMigrate: { ctx in                       // dedupe before the unique constraint applies
            let trips = try ctx.fetch(FetchDescriptor<TripSchemaV1.Trip>())
            // resolve collisions on `name` here, then save
            try ctx.save()
        },
        didMigrate: nil)
}
```

- Lightweight (`MigrationStage.lightweight`) covers additive changes: new optional property, new property with a default, a rename via `@Attribute(originalName:)`. SwiftData infers the mapping and migrates in place with no data movement.
- Heavyweight (`MigrationStage.custom`) is mandatory when data must be transformed or validated: adding `@Attribute(.unique)` to existing rows, splitting or merging properties, changing a property's type, or backfilling derived values. Do the work in `willMigrate`/`didMigrate`; this maps to Core Data's custom `NSEntityMigrationPolicy`.
- Never edit a schema that has already shipped. Add a new `VersionedSchema` and a stage. Keep the old versioned types compiled so the plan can read the old store.
- Test migrations by seeding a store at the old version in a temporary file and opening it with the new container; assert row counts and field values survive.

## Core Data interop

SwiftData and Core Data can share one store because SwiftData is built on Core Data.

- Generate an `NSManagedObjectModel` from SwiftData types with `NSManagedObjectModel.makeManagedObjectModel(for: [Trip.self])`, point an `NSPersistentContainer` at the same store URL, and the two stacks coexist as long as entity names, attribute names, and versioning match exactly.
- Use this to migrate an existing Core Data app incrementally: keep heavy batch operations or `NSFetchedResultsController` on the Core Data side while new features read and write through SwiftData against the same file.
- Drive a SwiftUI list off a Core Data store with `@FetchRequest`; the SwiftData `@Query` equivalent only works against a `ModelContainer`. Do not run two independent stacks on the same file with mismatched models — the second one to open will fail validation or migrate destructively.

## Offline state, CloudKit sync, and conflicts

- Enable iCloud sync with `ModelConfiguration(..., cloudKitDatabase: .automatic)` or `.private("iCloud.com.example.app")`. CloudKit imposes hard schema rules: every property must be optional or have a default, every relationship must be optional, and `@Attribute(.unique)` is forbidden (CloudKit has no unique constraint). Enforce uniqueness in the app, not the store.
- The local store is the source of truth. Writes land on disk immediately and queue for sync, so build optimistic UI that reads the local context and never blocks on the network. Use `NWPathMonitor` (Network framework) to surface an offline indicator, not to gate writes.
- CloudKit reconciles concurrently edited records with last-writer-wins per field; there is no custom `NSMergePolicy` hook in SwiftData. When LWW is unacceptable (counters, shared edits), model an append-only event log or CRDT and fold it locally instead of mutating shared fields.
- For your own backend sync or auditing, use history tracking (iOS 18+): `try context.fetchHistory(HistoryDescriptor<DefaultHistoryTransaction>())` returns inserted/updated/deleted changes since a stored `HistoryToken`. Persist the token, push deltas, and trim history so it does not grow unbounded.
- Encrypt sensitive fields at the property level with `@Attribute(.allowsCloudEncryption)` and rely on Data Protection for the file; never store secrets or tokens in the model unencrypted.

## Common pitfalls

- Mutating a model or `ModelContext` off the main actor without an actor that owns it. `PersistentModel` is not `Sendable`; this is a data race that strict concurrency will flag and that crashes intermittently in release.
- Passing a fetched model object between actors instead of its `PersistentIdentifier`, then reading it on the wrong context — the object is invalid and faults or returns stale data.
- A `#Predicate` that calls a Swift function, computed property, or `@Transient` field: it silently falls back to loading the whole table into memory and filtering, which scales linearly with row count.
- Editing an already-shipped `VersionedSchema` in place instead of adding a new version and a migration stage, which throws `SwiftDataError` on launch for every existing user.
- Adding `@Attribute(.unique)` to an existing entity with only a lightweight stage; existing duplicate rows make the migration fail. Use a custom stage that dedupes in `willMigrate`.
- Renaming a property without `@Attribute(originalName:)`, which drops the old column's data instead of migrating it.
- Enabling CloudKit with non-optional, default-less properties, `.unique` attributes, or required relationships — the container fails to initialize at runtime.
- Creating more than one `ModelContainer` for the same store URL, or running a parallel Core Data stack with a mismatched model, corrupting store coordination.
- Large `Data` stored inline without `.externalStorage`, bloating every row and slowing unrelated fetches.
- Unbounded `@Query`/`FetchDescriptor` with no `fetchLimit` on a growing table, loading thousands of objects into a view.

## Definition of done

- [ ] Every `@Model` is a `final class` with defaults or `init` for non-optional properties; relationships declare `inverse:` and an intentional delete rule.
- [ ] Large binary fields use `@Attribute(.externalStorage)`; uniqueness uses `#Unique`/`.unique` and is also enforced in app code when CloudKit is on.
- [ ] Exactly one `ModelContainer` per store; in-memory configuration used for previews and tests.
- [ ] All background mutation runs through an `@ModelActor`; only `PersistentIdentifier` crosses actor boundaries, and models are re-fetched on the target context.
- [ ] Queries use `#Predicate` operations the store can translate, set `fetchLimit` on growing lists, and prefetch relationships read in loops; counts use `fetchCount`.
- [ ] Schema is versioned with `VersionedSchema`; a `SchemaMigrationPlan` covers every shipped-to-shipped transition, with custom stages for non-additive changes and `originalName` for renames.
- [ ] Migrations are tested against a seeded old-version store; row counts and field values are asserted to survive.
- [ ] CloudKit schema (when used) satisfies all-optional/default constraints, drops `.unique`, and conflict semantics beyond last-writer-wins are handled with an event log, not shared-field mutation.
- [ ] UI reads the local store and works offline; writes are optimistic; connectivity is surfaced with `NWPathMonitor`, not used to block writes.
- [ ] Core Data interop, if present, shares one store URL with matching model, names, and versioning; no second uncoordinated stack opens the same file.
