# Testing Strategy

Default to the Swift Testing framework for new unit and logic tests, keep XCTest only where the platform still requires it (UI automation, performance, and the few APIs Swift Testing does not yet cover), and treat every test as fast, isolated, and deterministic by injecting collaborators behind protocols rather than reaching for the network, the clock, or shared singletons. Build the suite as a pyramid: many Swift Testing unit tests, a thinner band of integration tests, and a small set of XCUITest end-to-end flows, all running headless on simulators in CI with coverage gated.

## Swift Testing vs XCTest: when to use which

Swift Testing (bundled since Xcode 16 / Swift 6, mature in Xcode 26) is the target for unit and integration tests. It runs tests in parallel by default, even within a single suite, and uses value-type `struct` suites that are re-instantiated per test, so cross-test state leakage is structurally hard. XCTest serializes tests within a class and shares the `XCTestCase` instance across the `setUp`/`tearDown` lifecycle, which invites hidden coupling.

Use Swift Testing for: domain logic, view models, networking/parsing, actors, anything you can express as `import Testing`. Keep XCTest for: XCUITest UI flows (`XCUIApplication` has no Swift Testing equivalent), `measure {}` performance tests, and `XCTMetric`-based memory/CPU baselines. The two coexist in the same target and the same `xcodebuild test` run; do not rewrite a working XCTest UI suite just to change frameworks.

```swift
import Testing
@testable import Banking

@Suite("Money formatting")
struct MoneyFormatterTests {
    let formatter = MoneyFormatter(locale: Locale(identifier: "en_US"))

    @Test func formatsWholeAmount() {
        #expect(formatter.string(for: Money(cents: 4200)) == "$42.00")
    }

    @Test func roundsHalfUp() throws {
        let result = try #require(formatter.string(for: Money(cents: 4205)))
        #expect(result == "$42.05")
    }
}
```

`#expect` records a failure and continues; `#require` throws and aborts the test when a precondition that later lines depend on fails (the equivalent of `XCTUnwrap` plus an early return). Use `#require` to unwrap optionals and to stop before a guaranteed crash; use `#expect` for the actual assertions. `#expect` captures the sub-expression values on failure, so `#expect(a == b)` already prints both sides; you rarely need a message.

## Traits, tags, and conditional execution

Traits configure tests declaratively instead of with imperative skip logic.

- `@Test("human readable name")` sets the display name.
- `.disabled("reason")` skips with a recorded rationale; prefer it over commenting a test out.
- `.enabled(if: condition)` runs only when a runtime predicate holds (feature flag, OS version).
- `.bug("JIRA-123", "title")` links a failing test to a tracker.
- `.timeLimit(.minutes(1))` fails a test that hangs instead of stalling the whole run.
- `.tags(_:)` groups tests across suites so you can filter (`swift test --filter` or the IDE) by tag, for example a `.slow` or `.integration` tag.
- `.serialized` on a `@Suite` opts that suite out of parallelism when tests share an external resource.

```swift
extension Tag { @Tag static var integration: Self }

@Suite("Sync engine", .tags(.integration), .serialized)
struct SyncEngineTests {
    @Test(.enabled(if: ProcessInfo.processInfo.environment["RUN_DB"] != nil))
    func writesThenReads() async throws { /* ... */ }
}
```

## Parameterized tests

Swift Testing replaces copy-pasted XCTest variants with one parameterized `@Test`. Each argument runs as a separately reported case, so a single bad input does not hide the rest, and the failing argument appears in the result.

```swift
@Test(arguments: [
    (input: "", expected: ValidationError.empty),
    (input: "ab", expected: ValidationError.tooShort),
    (input: "  ", expected: ValidationError.empty),
])
func rejectsInvalidUsernames(input: String, expected: ValidationError) {
    #expect(throws: expected) { try Username(validating: input) }
}

@Test(arguments: zip(["1", "2", "3"], [1, 2, 3]))
func parsesDigits(_ text: String, _ value: Int) {
    #expect(Int(text) == value)
}
```

Prefer `zip` over two separate `arguments:` collections when inputs and expectations are positionally paired; passing two collections produces the Cartesian product (every combination), which is usually not what you want and explodes the case count.

## Async and concurrency testing

Swift Testing is `async`-native: mark the test `async` and `await` directly, no expectation/`waitForExpectations` ceremony. Test actors and `@MainActor` types by annotating the test or suite with the matching actor isolation.

```swift
@Test func loadsProfile() async throws {
    let client = APIClient(transport: StubTransport(json: profileJSON))
    let profile = try await client.profile(id: "u_1")
    #expect(profile.handle == "ada")
}
```

