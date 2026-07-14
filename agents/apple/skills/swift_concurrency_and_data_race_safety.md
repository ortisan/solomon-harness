---
name: swift-concurrency-and-data-race-safety
description: Governs Swift 6 strict concurrency checking, Sendable conformance and isolation domains, actor reentrancy, main-actor isolation, structured concurrency, cancellation, and migrating completion handlers and Combine to async/await. Use when writing or reviewing concurrent Swift code, resolving a Sendable or actor-isolation diagnostic, or migrating a target to Swift 6 language mode.
---

# Swift Concurrency and Data-Race Safety

Use Swift 6 language mode so the compiler proves the absence of data races at build time, with isolation expressed through `Sendable`, actors, and `@MainActor` rather than locks and dispatch queues. The stance is: every mutable state lives in exactly one isolation domain, all asynchronous work is structured and cancellation-aware, and the main actor is reserved for UI updates and never blocked. Adopt the Swift 6.2 "Approachable Concurrency" defaults so single-module app targets are `@MainActor` by default and you opt into background execution explicitly.

## Language mode and strict checking

- Swift 6.2 ships with Xcode 26 (the 2025/2026 baseline). Set the language mode per target, not per file: `SWIFT_VERSION = 6` in Xcode, or `swiftLanguageModes: [.v6]` in `Package.swift`. Swift 6 mode turns data-race violations into errors; Swift 5 mode with `-strict-concurrency=complete` (`SWIFT_STRICT_CONCURRENCY = complete`) turns the same diagnostics into warnings and is the migration on-ramp.
- Migrate incrementally: flip to `complete` warnings first, resolve them module by module, then switch the language mode to 6. Do not flip a large target straight to Swift 6 mode and bury the build in errors.
- Adopt Swift 6.2 defaults for app targets. In `Package.swift`:

```swift
.target(
    name: "App",
    swiftSettings: [
        .defaultIsolation(MainActor.self),                          // SE-0466
        .enableUpcomingFeature("NonisolatedNonsendingByDefault"),   // SE-0461
        .enableUpcomingFeature("InferIsolatedConformances"),        // SE-0470, isolated conformances
    ]
)
```

  In Xcode the equivalents are "Default Actor Isolation = MainActor" (`SWIFT_DEFAULT_ACTOR_ISOLATION`) and "Approachable Concurrency = YES" (`SWIFT_APPROACHABLE_CONCURRENCY`). `defaultIsolation(MainActor.self)` makes UI-layer code single-threaded by default and removes the bulk of spurious `Sendable` errors in app targets; keep library targets at `nonisolated` default and annotate explicitly.

## Sendable and isolation domains

`Sendable` marks a type safe to cross isolation domains. An isolation domain is a region the compiler proves is only ever touched by one task or actor at a time.

- Value types whose stored properties are all `Sendable` are inferred `Sendable` (structs, enums). Final classes with only immutable `Sendable` `let` properties are `Sendable`. Everything else needs a deliberate decision.
- Prefer immutability or an actor over `@unchecked Sendable`. `@unchecked Sendable` is an unaudited promise; the compiler stops checking. When you must hold mutable state in a reference type shared across domains, protect it with `Mutex` from the Synchronization framework (SE-0433, iOS 18 / macOS 15+) instead of a hand-rolled `NSLock`:

```swift
import Synchronization

final class ImageCache: Sendable {                 // no @unchecked needed
    private let storage = Mutex<[URL: Data]>([:])
    func data(for url: URL) -> Data? { storage.withLock { $0[url] } }
    func store(_ data: Data, for url: URL) { storage.withLock { $0[url] = data } }
}
```

- `@Sendable` closures capture only `Sendable` values. `sending` parameters and results (SE-0430) let you pass a non-`Sendable` value across a boundary by transferring ownership: the compiler proves the sender no longer uses it (region-based isolation, SE-0414). Reach for `sending` before `@unchecked`.
- For a genuinely externally-synchronized global, `nonisolated(unsafe)` silences the diagnostic on a single declaration without making the whole type unsafe. Use it sparingly and comment why it is safe.

## Actors and global actors

An `actor` serializes access to its mutable state; the compiler forces `await` on every cross-actor call.

```swift
actor BalanceStore {
    private var balance: Int = 0

    func deposit(_ amount: Int) { balance += amount }      // synchronous inside the actor

    func withdraw(_ amount: Int) async throws {
        guard balance >= amount else { throw PaymentError.insufficient }
        try await ledger.record(.debit(amount))            // suspension point
        guard balance >= amount else { throw PaymentError.insufficient } // re-check
        balance -= amount
    }
}
```

