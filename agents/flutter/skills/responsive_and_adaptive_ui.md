# Responsive and Adaptive UI

This skill governs how Flutter layouts respond to size, platform, and user settings: breakpoint policy, `LayoutBuilder`/`MediaQuery` discipline, platform-adaptive widgets, text scaling, safe areas, and foldables. The stance: layout derives from constraints and user preferences at runtime — a hardcoded pixel constant or a locked text scale is a defect, and "looks fine on my phone" is not a verification.

## Breakpoints

Adopt the Material 3 window size classes and name them in one place (`core/layout/breakpoints.dart`), not as magic numbers per screen:

- compact: width < 600 dp — single pane, bottom navigation;
- medium: 600–839 dp — single pane with more margin, navigation rail;
- expanded: 840–1199 dp — two panes (list-detail), rail or drawer;
- large/extra-large: >= 1200 dp — two panes plus persistent secondary content.

Branch on the class, not on `Platform.isX`: an iPad, a desktop window, and a landscape foldable all hit `expanded` and should get the same layout. Structure screens so panes are separate widgets composed per class (`ListDetailLayout(compact: ..., expanded: ...)`) rather than `if` statements scattered through one giant build method.

## LayoutBuilder and MediaQuery discipline

Two different questions, two different tools:

- `MediaQuery` answers "what is the window and the user's environment": `MediaQuery.sizeOf(context)` for window size, `.textScalerOf` for font scaling, `.paddingOf` for notches and system bars, `.viewInsetsOf` for the keyboard. Use the scoped `sizeOf`/`paddingOf` accessors, not `MediaQuery.of(context).size` — the scoped variants rebuild only when that specific value changes, `of` rebuilds on every metrics change including keyboard animation frames.
- `LayoutBuilder` answers "what space did my parent give me". A reusable card that switches from row to column belongs on `LayoutBuilder` constraints, because inside a two-pane layout the window size lies about available width.

Decide top-level page layout from window size class; decide component-internal layout from local constraints. Scale content with `Flexible`/`Expanded`/`Wrap`/`FittedBox`/`AspectRatio`; reserve `flutter_screenutil`-style global scaling for tightly speced design handoffs, and never combine it with breakpoint logic.

## Adaptive widgets per platform

Adapt behavior where platform conventions genuinely differ, and do it through the theme or `.adaptive` constructors, not `if (Platform.isIOS)` in build methods: `Switch.adaptive`, `CircularProgressIndicator.adaptive`, `showAdaptiveDialog`, and scroll physics from the theme (iOS bounce vs Android clamp). `Theme.of(context).platform` is the correct switch — it is overridable in tests and golden tests, unlike `dart:io` `Platform`. Keep the adaptation list short and deliberate (dialogs, switches, back-swipe, date pickers); wholesale Cupertino-vs-Material forks double the UI surface for marginal fidelity.

## Text scaling, safe areas, insets

- Honor `MediaQuery.textScalerOf(context)`; never wrap the app in a fixed `TextScaler.linear(1.0)`. Every screen must survive 200% font scaling without overflow errors — that means no fixed-height containers around text, `maxLines` + `overflow` chosen consciously, and scrollable fallbacks on dense forms. Verify at 200% in a golden or widget test, not by eyeball.
- Wrap page scaffolding in `SafeArea` (or consume `MediaQuery.paddingOf`) so notches, punch-holes, and home indicators never cover content. For edge-to-edge Android (default since SDK 35 targets), draw backgrounds behind system bars but keep interactive content inside the safe area.
- Keyboard: `viewInsetsOf` reports it; use `Scaffold.resizeToAvoidBottomInset` plus scrollable form bodies so the focused field is never hidden.
- Tap targets at least 48x48 dp (Material) / 44x44 pt (iOS). Provide `Semantics` labels for icon-only controls; verify contrast and traversal order with the accessibility inspector.
- No hardcoded user-facing strings: `flutter_localizations` + `intl` with ARB files, referenced through `AppLocalizations`. Localization interacts with responsiveness — German strings are ~30% longer, so test the compact layout in the longest locale.

## Foldables and desktop windows

Treat hinges with `MediaQuery.displayFeatures`: a `DisplayFeature` of type hinge/fold reports bounds you must not straddle with interactive content. `TwoPane`-style layouts split panes along the hinge; dialogs should be positioned onto one screen half. Foldables also change size class at runtime (folded compact -> unfolded expanded), so layouts must rebuild cleanly on metrics change without losing state — keep pane state in the application layer, not in the pane widget, so switching from one-pane to two-pane preserves selection. The same rule covers desktop and web window resizing, which is continuous rather than event-like.

## Common pitfalls

- Magic-number breakpoints duplicated per screen instead of one named window-size-class module; screens drift apart at the same width.
- `MediaQuery.of(context).size` in hot builds — rebuilds the subtree on every keyboard frame; use `sizeOf`/`paddingOf`/`textScalerOf`.
- Using window size inside a reusable component instead of `LayoutBuilder`; the component breaks the first time it is placed in a pane.
- Locking text scale (`TextScaler.linear(1)`) to "fix" overflow instead of fixing the layout; fails accessibility review.
- `Platform.isIOS` branching in build methods; untestable and wrong on iPad-as-expanded layouts — use `Theme.of(context).platform` and size classes.
- Content straddling the hinge on foldables, or selection state stored in a pane widget so unfolding resets it.
- Fixed-height text containers that clip at 130%+ font scale; RenderFlex overflow stripes in production screenshots.
- Layouts verified only on one emulator; no compact/expanded/200%-scale test evidence.

## Definition of done

- [ ] Breakpoints are the Material window size classes, defined once and imported; no per-screen magic widths.
- [ ] Page-level layout branches on window size class; component-level layout uses `LayoutBuilder` constraints.
- [ ] Only scoped `MediaQuery` accessors (`sizeOf`, `paddingOf`, `viewInsetsOf`, `textScalerOf`) appear in build methods.
- [ ] Platform adaptation goes through `.adaptive` constructors / `Theme.of(context).platform`; no `dart:io` platform checks in widgets.
- [ ] Every screen survives 200% text scale without overflow, verified by a widget or golden test with `textScaler` overridden.
- [ ] `SafeArea`/padding handling covers notches, edge-to-edge system bars, and keyboard insets; focused fields stay visible.
- [ ] Tap targets meet 48dp/44pt; icon-only controls have `Semantics` labels; traversal order checked.
- [ ] All user-facing strings come from ARB-backed `AppLocalizations`; compact layout checked in the longest supported locale.
- [ ] Foldable hinge (`displayFeatures`) and runtime size-class changes handled; pane/selection state survives fold-unfold and window resize.
