---
name: angular-standards
description: Governs Angular components, services, and templates: Angular 20+ baseline, standalone-only components, signals as the primary reactive primitive, mandatory OnPush or zoneless detection, and RxJS reserved for event-stream problems. Use when writing or reviewing Angular components, services, or templates.
---

# Angular Standards

This skill governs every Angular component, service, and template shipped in this workspace. The stance: Angular 20+ is the baseline, standalone components are the only component style, signals are the primary reactive primitive, `OnPush` (or zoneless) change detection is mandatory, and RxJS is reserved for genuinely event-stream-shaped problems at the edges.

## Standalone components, no NgModules

- Standalone is the default since Angular 19; do not write `standalone: true`, and do not create NgModules for new features. Existing NgModules are migration targets, not templates to copy.
- Application wiring lives in `app.config.ts` with provider functions: `provideRouter(routes, withComponentInputBinding())`, `provideHttpClient(withFetch())`, `provideZonelessChangeDetection()`.
- Routes lazy-load with `loadComponent`/`loadChildren` pointing at standalone components; guards and interceptors are plain functions using `inject()`, not class-based services.

## Signals-first state

- `signal()` for local state, `computed()` for every derived value, `linkedSignal()` (v19+) for state that resets when a source changes, `effect()` only for side effects that leave the graph (DOM, logging, storage). An `effect()` that writes another signal is a design smell: model it as `computed` or `linkedSignal` instead.
- Component I/O uses the signal APIs: `input()`, `input.required<T>()`, `output()`, `model()` for two-way binding. Decorator `@Input()`/`@Output()` only when touching legacy code.
- Async data: prefer `resource()`/`httpResource()` (introduced v19, still maturing through v20/21) or `toSignal(obs$, { initialValue })` over manual `subscribe`. When RxJS is unavoidable, teardown is non-negotiable: `takeUntilDestroyed()` or the `async` pipe. A bare `subscribe` without teardown is a defect.

```ts
@Component({
  selector: 'app-velocity',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @for (row of visible(); track row.id) {
      <app-row [row]="row" />
    } @empty {
      <p>No data for {{ range() }}.</p>
    }
  `,
})
export class VelocityComponent {
  private readonly api = inject(VelocityApi);
  readonly range = input.required<string>();
  readonly rows = toSignal(this.api.rows$(), { initialValue: [] });
  readonly visible = computed(() =>
    this.rows().filter((r) => r.range === this.range()),
  );
}
```

## Template control flow

- Built-in control flow only: `@if`, `@for`, `@switch`. The structural directives `*ngIf`/`*ngFor`/`*ngSwitch` are deprecated as of Angular 20; migrate with `ng generate @angular/core:control-flow`.
- Every `@for` declares `track` on a stable domain ID. `track $index` on a reorderable list re-creates DOM on every mutation; treat it as a review rejection. Use `@empty` for the zero-row case.
- `@defer` for below-the-fold or heavy components: `@defer (on viewport)` with a `@placeholder` sized to the final content, `prefetch on idle` for likely-needed blocks.
- Templates stay thin: no method calls in bindings (they run on every change detection); signal reads are the memoized replacement, so precompute in `computed()` or fields.

## Change detection: OnPush and zoneless

- `ChangeDetectionStrategy.OnPush` on every component, including ones that look trivially cheap; the exceptions are none.
- Zoneless change detection (`provideZonelessChangeDetection()`) is stable in Angular 21 and the default for new applications; on v20 it is developer preview under the `provideExperimentalZonelessChangeDetection` name in earlier minors. Adopting it removes `zone.js` from polyfills (roughly 15 KB gzipped and a class of patched-API overhead) but requires that all view updates flow through signals, the `async` pipe, or explicit `markForCheck()`. The pattern that breaks: mutating a plain class field inside `setTimeout` and expecting the view to notice.
- Keep the same discipline under Zone.js so the codebase is zoneless-ready: if a component only updates via signals and `async`, flipping the provider is a no-op.

## Dependency injection with inject()

- `inject(Service)` in field initializers over constructor parameters: cleaner inheritance, works in functional guards/interceptors/resolvers, and composes into reusable functions.
- `inject()` is only valid in an injection context (field initializer, constructor body, factory, or `runInInjectionContext`); calling it inside a callback or an event handler throws `NG0203`. Capture what you need at construction time, including `DestroyRef` for teardown.

## Typed reactive forms

- Reactive forms with full generic types: `FormGroup<{ email: FormControl<string> }>` or `NonNullableFormBuilder`, which defaults controls to non-nullable and keeps `reset()` from injecting `null` into your model.
- No untyped `FormGroup`/`FormControl` (they type values as `any`), no template-driven forms beyond trivial single-field cases. Validators declared with the control; cross-field validators on the group.
- Signal Forms are experimental in Angular 21; evaluate in spikes, do not ship them until stable.

## Common pitfalls

- Manual `subscribe` without `takeUntilDestroyed()` or `async` pipe: memory leak and post-destroy writes.
- `effect()` used to derive state (writing signals): infinite loops and hidden data flow; use `computed`.
- `track $index` or missing `track` on `@for` over mutable lists: DOM churn and lost input state.
- Default change detection left on a new component, hiding cost until zoneless migration.
- `inject()` called outside an injection context (`NG0203`) inside callbacks or handlers.
- Untyped forms leaking `any` through `form.value` into typed services.
- New NgModules, decorator I/O, or `*ngIf` in new code when the modern equivalents are the project standard.

## Definition of done

- [ ] Standalone component with `OnPush`; wiring via provider functions; route lazy-loaded.
- [ ] State modeled with `signal`/`computed`/`linkedSignal`; `effect()` only for true side effects; I/O via `input()`/`output()`/`model()`.
- [ ] No manual subscription without teardown; async data through `resource`/`httpResource`, `toSignal`, or the `async` pipe.
- [ ] Templates use `@if`/`@for` (`track` on a stable ID, `@empty` handled) and `@defer` for heavy or below-the-fold content; no method calls in bindings.
- [ ] Component updates flow through signals or `async` so zoneless (`provideZonelessChangeDetection`) works without patching.
- [ ] DI uses `inject()` in valid injection contexts; guards and interceptors are functional.
- [ ] Forms are typed reactive forms (`NonNullableFormBuilder`); no `any` reaches consumers.
- [ ] Tests written first and passing: TestBed or Testing Library for Angular asserting rendered output, emitted outputs, and form validity, not private members.
