---
name: clean-architecture-layout
description: Governs feature-first foldering, the presentation/application/domain/data layer split, repository contracts, DTO-to-entity mapping, and mechanical enforcement of the inward dependency rule in a Flutter codebase. Use when structuring a new feature, defining a repository interface, or reviewing whether an import violates the domain/data/presentation boundary.
---

# Clean Architecture Layout

This skill governs how a Flutter codebase is foldered and layered: feature-first organization, the presentation/application/domain/data split inside each feature, repository contracts, DTO-to-entity mapping, and mechanical enforcement of the dependency rule. The stance: dependencies point inward, `domain/` is pure Dart that knows nothing about Flutter, HTTP, or persistence, and any import that violates that direction is a defect, not a style choice.

## Feature-first foldering

Organize by feature first, layer second. Layer-first trees (`lib/blocs/`, `lib/models/`, `lib/screens/`) scatter one feature across the whole repo and make deletion and ownership impossible. The canonical layout:

```
lib/
  core/                  # shared kernel: errors, typedefs, DI wiring, theme,
                         # router, l10n, extensions
  features/<name>/
    domain/              # entities, value objects, repository interfaces,
                         # use cases -- pure Dart, zero flutter/ imports
    application/         # notifiers/blocs, view-state models, mappers to UI state
    data/                # DTOs (from/toJson), remote + local data sources,
                         # repository implementations
    presentation/        # pages, widgets, layout -- no direct data/ imports
  main_development.dart  # one entrypoint per flavor
  main_production.dart
```

A feature is a user-facing capability (checkout, onboarding, portfolio), not a screen. If two features need the same code, promote it to `core/` deliberately; do not import sideways between features. Cross-feature imports are the first symptom of a missing shared module or a wrongly drawn boundary.

## The layers and the dependency rule

- `domain/` holds entities (immutable, `freezed`, business rules only), repository interfaces, and use cases. A use case is a single-purpose callable class — one class, one `call()` method, one business action (`GetPortfolio`, `SubmitOrder`). Domain imports nothing but `meta`, `freezed_annotation`, and other domain code. If `import 'package:flutter/...'` appears here, the layer is broken.
- `application/` orchestrates: Riverpod notifiers or blocs depend on use cases (or directly on repository interfaces in small features — a use-case class that only forwards one repository call is ceremony, skip it), transform entities into view state, and own async lifecycle. No `dio`, no `shared_preferences`, no widget code.
- `data/` implements the repository interfaces. Data sources talk to the wire and disk; repository implementations catch narrow data-source exceptions and map them to domain `Failure` types. Nothing above `data/` sees a `DioException` or a `Map<String, dynamic>`.
- `presentation/` renders application-layer state and dispatches intents. Widgets never construct repositories or clients.

## Repository contracts

The repository interface is the design contract between domain and data, so make failure explicit in its type. Two accepted shapes: return a sealed `Result<T, Failure>` (Dart 3 sealed class or `fpdart`'s `Either`) or throw a sealed `Failure` hierarchy that the application layer switches on exhaustively. Pick one per project and record it in an ADR; mixing both forces callers to defend against two error channels.

```dart
abstract interface class PortfolioRepository {
  Future<Result<Portfolio, PortfolioFailure>> fetch({required String accountId});
  Stream<Portfolio> watch({required String accountId});
}

sealed class PortfolioFailure {
  const PortfolioFailure();
}
final class PortfolioNotFound extends PortfolioFailure { const PortfolioNotFound(); }
final class PortfolioNetwork extends PortfolioFailure { const PortfolioNetwork(); }
```

Sealed failures plus Dart 3 exhaustive `switch` mean the compiler flags the unhandled error branch when someone adds a new failure case.

## DTO versus entity

DTOs mirror the wire format and live in `data/`; entities model the business and live in `domain/`. Never merge them: the first backend rename that ripples into fifty widgets is the cost of skipping the mapping. DTOs carry `fromJson`/`toJson` (via `json_serializable` or `freezed`) plus a `toEntity()` mapper; entities never carry JSON code. Tolerate nullable, loosely typed fields on the DTO and normalize at the mapping boundary — defaults, enum fallbacks, date parsing — so entities can require non-null, valid state.

```dart
@freezed
abstract class QuoteDto with _$QuoteDto {
  const QuoteDto._();
  const factory QuoteDto({required String symbol, double? last}) = _QuoteDto;
  factory QuoteDto.fromJson(Map<String, dynamic> json) => _$QuoteDtoFromJson(json);

  Quote toEntity() => Quote(symbol: symbol, last: last ?? 0);
}
```

## Enforcing the rule mechanically

Convention decays; enforce with tooling. Wire concretes only at the composition root — `ProviderScope` overrides for Riverpod, or `get_it` + `injectable` registered in one `configureDependencies()` — never `Dio()` inside a widget or notifier. Then make violations fail CI:

- A `custom_lint` rule (or an import-boundary linter) rejecting `package:flutter/` imports under `domain/` and `data/` imports under `presentation/`.
- A cheap grep gate works until then: `grep -r "package:flutter" lib/features/*/domain/ && exit 1`.
- Unit tests for `domain/` run under plain `dart test` with no Flutter binding; if they need `TestWidgetsFlutterBinding`, the layer leaked.

Set global error capture once at the composition root: `FlutterError.onError` and `PlatformDispatcher.instance.onError` forward to crash reporting, and `runApp` runs inside `runZonedGuarded` so uncaught async errors are captured too.

## Common pitfalls

- Entities with `fromJson` constructors — the wire format has invaded the domain; every backend change now touches business rules.
- `Map<String, dynamic>` passed above the data layer; typed mapping at the boundary is the whole point of the DTO.
- One giant `UserService` doing fetch, cache, validation, and formatting instead of single-purpose use cases; it becomes untestable and unmergeable.
- Feature A importing `features/b/data/...` directly — sideways coupling that dodges both contracts and DI.
- Hand-written `==`/`hashCode` on entities instead of `freezed` or `Equatable`; drift between fields and equality causes silent state-comparison bugs.
- Repository implementations that rethrow `DioException` upward, forcing presentation code to know about HTTP.
- Service-locator lookups (`getIt<Foo>()`) sprinkled inside widget builds instead of constructor injection from the composition root.

## Definition of done

- [ ] New code lives under `lib/features/<name>/` with the domain/application/data/presentation split; shared code promoted to `core/` deliberately, no sideways feature imports.
- [ ] `domain/` compiles with zero Flutter imports and its tests run under plain `dart test`.
- [ ] Every repository is an interface in `domain/` with its implementation in `data/`; failure typing (sealed `Failure` or `Result`) matches the project ADR.
- [ ] DTOs live in `data/` with `fromJson`/`toJson` and explicit `toEntity()` mapping; no JSON code on entities, no `Map<String, dynamic>` above the data layer.
- [ ] Entities, DTOs, and view states are immutable via `freezed` (or `Equatable` where codegen is deliberately avoided); no hand-written `==`/`hashCode`.
- [ ] Concretes wired only at the composition root; no client or repository construction inside widgets, notifiers, or blocs.
- [ ] An import-direction gate (custom lint or grep check) runs in CI and fails on dependency-rule violations.
- [ ] `FlutterError.onError`, `PlatformDispatcher.instance.onError`, and `runZonedGuarded` are set at startup and forward to crash reporting.
