---
name: widgets-rendering-and-performance
description: Governs Flutter build-method hygiene, list virtualization, RepaintBoundary isolation, Impeller rendering behavior, and frame-budget measurement via DevTools on a profile-mode device. Use when optimizing a slow widget tree, virtualizing a list, isolating repaints, or verifying a performance claim against a DevTools timeline.
---

# Widgets, Rendering, and Performance

This skill governs build-method hygiene, list virtualization, repaint isolation, Impeller-era rendering behavior, and how performance is measured. The stance: the frame budget is 16.7 ms at 60 Hz and 8.3 ms at 120 Hz across both the UI and raster threads; a claim that "it feels faster" without a DevTools timeline from a profile build on a real device is not evidence.

## Build-method hygiene

`build` runs constantly; it must be cheap and pure.

- Mark every constructible-at-compile-time widget `const`. Const widgets are canonicalized, skip rebuild, and let the framework short-circuit identical subtrees. Enforce with `prefer_const_constructors` and `prefer_const_literals_to_create_immutables` — this is a lint gate, not a habit.
- Extract subtrees into small `StatelessWidget` classes, not `Widget _buildHeader()` helper methods. A helper method re-executes on every parent rebuild and can never be const; a widget class gets its own element, rebuilds independently, and shows up named in DevTools. This is the single highest-value refactor on slow screens.
- No allocation-heavy or blocking work in `build`: no JSON decoding, no `DateFormat` construction per item (hoist formatters), no network calls, no sorting a thousand-row list inline — precompute in the application layer.
- Give dynamic list children stable identity with `ValueKey`/`ObjectKey` so reorder and insert reuse elements instead of rebuilding and losing state.
- Across async gaps, guard `if (!mounted) return;` before touching `context`; keep `use_build_context_synchronously` enabled. Dispose every `AnimationController`, `TextEditingController`, `ScrollController`, `FocusNode`, and `StreamSubscription` in `dispose()` — leaks here surface as "setState after dispose" crashes and steadily rising memory.

## Lists and slivers

Unbounded or long content is always virtualized: `ListView.builder`/`separated`, `GridView.builder`, or explicit `Sliver*` in a `CustomScrollView`. `ListView(children: items.map(...).toList())` instantiates everything eagerly and is a reject for unbounded data. Set `itemExtent` or `prototypeItem` when rows are fixed-height — layout cost drops and scrollbar math becomes exact. `shrinkWrap: true` on a large list defeats virtualization (it lays out all children to measure itself); restructure with slivers instead. For images in lists use `cached_network_image`, decode at display size with `cacheWidth`/`cacheHeight` (a 4000 px photo decoded into a 120 px tile wastes memory and raster time), and `precacheImage` above-the-fold assets.

## Repaint isolation and raster cost

- Wrap frequently repainting islands (animations, progress indicators, charts redrawing per tick) in `RepaintBoundary` so their dirty region does not force the whole screen to re-rasterize. Verify with the "Highlight repaints" toggle in DevTools rather than sprinkling boundaries speculatively — each boundary costs a layer and memory.
- Avoid `Opacity` around large or animating subtrees; it forces `saveLayer`. Prefer `FadeTransition`/`AnimatedOpacity` (which animate without rebuilds) or draw the color with alpha directly.
- `saveLayer` triggers — `Opacity`, some blend modes, `ShaderMask`, antialiased clips like `ClipRRect` over changing content — are the classic raster-thread killers; keep them off the scroll and animation hot paths.
- Prefer `AnimatedBuilder`/`ListenableBuilder` with a prebuilt `child:` so the static subtree is constructed once and only the animated wrapper rebuilds per tick.

## Impeller notes