- Actor reentrancy is the trap: every `await` is a suspension point where other tasks can mutate the actor's state. Re-validate invariants after each `await`, as the second `guard` above does. Never assume state is unchanged across a suspension.
- `nonisolated` members run outside the actor and may not touch isolated state; use it for pure helpers so callers avoid an unnecessary hop:

```swift
@MainActor
final class PriceFormatter {
    nonisolated func string(from value: Decimal) -> String { /* no actor state */ }
}
```

- Custom global actors serialize state spread across many types:

```swift
@globalActor
actor StorageActor { static let shared = StorageActor() }

@StorageActor final class DiskWriter { /* every member isolated to StorageActor */ }
```

- When a synchronous callback from a framework is documented to arrive on a specific actor, assert it rather than dispatching: `MainActor.assumeIsolated { self.refresh() }` runs synchronously and traps if the precondition is violated. This is the correct replacement for `DispatchQueue.main.async` inside a known-main callback.

## Main actor isolation

- `@MainActor` on a view model, `@Observable` class, or single method pins it to the main thread. With `defaultIsolation(MainActor.self)`, app types get this implicitly; library and CPU-bound types must be annotated or moved off main explicitly.

```swift
@MainActor @Observable
final class CheckoutViewModel {
    private(set) var isLoading = false
    private(set) var items: [Item] = []
    private let repository: ItemRepository           // actor or Sendable

    func load() async {
        isLoading = true
        defer { isLoading = false }
        items = await repository.fetchItems()        // hops off main only inside repository
    }
}
```

- In Swift 6.2 with `NonisolatedNonsendingByDefault`, a `nonisolated` async function runs on the caller's actor instead of hopping to the global executor, so calling it from `@MainActor` does not silently leave the main actor and back. To force CPU-heavy work onto the global concurrent executor, mark it `@concurrent`:

```swift
@concurrent
func resized(_ image: CGImage, to size: CGSize) async -> CGImage { /* heavy */ }
```

  This pairing is the rule: default to staying on the caller's actor, and only spend a thread hop where the work is genuinely expensive and `Sendable`-clean.

## Structured concurrency

Prefer structured concurrency (`async let`, task groups) over unstructured `Task {}`. Structured children inherit cancellation, priority, and task-local values, and the parent cannot return until they finish.

```swift
async let profile = api.profile(id)            // both requests run concurrently
async let orders  = api.orders(id)
let dashboard = try await Dashboard(profile: profile, orders: orders)
```

```swift
func thumbnails(for urls: [URL]) async throws -> [URL: CGImage] {
    try await withThrowingTaskGroup(of: (URL, CGImage).self) { group in
        for url in urls { group.addTask { (url, try await renderThumbnail(url)) } }
        var result: [URL: CGImage] = [:]
        for try await (url, image) in group { result[url] = image }   // cancels siblings on throw
        return result
    }
}
```

- Use `withDiscardingTaskGroup` (SE-0381) for fire-and-forget fan-out with no results; it reaps children eagerly and avoids unbounded memory growth. `Task {}` (unstructured) inherits the enclosing actor isolation in Swift 6; `Task.detached {}` does not and starts `nonisolated`. Reserve unstructured tasks for bridging into non-async entry points (a SwiftUI `.task` modifier is the preferred place); store the handle so you can cancel it.

## Cancellation

Cancellation is cooperative: a cancelled task keeps running until the code checks. Always check.

```swift
func sync(_ batches: [Batch]) async throws {
    for batch in batches {
        try Task.checkCancellation()        // throws CancellationError
        try await upload(batch)
    }
}
```

- Check `Task.isCancelled` or call `try Task.checkCancellation()` before expensive or irreversible steps. `Task.sleep(for:)` already throws on cancellation; never use a blocking `sleep`.
- Bridge cancellation into callback APIs with `withTaskCancellationHandler`:

```swift
let result = try await withTaskCancellationHandler {
    try await withCheckedThrowingContinuation { continuation in
        let op = client.start { continuation.resume(with: $0) }
        cancelBox.store(op)
    }
} onCancel: {
    cancelBox.cancel()                      // runs immediately on cancellation
}
```

## Async sequences

- Consume streams with `for await`/`for try await`. Build an `AsyncStream` to adapt a delegate or callback source, and always set `onTermination` to release the underlying resource:

```swift
func locationUpdates() -> AsyncStream<CLLocation> {
    AsyncStream { continuation in
        let delegate = LocationDelegate { continuation.yield($0) }
        manager.delegate = delegate
        continuation.onTermination = { _ in manager.stopUpdatingLocation() }
        manager.startUpdatingLocation()
    }
}
```