For code that emits over time, use `confirmation` to assert a callback or event fires an exact number of times within the test scope; it is the Swift Testing analogue of `XCTestExpectation` and fails if the count is wrong.

```swift
@Test func emitsOneValuePerTick() async {
    await confirmation("tick fired", expectedCount: 3) { ticked in
        let clock = TestClock()
        let ticker = Ticker(clock: clock) { ticked() }
        ticker.start()
        await clock.advance(by: .seconds(3))
    }
}
```

Never `Task.sleep` or `sleep()` against wall-clock time to "wait for" async work; it makes tests slow and flaky. Inject a `Clock` (the `swift-clocks` `TestClock`, or a custom protocol) and advance it deterministically. Annotate UI-bound view-model tests with `@MainActor` so assertions observe published state on the same actor that mutated it.

## Protocol-based mocking and dependency injection

There is no runtime mocking framework on Apple platforms (no Mockito-style proxies for value types), and that is by design. Define a protocol at every external boundary, inject a conforming type, and supply a hand-written stub/spy in tests. This keeps tests fast and the production type swappable.

```swift
protocol PaymentGateway: Sendable {
    func charge(_ cents: Int, token: String) async throws -> Receipt
}

struct SpyGateway: PaymentGateway {
    let result: Result<Receipt, Error>
    let recorded = Recorder()              // an actor or locked box for thread-safe capture
    func charge(_ cents: Int, token: String) async throws -> Receipt {
        await recorded.append((cents, token))
        return try result.get()
    }
}

@Test func declinesAreSurfaced() async {
    let vm = CheckoutModel(gateway: SpyGateway(result: .failure(GatewayError.declined)))
    await vm.pay(cents: 999, token: "tok_x")
    #expect(vm.state == .failed(.declined))
}
```

Make spies `Sendable` and store captured calls in an `actor` or a lock-protected box, because Swift Testing runs tests in parallel and a mutable `var calls: [Call]` on a non-isolated struct is a data race the compiler will flag under strict concurrency. For larger dependency graphs, consider `swift-dependencies` (Point-Free, 1.x) which gives a single `@Dependency` injection point and a `withDependencies { } operation:` override scope per test; otherwise plain initializer injection is enough and has zero dependencies.

## SwiftUI and snapshot tests

For SwiftUI view *logic*, test the `@Observable` view model directly rather than the view; views should be thin. When you must assert rendered structure, `ViewInspector` (1.x) lets you traverse the view tree in a unit test without a simulator UI.

For visual regressions, use `swift-snapshot-testing` (Point-Free, 1.18+). It renders a view or controller to a reference image/text on first run and diffs on later runs. Pin the environment so snapshots are stable across machines: fixed device trait (`.iPhone13`), fixed scale, and a fixed locale; otherwise CI produces false diffs against locally-recorded references.

```swift
import SnapshotTesting

func test_emptyCart_layout() {
    let view = CartView(model: .empty)
    assertSnapshot(of: view, as: .image(layout: .device(config: .iPhone13)),
                   record: false)
}
```

Rules: commit reference images, review them in PRs like code, and never leave `record: true` (or the `SNAPSHOT_TESTING_RECORD` env) on in CI, which silently overwrites references and makes the test always pass. Re-record deliberately when the design changes, in a separate, reviewable commit. Keep snapshot tests to meaningful states (empty, error, populated, long-text/Dynamic Type XXXL), not every screen, because images are heavy and brittle.

## XCUITest for end-to-end UI flows

XCUITest drives the real app through the accessibility tree. Keep this layer thin (sign-in, checkout, a core navigation path) because it is the slowest and flakiest tier. Make it robust:

- Query by accessibility identifier, never by visible label: `app.buttons["checkout.payButton"]`. Labels change with copy and localization; identifiers are stable and invisible to users. Set them with `.accessibilityIdentifier(_:)` in SwiftUI.
- Launch with `app.launchArguments`/`launchEnvironment` flags that put the app in a deterministic state (seeded data, mocked network, skipped onboarding). Do not hit production services from a UI test.
- Always `waitForExistence(timeout:)` before interacting; never assume an element is present. Use a 5-10s timeout for normal transitions.
- Page Object pattern: wrap each screen in a struct exposing intent methods (`signIn.enter(email:password:)`) so selectors live in one place and tests read as flows.

```swift
final class CheckoutUITests: XCTestCase {
    func test_guestCheckout_succeeds() {
        let app = XCUIApplication()
        app.launchEnvironment = ["UITEST_SEED": "guest_cart"]
        app.launch()

        let pay = app.buttons["checkout.payButton"]
        XCTAssertTrue(pay.waitForExistence(timeout: 10))
        pay.tap()
        XCTAssertTrue(app.staticTexts["checkout.successBanner"].waitForExistence(timeout: 10))
    }
}
```

