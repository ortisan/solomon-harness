## Common pitfalls


- Calling `setState`/emitting after dispose or `close()`. Guard with `mounted`/`isClosed`.
- Using `BuildContext` after an `await` without a `mounted` check.
- Forgetting to dispose controllers and subscriptions (memory leaks, ghost callbacks).
- `pumpAndSettle` on an infinite animation (test timeout).
- Rebuilding whole pages because a top-level `Bloc`/provider was watched broadly; select narrow slices instead.
- `ListView` over unbounded data instead of `.builder`; `shrinkWrap: true` on large lists.
- Business logic inside widgets; HTTP/JSON leaking out of the data layer.
- Hardcoded sizes and strings; ignoring text scale and `SafeArea`.
- Hand-rolled `==`/`hashCode` causing stale UI; use `freezed`/`Equatable`.
