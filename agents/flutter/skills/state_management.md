## State management


Pick one primary approach per app and stay consistent. Bloc/Cubit, Riverpod, or Provider are all acceptable per the role; below are the rules that keep each correct.

- **Bloc/Cubit (`flutter_bloc`)**: events and states immutable (freezed). Use `Cubit` for simple imperative state, `Bloc` for event-driven flows with traceable transitions. Emit only inside event handlers; never emit after `close()`. Guard async with `emit.isDone`/`isClosed`. Persist with `hydrated_bloc` when needed. Test with `bloc_test` asserting the exact emitted sequence.
- **Riverpod (2.x/3.x)**: prefer code generation (`@riverpod`). Model async state as `AsyncValue` and render its `loading`/`error`/`data` branches explicitly. Use `ref.watch` to react, `ref.read` for one-off actions in callbacks, `ref.listen` for side effects. Code-gen providers auto-dispose by default; reach for `keepAlive` only deliberately, and use a `family`/provider parameters for parameterized providers. Never call `ref.read`/`watch` outside `build` or provider bodies.
- **Provider**: expose immutable models, rebuild selectively with `Selector`/`context.select`, and dispose `ChangeNotifier`s.
- **Rebuild discipline (all approaches)**: subscribe to the narrowest slice. Use `BlocSelector`, `context.select`, or `select` providers so a widget rebuilds only when its data changes. `setState` is acceptable only for local, ephemeral widget state (e.g. a toggle, a controller); promote anything shared into the application layer.
