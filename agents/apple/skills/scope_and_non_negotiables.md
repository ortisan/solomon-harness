---
name: scope-and-non-negotiables
description: Governs the default Apple stack and Swift 6 concurrency mode, @Observable MVVM architecture, UIKit/AppKit interop boundary, minimum-deployment-target policy, strict TDD, and the handoff boundary with the auth_engineer and sre agents. Use when scoping a new Apple-platform task, choosing a deployment target or API availability gate, or deciding whether work belongs to the apple agent or should be handed off.
---

# Scope and Non-Negotiables

Every Apple-platform feature in this harness ships as Swift + SwiftUI under the Swift 6 language mode with complete data-race checking, an `@Observable` MVVM core with unidirectional flow, and a test written before the code. This skill is the working standard: it fixes the default stack, the concurrency model, the deployment-target floor, what the apple specialist owns versus hands off, and the bar a reviewer rejects against. Treat deviations (a UIKit screen, a lowered minimum target, an untested code path) as exceptions that need an explicit, recorded reason, not as discretionary choices.

## Default stack and versions (2026)

- Toolchain: Xcode 26.x with the bundled Swift 6.2 compiler. The Swift 6 language mode is mandatory on every target (`SWIFT_VERSION = 6.0` or the Package.swift `swiftLanguageModes: [.v6]`). Swift 5 mode is allowed only on a third-party dependency you do not control.
- UI: SwiftUI is the default and the framework you reach for first. UIKit (iOS/iPadOS/tvOS) and AppKit (macOS) are interop layers, used only where SwiftUI lacks the control or the API is UIKit/AppKit-only.
- Architecture: MVVM with one-way data flow. View models are plain `@Observable` reference types isolated to `@MainActor`; dependencies arrive by injection, never via singletons reached from inside the view model.
- Concurrency: Swift Concurrency (`async`/`await`, actors, structured `Task`s). Combine is permitted only where a genuinely reactive pipeline fits (for example bridging `NotificationCenter` or a Core Data publisher); it is not the default for one-shot async work.
- Persistence: SwiftData on the current target, Core Data when a feature needs an API SwiftData has not yet exposed (custom migrations, fine-grained fetch tuning) or when the deployment floor predates SwiftData.
- Networking: `URLSession` with `async` methods and `Codable`. No third-party HTTP client unless a requirement (multipart streaming, background transfer ergonomics) justifies it and it is recorded.
- Lint/format: `swift-format` (the Apple tool shipped with the toolchain) or SwiftLint in CI as a blocking step.

## Swift 6 strict concurrency (data-race safety)

The Swift 6 language mode turns data races into compile errors. Do not silence the checker with `@unchecked Sendable`, `nonisolated(unsafe)`, or `@preconcurrency` to make a build pass; each of those is a race the compiler caught and you hid.

- Pin UI state to the main actor. Annotate view models and view-facing types with `@MainActor`. In Swift 6.2, prefer enabling the "Default Actor Isolation = MainActor" build setting (the Approachable Concurrency option) so app-module types are main-actor by default and you annotate the exceptions, not the rule.
- Move work off the main actor explicitly. Background work belongs to an `actor` or a `@concurrent`/`nonisolated` async function, not to a `Task.detached` sprinkled to "fix" a hang. Shared mutable state lives behind an `actor` or a `Mutex` from the `Synchronization` framework, never behind a bare `var` guarded by comments.
- Make values crossing isolation boundaries `Sendable`. Model types should be `struct`/`enum` with `Sendable` members so they pass between actors for free. Use `sending` parameters when you must transfer a non-`Sendable` value and let region-based isolation prove it is safe.

```swift
import Observation

@MainActor
@Observable
final class TransactionsViewModel {
    enum State: Equatable { case idle, loading, loaded([Transaction]), failed(String) }
    enum Intent { case appear, retry }

    private(set) var state: State = .idle
    private let service: TransactionsService   // injected, Sendable

    init(service: TransactionsService) { self.service = service }

    func send(_ intent: Intent) {
        switch intent {
        case .appear, .retry: Task { await load() }
        }
    }

    func load() async {                 // stays on MainActor; service hops off it
        state = .loading
        do { state = .loaded(try await service.fetch()) }   // Transaction is Sendable
        catch { state = .failed(error.localizedDescription) }
    }
}

actor TransactionsService {            // off-main mutable state, race-free by construction
    func fetch() async throws -> [Transaction] { /* URLSession + Codable */ [] }
}
```

