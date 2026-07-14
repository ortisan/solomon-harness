---
name: performance-and-instruments
description: Governs Instruments-based profiling of CPU, memory, launch time, and scroll hitches, SwiftUI view-body cost, launch-time budgets, retain-cycle diagnosis, and production MetricKit monitoring on Apple platforms. Use when investigating a slow launch, main-thread hang, scroll jank, or memory leak, or when validating a performance claim before merge.
---

# Performance and Instruments

Profile against measured budgets, not intuition: every claim about CPU, memory, launch time, or scrolling smoothness must come from an Instruments trace or a MetricKit field payload, not a guess. The targets are concrete — sub-400 ms time to first frame, a hitch time ratio under 5 ms/s, zero abandoned memory in Cycles & Roots, and a main thread that never blocks past 250 ms — and this skill governs how to reach and hold them on Xcode 26 / Swift 6.2 against iOS/iPadOS 26 and macOS 26.

## Instruments templates and what each measures

Launch with Product > Profile (Cmd+I) on a Release build; debug builds carry assertion and ARC overhead that distort timings. Pick the template by the question:

- **Time Profiler** — samples every thread's call stack at 1 ms intervals to find where CPU time goes. Invert the call tree and "Hide system libraries" to surface your hottest frames. On A17 Pro / M-series hardware use **CPU Counters** or the **Processor Trace** instrument (Xcode 16+) for cycle-accurate, non-sampled stacks when the hot path is too short for 1 ms sampling to catch.
- **Allocations** — every heap allocation, split into transient (freed) and persistent (live). Use the generation feature: tap "Mark Generation" before and after a repeatable action (push a screen, pop it); a generation that keeps growing across identical cycles is a leak or an unbounded cache.
- **Leaks** — flags memory unreachable from any root. It catches classic leaks but misses retain cycles whose nodes still reference each other; for those use the **Cycles & Roots** view or Xcode's Debug Memory Graph.
- **SwiftUI** — view body evaluation count and duration, plus Core Animation commits. The lane to watch is "Long View Body" and the "Cause" track that names the `@State`/`@Observable` change that triggered the update.
- **Hangs** and **Animation Hitches** — main-thread stalls and frames that miss their display deadline, both reconstructed from `os_signpost` render-loop events.

## Time Profiler, Allocations, and Leaks workflow

