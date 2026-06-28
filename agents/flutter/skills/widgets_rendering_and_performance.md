## Widgets, rendering, and performance


Frame budget: **16ms at 60fps, 8ms at 120fps**. Jank means a frame exceeded budget on the UI or raster thread. Profile with DevTools (performance overlay, timeline), always in `--profile` mode on a real device, never in debug.

- Impeller is the default renderer on iOS and Android. Profile shader and animation jank against Impeller, not the legacy Skia path, since first-run shader compilation stalls no longer apply.
- Mark every widget that can be `const` as `const`. Const widgets skip rebuild and reuse element subtrees. Enable `prefer_const_constructors` lint.
- Split large `build` methods into small widgets instead of helper methods that return `Widget`; small widgets rebuild independently and benefit from const.
- Long or infinite lists use `ListView.builder`/`GridView.builder`/`Sliver*`. Never `ListView(children: list.map(...))` for unbounded data. Set `itemExtent`/`prototypeItem` when item height is fixed. Avoid `shrinkWrap: true` on large lists.
- Stable identity in dynamic lists with `ValueKey`/`ObjectKey` so Flutter reuses elements instead of rebuilding.
- Isolate expensive paints behind `RepaintBoundary`. Avoid wrapping large subtrees in `Opacity` (prefer `AnimatedOpacity`/`FadeTransition`) and avoid `saveLayer` (clips, blend modes) on the hot path.
- Move CPU-heavy work (JSON of large payloads, parsing, crypto) off the UI thread with `compute()` or `Isolate.run`.
- Images: use `cached_network_image`, set `cacheWidth`/`cacheHeight` to decode at display size, and `precacheImage` for above-the-fold assets.
- Always dispose `AnimationController`, `TextEditingController`, `ScrollController`, `FocusNode`, and `StreamSubscription` in `dispose()`. Leaks here cause "setState after dispose" crashes.
- Across async gaps, check `if (!mounted) return;` before using `BuildContext`. Enable `use_build_context_synchronously` lint.