## MVVM and unidirectional flow

Data flows one way: the view renders state, sends typed intents, and the view model is the only thing that mutates state. A view never owns business logic, and a view model never imports SwiftUI or touches a `View`.

- The view owns its view model with `@State`; two-way bindings use `@Bindable`. Pass shared models down with the environment, not global singletons.
- State is a single, equatable value (an `enum` or a small `struct`), so the view is a pure function of it and previews/tests can construct any state directly.
- Side effects (network, persistence, navigation requests) are expressed as intents handled in the view model, not started inline in `body`.

```swift
struct TransactionsView: View {
    @State private var model: TransactionsViewModel

    init(service: TransactionsService) {
        _model = State(initialValue: TransactionsViewModel(service: service))
    }

    var body: some View {
        Group {
            switch model.state {
            case .idle, .loading: ProgressView()
            case .loaded(let items): List(items) { Text($0.title) }
            case .failed(let message): RetryView(message: message) { model.send(.retry) }
            }
        }
        .task { model.send(.appear) }
    }
}
```

## UIKit / AppKit interop boundary

Reach for UIKit or AppKit only when SwiftUI cannot express the requirement: a control with no SwiftUI equivalent (`PHPickerViewController`, `MFMailComposeViewController`, advanced `UITextView`/`NSTextView` text systems, `MKMapView` features beyond `Map`), `UIViewControllerRepresentable`-hosted SDK screens, or AppKit-specific macOS chrome.

- Wrap the imperative view in `UIViewRepresentable` / `UIViewControllerRepresentable` (or the AppKit `NSViewRepresentable`) and keep the wrapper thin: it adapts, it does not hold business logic. State still lives in the `@Observable` model.
- Drive the wrapped view from SwiftUI state in `updateUIView`/`updateUIViewController`; push events back through a `Coordinator` or a closure, never by mutating SwiftUI state from inside `makeUIView`.
- Record why the interop exists in the file. A reviewer should be able to see the SwiftUI gap that forced it; "we already had the UIKit code" is not a reason for a new feature.

## Minimum deployment target policy

