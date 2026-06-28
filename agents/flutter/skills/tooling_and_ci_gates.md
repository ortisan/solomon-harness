## Tooling and CI gates


- `flutter analyze` clean with a strict ruleset (`flutter_lints` minimum, `very_good_analysis` preferred). Treat warnings as errors in CI.
- `dart format --set-exit-if-changed .` enforced.
- Sound null safety throughout; avoid the `!` bang operator. Use `?.`, `??`, pattern matching, and exhaustive `switch` on sealed types.
- CI must run: `dart format` check, `flutter analyze`, `flutter test --coverage`, and a coverage threshold check. Block merge on any failure.