- Choose the buffering policy explicitly (`AsyncStream(bufferingPolicy: .bufferingNewest(1))`) for high-rate producers, otherwise an unbounded buffer grows without backpressure. Use `AsyncThrowingStream` when the source can fail.

## Migrating completion handlers and Combine

- Wrap a one-shot completion handler with `withCheckedThrowingContinuation`. Resume exactly once: `CheckedContinuation` traps on double-resume or leak (use it in debug; `UnsafeContinuation` skips the check and is only for proven-hot paths).

```swift
func fetch(_ url: URL) async throws -> Data {
    try await withCheckedThrowingContinuation { continuation in
        legacyClient.load(url) { result in
            continuation.resume(with: result)          // map to Result, resume once
        }
    }
}
```

- Bridge Combine with `Publisher.values`, which exposes the publisher as an `AsyncSequence`; do not route the migration through a stored `Set<AnyCancellable>` plus a continuation when a direct bridge exists.

```swift
for await user in userSubject.values { updateUI(user) }   // @MainActor context
```

- For an SDK not yet annotated for concurrency, `@preconcurrency import SomeSDK` suppresses `Sendable` warnings at the boundary until the vendor updates; remove the attribute once they do.
- Never block the main actor to bridge async into sync. `DispatchQueue.main.sync`, a `DispatchSemaphore.wait()` that waits on a `Task`, or `Task { ... }.value` read from a synchronous main-thread path all deadlock or stall the UI. Make the caller `async`, or hop with `await MainActor.run { ... }` from a `nonisolated` context.

## Common pitfalls

- `@unchecked Sendable` slapped on a mutable class to silence the compiler, with no actual synchronization. It disables the one check that would have caught the race. Use an actor or `Mutex`.
- Assuming actor state is unchanged across an `await`. Reentrancy lets other tasks mutate it; invariants must be re-checked after every suspension point.
- A continuation resumed twice or never resumed. Double-resume crashes; a leak hangs the awaiting task forever. Every code path through the callback must resume exactly once.
- CPU-bound work left on `@MainActor`, freezing the UI. Move it to an actor or a `@concurrent` function; do not parse, resize, or crunch on main.
- `Task.detached` used as a default for background work, dropping cancellation, priority, and task-local context. Prefer structured tasks or an actor; reserve detached for the rare truly-independent job.
- Loops with `await` that never call `Task.checkCancellation()`; the task ignores cancellation and wastes work after the user navigated away.
- `DispatchQueue.main.async` sprinkled inside code that is already `@MainActor`, or `DispatchQueue.main.sync` from a background context to touch UI. Use `@MainActor` isolation or `MainActor.assumeIsolated`.
- An `AsyncStream` with no `onTermination`, leaking the timer, observer, or manager that feeds it. The same applies to `nonisolated(unsafe)` used to dodge a diagnostic without real external synchronization.

## Definition of done

- [ ] The target builds clean in Swift 6 language mode (`SWIFT_VERSION = 6` / `swiftLanguageModes: [.v6]`), or at minimum with `-strict-concurrency=complete` and zero warnings, as the documented interim step.
- [ ] App/UI targets use `defaultIsolation(MainActor.self)` and `NonisolatedNonsendingByDefault`; background and CPU-bound work is explicitly `@concurrent` or actor-isolated.
- [ ] All shared mutable reference types are `Sendable` via an actor, immutability, or `Mutex`/`Atomic`; `@unchecked Sendable` and `nonisolated(unsafe)` appear only where externally synchronized and commented.
- [ ] Actor methods re-validate invariants after every `await`; reentrancy is accounted for, not assumed away.
- [ ] Asynchronous work is structured (`async let`, task groups) wherever possible; unstructured `Task` handles are stored and cancellable; `Task.detached` is justified case by case.
- [ ] Long-running and looping operations check `Task.checkCancellation()`/`Task.isCancelled`, and callback bridges install `withTaskCancellationHandler`.
- [ ] Every continuation resumes exactly once on all paths; `CheckedContinuation` is used outside proven hot paths.
- [ ] No main-actor blocking: no `DispatchQueue.main.sync`, no semaphore/`.value` waits from main; UI updates run on `@MainActor`.
- [ ] `AsyncStream`/`AsyncThrowingStream` adapters set `onTermination` and a deliberate buffering policy; Combine migrations use `Publisher.values`.
- [ ] Tests run with Swift Testing or XCTest under Swift 6 checking; `@MainActor` test suites and `await confirmation` cover the async paths, and no test relies on sleeps for synchronization.