- Default floor is N-1: support the current shipping major OS and the one before it. In 2026 that is iOS/iPadOS 18 as the minimum while iOS/iPadOS 26 is current (Apple's year-based versioning jumped 18 → 26), which covers well over 90% of active devices. macOS holds the same two-major window (Sequoia / Tahoe-era), and watchOS/tvOS track their paired iOS.
- The floor is a deliberate decision, not a default Xcode leaves at the SDK version. Changing it (raising to use a new API, or lowering for a partner requirement) is recorded in project memory with the adoption-rate or contractual reason.
- Gate newer APIs with `if #available` / `@available` and provide a real fallback down to the floor; do not raise the whole app's minimum to use one convenience API.
- `@Observable` requires iOS 17 / macOS 14 and is satisfied by this floor. If an exceptional target must go below it, fall back to `ObservableObject` rather than abandoning MVVM.

## Strict TDD

Red, green, refactor on every logical change; no production line lands without a test that failed first.

- Use the Swift Testing framework (`import Testing`, `@Test`, `#expect`, `#require`) for new tests; keep XCTest for legacy suites and for `XCUITest` UI flows, which Swift Testing does not yet cover.
- View models are the unit under test: inject a stub/fake service, drive an intent or call the async method, assert the resulting `State`. Because state is one equatable value, assertions are exact.
- Mark async, main-actor suites `@MainActor`; use `await confirmation` for callbacks and `#expect(throws:)` for error paths. Mock every network and persistence dependency so tests are deterministic and offline.

```swift
import Testing
@testable import App

@MainActor @Suite struct TransactionsViewModelTests {
    @Test func loadsTransactionsOnAppear() async {
        let model = TransactionsViewModel(service: .stub(returning: [.sample]))
        await model.load()
        #expect(model.state == .loaded([.sample]))
    }

    @Test func surfacesFailure() async {
        let model = TransactionsViewModel(service: .stub(throwing: URLError(.notConnectedToInternet)))
        await model.load()
        guard case .failed = model.state else { Issue.record("expected .failed"); return }
    }
}
```

## In scope vs out of scope

In scope: native iOS, iPadOS, macOS, watchOS, tvOS (and visionOS where required) apps; SwiftUI/UIKit/AppKit UI; Swift Concurrency; SwiftData/Core Data; `URLSession` client code; XCTest/Swift Testing/XCUITest; Xcode/SwiftPM/`xcodebuild` builds, code signing, provisioning, App Store distribution, and Instruments profiling; Human Interface Guidelines, Dynamic Type, dark mode, and accessibility.

Out of scope: backend services and API design (consume contracts, do not author them); Android (`android` agent); Flutter/Dart (`flutter` agent); web frontends (`frontend` agent); server-side Swift unless explicitly assigned.

## Handoff boundaries

- API and data contracts: consume an agreed schema; surface gaps to the backend owner rather than reshaping the server from the client.
- Authentication: Sign in with Apple, passkeys, and `ASAuthorization`/`AuthenticationServices` flows are coordinated with the `auth_engineer` agent for policy (AAL, token handling); the apple specialist owns the platform integration, Keychain storage, and UI.
- Design: visual tokens, layout, and HIG decisions come from the design source; implement to them and flag platform constraints.
- Release infrastructure: CI pipelines, signing-secret management, and deployment automation are shared with `sre`; the apple specialist owns the project's build settings and `xcodebuild` invocations.

## Common pitfalls

- Building on Swift 5 mode (or `-strict-concurrency=minimal`) so data-race errors never appear: the safety guarantee is gone. Require Swift 6 language mode.
- `@unchecked Sendable` / `nonisolated(unsafe)` added to clear a compiler error: a hidden race, reject and fix the isolation.
- `Task.detached` used to "get off the main thread" for state that should live on an actor: it discards isolation and priority. Use an `actor` or `@concurrent`.
- View model importing SwiftUI or referencing a `View`, or business logic written inline in `body`: that is not MVVM and is untestable.
- Mutating SwiftUI `@State` from inside `makeUIView`/`makeUIViewController`: causes update loops; route events through the `Coordinator`.
- Reaching for UIKit when SwiftUI already has the control, with no recorded reason: interop is an exception, not a habit.
- Minimum deployment target left at the SDK default, silently dropping a still-supported OS, or a single API raising the whole app's floor instead of an `#available` gate.
- Production code committed with no failing-test-first, or tests that hit the real network/persistence and are therefore flaky and order-dependent.
- New tests written in XCTest when Swift Testing fits, or async main-actor tests left un-isolated and racing.

## Definition of done

- [ ] Target builds clean under the Swift 6 language mode with complete concurrency checking; no `@unchecked Sendable` or `nonisolated(unsafe)` added to pass.
- [ ] UI is SwiftUI; any UIKit/AppKit interop is wrapped in a thin `*Representable`, holds no business logic, and records the SwiftUI gap it fills.
- [ ] Feature follows `@Observable` MVVM with unidirectional flow: a single equatable state, typed intents, view models on `@MainActor`, dependencies injected, no SwiftUI import in the model.
- [ ] Off-main work runs on an `actor` or `@concurrent`/`nonisolated` async function; shared mutable state is actor- or `Mutex`-protected; values crossing isolation are `Sendable` or `sending`.
- [ ] Minimum deployment target matches the N-1 policy (iOS 18 floor in 2026) or carries a recorded exception; newer APIs are `#available`-gated with a working fallback.
- [ ] Every logical change has a test written red-first (Swift Testing for new code, XCUITest for UI flows); network and persistence are mocked; tests pass offline and in CI.
- [ ] Lint/format runs as a blocking CI step; accessibility (Dynamic Type, dark mode, VoiceOver labels) is verified.
- [ ] Work outside the apple scope (backend, auth policy, Android/Flutter/web) is handed to the owning agent, and the relevant design decision is persisted to project memory.
