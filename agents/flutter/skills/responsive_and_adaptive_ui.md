## Responsive and adaptive UI


- Drive layout from `LayoutBuilder` and `MediaQuery` (size, `textScaler`, `padding`, `viewInsets`), not hardcoded pixel constants. Define breakpoints (for example compact <600, medium 600–840, expanded >840 logical px) and branch layout on them.
- Use `Flexible`/`Expanded`/`Wrap`/`FittedBox` and `AspectRatio` to scale; reserve `flutter_screenutil` for tightly speced designs. Wrap screens in `SafeArea`.
- Honor `MediaQuery.textScaler`; never lock text scale. Layout must survive 200% font scaling without overflow.
- Tap targets at least **48x48 dp (Material)** / **44x44 pt (iOS)**. Provide `Semantics` labels for icon-only controls; verify contrast and screen-reader order.
- Adapt platform conventions with `Theme.of(context).platform` or `.adaptive` constructors (switches, dialogs, scroll physics) when targeting both iOS and Android.
- No hardcoded user-facing strings. Use `flutter_localizations` + `intl` with ARB files; reference `AppLocalizations`.