## Code coverage

Enable coverage in the scheme (Test action, "Gather coverage for") or `xcodebuild test -enableCodeCoverage YES`. Extract numbers from the `.xcresult` with `xcrun xccov view --report --json Result.xcresult` and gate in CI. Target 70-80% line coverage on app modules and push higher (85%+) on pure domain/business-logic modules where coverage is cheap and meaningful; do not chase 100%, which forces tests for trivial getters and view boilerplate.

Coverage is a floor, not a goal: a line executed by a test with no assertion still counts as covered. Review that critical paths (money, auth, persistence) have *assertions*, not just execution. Exclude generated code and UI scaffolding from the denominator so the number reflects logic you actually own. Fail the build when coverage drops below the threshold rather than only reporting it, so regressions are blocked at the PR.

## Running tests on simulators in CI

Run headless with `xcodebuild` against a pinned simulator. Pin the OS and device so a CI image update does not silently change the platform under test.

```bash
xcodebuild test \
  -scheme Banking \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.5' \
  -resultBundlePath Result.xcresult \
  -enableCodeCoverage YES \
  -parallel-testing-enabled YES \
  -test-timeouts-enabled YES \
  | xcbeautify
```

- Pipe through `xcbeautify` (the maintained successor to `xcpretty`) for readable logs; keep the raw `.xcresult` as the source of truth and the CI artifact.
- Boot the simulator deterministically (`xcrun simctl boot`, `xcrun simctl shutdown`) and erase between runs (`xcrun simctl erase`) when residual state causes flakiness.
- Shard large suites across runners with `-only-testing:`/`-skip-testing:` or by tag, and enable `-parallel-testing-enabled YES` so independent test classes run on parallel simulator clones.
- Quarantine, do not delete, a flaky test: tag it and exclude it from the blocking job while it is fixed, so the signal stays green and the flake stays visible. `fastlane scan` wraps the same `xcodebuild` invocation with retry and JUnit output if your CI needs that format.
- For pure Swift packages with no UIKit dependency, `swift test --parallel --enable-code-coverage` is faster than `xcodebuild` and runs on Linux CI too; reserve `xcodebuild` for targets that need a simulator.

## Common pitfalls

- A test that calls the real network, filesystem, or `Date()`/`UUID()` directly: it is slow, order-dependent, and flaky. Inject the dependency behind a protocol and a clock.
- Sharing mutable state between Swift Testing tests via a `static var` or singleton; parallel execution turns this into a race and intermittent failures. Use per-test `struct` suite instances.
- A spy that stores recorded calls in a non-`Sendable` mutable property; under strict concurrency this is a data race. Capture via an `actor` or a lock.
- `Task.sleep`/`sleep()` used to wait for async work instead of a `TestClock` or `confirmation`; it slows the suite and still races.
- Passing two collections to `@Test(arguments:)` expecting paired inputs and getting the Cartesian product; use `zip` for pairing.
- XCUITest elements queried by visible label or with no `waitForExistence`; both break on copy changes, localization, and timing.
- Snapshot tests left in record mode, or with floating device/locale/scale, so they either always pass or always diff.
- Coverage treated as the goal: high percentage from executed-but-unasserted lines. Gate the number but review assertions on critical paths.
- Rewriting a working XCTest UI suite into Swift Testing for its own sake; XCUITest still belongs in XCTest.
- Unpinned `-destination` (no `OS=`) so the test platform changes when the CI image updates.

## Definition of done

- [ ] New unit/logic tests are written in Swift Testing (`@Test`, `#expect`/`#require`); XCTest is used only for XCUITest, performance, and APIs Swift Testing lacks.
- [ ] Every external boundary (network, persistence, gateways, clock) is injected behind a `Sendable` protocol; tests use hand-written stubs/spies, no live services.
- [ ] Async tests use `async`/`await` and `confirmation`/`TestClock`; no wall-clock `sleep`. Spies capture calls race-free.
- [ ] Repeated cases are parameterized with `@Test(arguments:)` (paired inputs via `zip`); flaky/slow/integration tests carry traits and tags for filtering.
- [ ] UI flows query by accessibility identifier, launch into a seeded/mocked deterministic state, and `waitForExistence` before every interaction, behind Page Objects.
- [ ] Snapshot tests pin device, scale, and locale, commit reference images, and never run with record mode enabled in CI.
- [ ] Coverage is gathered, gated at the agreed threshold (70-80% app, 85%+ domain), and the build fails on regression; critical paths verified to assert, not just execute.
- [ ] CI runs `xcodebuild test` (or `swift test` for pure packages) on a pinned simulator OS/device, in parallel, piping through `xcbeautify`, with the `.xcresult` archived as an artifact.