Run Time Profiler against the real device and a real interaction, never the Simulator (it uses the Mac's CPU and memory characteristics and will lie about both). Read the inverted tree bottom-up: a leaf that is 30% of weight with your code two frames up is the target. Common findings are synchronous JSON decoding, image decoding, or layout on the main thread.

For memory, drive Allocations with a repeating navigation loop and watch the persistent byte count return to baseline. When it does not, switch to Leaks plus the memory graph. From the command line during a debug session the same data is available with `leaks <pid>`, `heap <pid>`, and `malloc_history <pid> <address>`; enable Malloc Stack Logging in the scheme's Diagnostics tab first so `malloc_history` can resolve allocation backtraces.

## SwiftUI instrument and view-body cost

A `body` must be cheap and pure: it can be called many times per frame, so any work beyond describing the view belongs in the model or a cached property. The SwiftUI instrument's "Long View Body" lane flags bodies that exceed the frame budget. To find why a view re-renders, drop in the debug-only call:

```swift
var body: some View {
    let _ = Self._printChanges()   // logs which property invalidated this view; remove before commit
    RowContent(item: item)
}
```

Prefer `@Observable` (the Observation framework, iOS 17+) over `ObservableObject`: it tracks property reads per view, so a view that reads only `model.title` does not re-render when `model.count` changes, which `@Published` cannot do. Keep expensive derived values out of `body`, give subtrees stable identity, and apply `Equatable` to a heavy custom view (`EquatableView`/`.equatable()`) so SwiftUI can skip diffing it when inputs are unchanged.

## Hangs and hitches: the render loop budget

Two distinct failures, two distinct fixes.

A **hang** is the main thread blocked so the app stops responding to touch. Apple's responsiveness budget is ~100 ms to feel instantaneous; Instruments and MetricKit flag any unresponsiveness past **250 ms** as a hang. The fix is always to move blocking work (disk, network, decode, heavy compute) off the main actor:

```swift
// Bad: decode + parse on the main actor blocks the run loop.
let model = try JSONDecoder().decode(Feed.self, from: data)

// Good: hop off, return a Sendable value, update UI back on the main actor.
let model = try await Task.detached(priority: .userInitiated) {
    try JSONDecoder().decode(Feed.self, from: data)
}.value
```

Enable the **Thread Performance Checker** (scheme > Diagnostics) during development; it reports hangs, priority inversions, and excessive disk writes as runtime issues without a trace.

A **hitch** is a frame delivered to the display late. The deadline is the refresh interval: **16.67 ms at 60 Hz, 8.33 ms at 120 Hz ProMotion**. Measure with the hitch time ratio (milliseconds hitched per second of animation): under 5 ms/s is good, 5–10 ms/s needs attention, above 10 ms/s is visible jank. Hitches split into commit hitches (your main-thread layout/`body` overran) and render hitches (the render server overran, usually offscreen passes, shadows, or blends). Reduce offscreen rendering, give shadows an explicit `shadowPath`/`.drawingGroup()`, and avoid per-frame layout invalidation.

Wrap the suspect interval in a signpost so it shows up on the Instruments timeline:

```swift
let signposter = OSSignposter(subsystem: "com.example.app", category: .pointsOfInterest)
let state = signposter.beginInterval("ScrollLoad")
defer { signposter.endInterval("ScrollLoad", state) }
```

## Launch time and MetricKit in production

Cold launch should reach the first frame in **under 400 ms**; the system watchdog kills a launch that exceeds **20 s** (`0x8badf00d`). Profile with the **App Launch** template, which separates pre-main (dyld, static initializers, `+load`) from post-main work. Cut pre-main time by avoiding heavy work in initializers and `application(_:didFinishLaunchingWithOptions:)`; defer non-critical setup until after the first frame.

Lab traces only describe your devices. Field data comes from **MetricKit** (`MXMetricManager`), which delivers an aggregated `MXMetricPayload` roughly daily and `MXDiagnosticPayload` for crashes, hangs, CPU exceptions, and disk-write exceptions. Register one subscriber at launch and forward payloads to your backend:

```swift
final class MetricsObserver: NSObject, MXMetricManagerSubscriber {
    override init() { super.init(); MXMetricManager.shared.add(self) }

    func didReceive(_ payloads: [MXMetricPayload]) {
        for p in payloads {
            _ = p.applicationLaunchMetrics?.histogrammedTimeToFirstDraw
            _ = p.applicationResponsivenessMetrics?.histogrammedApplicationHangTime
            _ = p.animationMetrics?.scrollHitchTimeRatio
            upload(p.jsonRepresentation())
        }
    }

    func didReceive(_ payloads: [MXDiagnosticPayload]) {
        // MXHangDiagnostic / MXCrashDiagnostic / MXCPUExceptionDiagnostic carry symbolicated call trees.
        for d in payloads { upload(d.jsonRepresentation()) }
    }
}
```

Track p90 of time-to-first-draw, hang time, and scroll hitch ratio as release gates; a regression in any of them should block the rollout.

## Retain cycles and capture lists

Closures capture `self` strongly by default. A cycle forms when `self` owns the closure and the closure captures `self` — Combine subscriptions stored in `self`, long-lived `Task`s held by `self`, and stored callbacks are the usual culprits.

```swift
final class FeedViewModel {
    private var cancellables = Set<AnyCancellable>()
    private var streamTask: Task<Void, Never>?

    func start() {
        service.updates
            .receive(on: DispatchQueue.main)
            .sink { [weak self] value in           // without [weak self] this retains the VM forever
                guard let self else { return }
                apply(value)
            }
            .store(in: &cancellables)

        streamTask = Task { [weak self] in          // a stored, long-running task needs weak self
            for await event in service.eventStream {
                guard let self else { return }
                await handle(event)
            }
        }
    }

    deinit { streamTask?.cancel() }
}
```

Rules that hold up in review:

- Use `[weak self]` in any escaping closure that `self` (transitively) retains, then `guard let self else { return }`. A short-lived one-shot `Task` that captures `self` is fine because it releases on completion; an infinite-stream `Task` stored on `self` is not.
- Delegate and parent back-references are `weak var delegate`. Closure-based `Timer`/`CADisplayLink` retain their target — invalidate them in `deinit` or use `[weak self]`.
- Confirm with the Debug Memory Graph (the icon in the debug bar): purple "!" badges mark leaks, and the inspector shows the exact reference chain keeping an object alive. Add `deinit` logging during development to prove view models actually deallocate when a screen is dismissed.

## List and image performance

Render only what is on screen and decode images at display size.

`List` and `LazyVStack`/`LazyHStack` instantiate rows lazily and reuse them; a plain `VStack`/`HStack` inside a `ScrollView` builds every row eagerly and will stall on large data sets.

```swift
List(items) { item in RowView(item: item) }        // lazy + reuse, preferred for large data
// or, when you need custom scroll behavior:
ScrollView { LazyVStack(spacing: 0) { ForEach(items) { RowView(item: $0) } } }
```

Give every row stable identity via `Identifiable` with a real model id; never key `ForEach` by array index, which forces full rebuilds on insertion or reorder. Avoid `.id(...)` on rows unless you intend to discard and rebuild them.

Images dominate scroll cost because full-resolution decode happens on the main thread. Downsample to the target point size before display rather than handing a 4000×3000 photo to a 120-point thumbnail:

```swift
func downsample(_ url: URL, to pointSize: CGSize, scale: CGFloat) -> UIImage? {
    let src = CGImageSourceCreateWithURL(url as CFURL,
        [kCGImageSourceShouldCache: false] as CFDictionary)
    guard let src else { return nil }
    let opts = [
        kCGImageSourceCreateThumbnailFromImageAlways: true,
        kCGImageSourceShouldCacheImmediately: true,        // decode now, off the main thread
        kCGImageSourceCreateThumbnailWithTransform: true,
        kCGImageSourceThumbnailMaxPixelSize: max(pointSize.width, pointSize.height) * scale,
    ] as CFDictionary
    guard let cg = CGImageSourceCreateThumbnailAtIndex(src, 0, opts) else { return nil }
    return UIImage(cgImage: cg)
}
```

`AsyncImage` is convenient but does no caching or downsampling, so it re-fetches and full-decodes on every reappearance — for lists, back rows with a downsampling cache (a custom loader or a maintained library such as Nuke 12+). Decode off the main actor, cache by a key that includes the target size, and pin row heights with `.frame` to avoid layout thrash during scroll.

## Common pitfalls

- Profiling a Debug build or the Simulator: ARC/assertion overhead and host-CPU characteristics make every number wrong. Always Release, always device.
- Calling a leak "fixed" because Leaks is clean while a retain cycle survives in Cycles & Roots — the two instruments catch different failures.
- `body` doing real work (sorting, formatting, decoding); it is called repeatedly per frame and belongs in the model.
- `[weak self]` sprinkled on every closure, including non-escaping ones and one-shot tasks, hiding intent and sometimes dropping work that should have run. Use it only where `self` retains the closure.
- Blocking the main actor on `JSONDecoder`, file I/O, or image decode, then blaming SwiftUI for the resulting >250 ms hang.
- `VStack`/`HStack` with hundreds of children inside a `ScrollView` instead of `LazyVStack` or `List`, building every row up front.
- `ForEach` keyed by index, causing wholesale rebuilds and broken animations on data mutation.
- Loading full-resolution images into small cells with `AsyncImage` and no cache, producing scroll hitches and memory spikes.
- Shipping with no MetricKit subscriber, so production launch, hang, and hitch regressions are invisible until reviews drop.

## Definition of done

- [ ] Performance claims are backed by an Instruments trace or a MetricKit field payload, captured on a Release build on a real device.
- [ ] Cold launch reaches first frame under 400 ms in the App Launch trace; no synchronous heavy work runs in initializers or `didFinishLaunching`.
- [ ] No main-thread block exceeds 250 ms (Thread Performance Checker and the Hangs instrument clean); blocking work runs off the main actor.
- [ ] Scroll/animation hitch time ratio is under 5 ms/s on the target refresh rate, verified with the Animation Hitches instrument.
- [ ] Debug Memory Graph and Cycles & Roots show no leaked view models or retained cycles; `deinit` fires when screens are dismissed.
- [ ] Large collections use `List`/`LazyVStack` with stable `Identifiable` ids, not eager stacks or index keys.
- [ ] Images are downsampled to display size and decoded off the main thread with a size-keyed cache; raw `AsyncImage` is not used for list cells.
- [ ] A MetricKit subscriber is registered at launch, forwarding `MXMetricPayload` and `MXDiagnosticPayload` to the backend, with launch time, hang time, and hitch ratio tracked as release gates.
