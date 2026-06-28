## Clean architecture layout


Organize by feature, then by layer. Enforce the dependency rule: dependencies point inward, domain is the center and knows nothing about Flutter, HTTP, or persistence.

```
lib/
  core/            # shared: errors, typedefs, di, theme, router, l10n
  features/<name>/
    domain/        # entities, repository interfaces, use cases (pure Dart)
    application/   # blocs/cubits/notifiers, view state models
    data/          # models (DTO with from/toJson), data sources, repo impls
    presentation/  # widgets, pages, layout
```

- **Entities** are immutable, framework-free, and hold business rules. **Models/DTOs** live in `data/` and convert to/from entities; never leak `Map<String, dynamic>` past the data layer.
- **Use cases** are single-purpose (`callable` classes, `call()` method). One use case per business action.
- **Dependency injection** with `get_it` + `injectable`, or Riverpod providers. Wire concretes only at the composition root. No `new HttpClient()` inside widgets or blocs.
- **Immutability** via `freezed` for entities, DTOs, events, and states. Use `Equatable` only where you avoid codegen. Hand-written `==`/`hashCode` is a smell.
- **Error handling**: data sources throw narrow exceptions; repositories catch and map to `Failure` subtypes; UI renders failures. Set a global `FlutterError.onError` and `PlatformDispatcher.instance.onError`, and wrap `runApp` in `runZonedGuarded` for crash reporting.