Impeller is the default renderer on iOS and on Android (Vulkan-first, GL fallback on older devices) in current Flutter 3.3x releases. Consequences: precompiled shaders remove Skia's first-run shader-compilation jank, so SkSL warm-up files and `--purge-persistent-cache` rituals are obsolete — do not carry them into new projects. What still costs: `saveLayer`, giant blur sigmas (`ImageFilter.blur` on full-screen backdrops), and very wide antialiased clips. Profile on both a Vulkan device and a GL-fallback device (Android 7–9 era) because their cost profiles differ; if a screen regresses only on Impeller, isolate it with `flutter run --no-enable-impeller` to confirm attribution, then file it against the specific op rather than disabling Impeller in release.

## Measuring: DevTools and jank thresholds

- Profile only in `--profile` mode on a physical device. Debug builds run unoptimized with assertions and are meaningless; emulators lie about GPU characteristics.
- In DevTools Performance: red bars in the frame chart are over-budget frames. Attribute each to UI thread (your Dart: builds, layout) or raster thread (paint cost: shaders, layers). "Track widget builds" names the offending rebuilds; the enhanced tracing flags (`trace-widget-builds`, layout, paint) localize the phase.
- Thresholds to enforce, not admire: frame build + raster <= 16.7 ms at 60 Hz (8.3 ms at 120 Hz — most current flagships); scrolling a core list produces zero janky frames over a 30-second capture; navigation transitions stay under budget. `SchedulerBinding.addTimingsCallback`/`FrameTiming` feeds the same numbers to production telemetry so regressions are caught after release, and `flutter drive --profile` with a timeline summary (`average_frame_build_time_millis`, `worst_frame_rasterizer_time_millis`, jank counts) turns the budget into a CI check.
- CPU-heavy work (parsing multi-hundred-KB JSON, crypto, image manipulation) moves off the UI isolate via `Isolate.run` (or `compute`); above roughly a few milliseconds of pure computation, isolate spawn cost pays for itself.

## Common pitfalls

- `Widget _buildFoo()` helper methods instead of extracted widget classes; the whole screen rebuilds as one opaque unit and const is impossible.
- Missing `const` on obviously constant subtrees because the lints are off.
- `ListView(children: ...)` or `shrinkWrap: true` on unbounded data; eager layout of the entire list.
- `Opacity`/`ShaderMask`/heavy blur wrapped around animating subtrees — `saveLayer` on every frame, raster-thread jank.
- `RepaintBoundary` sprinkled everywhere "for performance" without checking repaint highlighting; layers cost memory and can slow things down.
- Full-resolution image decode into thumbnails (no `cacheWidth`/`cacheHeight`).
- Profiling in debug mode or on an emulator, then reporting conclusions.
- Carrying SkSL shader-warm-up steps into Impeller-default projects.
- Undisposed controllers and subscriptions; missing `mounted` checks after awaits.
- Doing JSON parsing on the UI isolate and blaming the list view for the jank.

## Definition of done

- [ ] Const lints (`prefer_const_constructors`, `prefer_const_literals_to_create_immutables`) enabled and clean; shared subtrees extracted as widget classes, not helper methods.
- [ ] No blocking or allocation-heavy work in `build`; formatters and derived data hoisted; heavy computation on `Isolate.run`.
- [ ] All unbounded lists virtualized with builder/sliver variants; `itemExtent`/`prototypeItem` set for fixed-height rows; no `shrinkWrap` on large lists; dynamic children keyed.
- [ ] Images decoded at display size and cached; above-the-fold assets precached.
- [ ] Repaint isolation verified with the repaint-highlight overlay; no `saveLayer` trigger on scroll/animation hot paths.
- [ ] Profile-mode capture from a physical device shows zero over-budget frames on the flow's core scroll and transitions (16.7 ms at 60 Hz, 8.3 ms at 120 Hz).
- [ ] A `flutter drive --profile` timeline (or `FrameTiming` telemetry) guards the budget in CI or production monitoring.
- [ ] Every controller, focus node, and subscription is disposed; `use_build_context_synchronously` clean.
