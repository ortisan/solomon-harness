# Architecture Fitness Functions

Encode every structural rule you care about as an automated fitness function that runs in CI and fails the build, so architecture erosion is rejected at the pull request instead of discovered months later in review. A fitness function is any objective check that a candidate change still satisfies an architectural characteristic; the design contracts and NFRs you author (`design_contracts_as_component_boundaries`, `non_functional_requirements`) are only real if something executable enforces them on every commit.

## Taxonomy and where each rule lives

From *Building Evolutionary Architecture* (Ford, Parsons, Kua), classify each function so you pick the right tool and cadence:

- Atomic vs holistic: one characteristic in isolation (no cycles in a package) vs an emergent combination (latency under load while a circuit breaker is open).
- Triggered vs continuous: runs on a deploy/PR (the default for structure) vs runs constantly in production (continuous: monitoring/synthetic checks, owned with `observability`).
- Static vs dynamic: evaluated against source/bytecode (layering, coupling) vs against a running system (performance, security budgets).

Structural rules (layering, dependency direction, cycles, coupling) are atomic, triggered, static; they belong in the test/CI stage and must gate the merge. Treat the rule set itself as a versioned artifact in the repo, not as tribal knowledge.

## Layering and dependency direction

The primary control. Declare allowed dependency directions and forbid everything else; the build fails on a single illegal import.

JVM with ArchUnit (run as ordinary JUnit tests, `consideringAllDependencies` to avoid blind spots):

```java
@AnalyzeClasses(packages = "com.example")
class ArchitectureTest {
  @ArchTest static final ArchRule layers = layeredArchitecture().consideringAllDependencies()
    .layer("Controller").definedBy("..controller..")
    .layer("Service").definedBy("..service..")
    .layer("Repository").definedBy("..repository..")
    .whereLayer("Controller").mayNotBeAccessedByAnyLayer()
    .whereLayer("Service").mayOnlyBeAccessedByLayers("Controller")
    .whereLayer("Repository").mayOnlyBeAccessedByLayers("Service");

  @ArchTest static final ArchRule noCycles =
    slices().matching("com.example.(*)..").should().beFreeOfCycles();
}
```

Python (this project's stack) with `import-linter`, configured in `pyproject.toml`/`.importlinter` and run in CI as `lint-imports`:

```ini
[importlinter]
root_package = solomon_harness

[importlinter:contract:layering]
name = Harness layering, high to low
type = layers
layers =
    solomon_harness.cli
    solomon_harness.mcp_server
    solomon_harness.tools

[importlinter:contract:domain-purity]
name = Domain must not import I/O adapters
type = forbidden
source_modules = solomon_harness.tools.database_client
forbidden_modules = requests, httpx
```

`tach` (Rust-based, fast) is the modern alternative: it pins each module's public interface and allowed dependencies in `tach.toml` and enforces them, which scales better on large monorepos than import-time graphs. JS/TS with `dependency-cruiser`:

```js
module.exports = { forbidden: [
  { name: 'no-circular', severity: 'error', from: {}, to: { circular: true } },
  { name: 'domain-pure', severity: 'error',
    from: { path: '^src/domain' }, to: { path: '^src/(infra|ui)' } },
  { name: 'no-orphans', severity: 'warn', from: { orphan: true }, to: {} },
] };
```

Rule of thumb: dependencies point inward toward the domain (hexagonal/clean architecture), never outward. Every rule needs a one-line rationale recorded as an ADR (`architectural_decision_records`) and persisted with `save_decision`, so the next engineer who hits the failure learns the why, not just the what.

## Coupling and cyclic dependencies

Cycles are the first erosion symptom; forbid them outright (`beFreeOfCycles`, dependency-cruiser `circular: true`, `madge --circular`, `pydeps --show-cycles`). For trend control, track Martin's package metrics and gate on movement, not just absolutes:

- Instability `I = Ce / (Ca + Ce)` (efferent over total coupling), range 0-1. Stable packages (low I) should be the ones depended upon.
- Abstractness `A = abstract types / total types`, range 0-1.
- Distance from the main sequence `D = |A + I - 1|`. Aim for `D` near 0; flag any package with `D > 0.5` (the zones of pain and uselessness).
- Propagation cost (share of components reachable through the dependency DSM): a rising value means change ripples widely. Budget it and fail on regression.

Tooling: `tach`/`pydeps` and `import-linter` for Python, `dependency-cruiser`/`madge` for JS/TS, ArchUnit plus jQAssistant, Sonargraph or Structure101 for the JVM. Prefer a delta gate ("coupling may not increase versus the base branch") over a fixed threshold so a legacy codebase can ratchet down instead of failing on day one.

## Performance and security budgets

These are dynamic fitness functions; derive the numbers from the NFRs and SLOs, do not invent them.

- Web performance: Lighthouse CI with a `budget.json` (LCP <= 2.5s, TBT <= 200ms, total JS <= 200KB gzip) and `size-limit`/`bundlesize` on the bundle; coordinate the UI specifics with `frontend` and `seo`.
- Backend latency/throughput: `k6` thresholds in the pipeline, e.g. `http_req_duration: ['p(95)<200', 'p(99)<500']` and `http_req_failed: ['rate<0.01']`; a breach exits non-zero and fails the stage.
- Security budgets: dependency scanning (`pip-audit`, OSV-Scanner, Trivy) and SAST (Semgrep, CodeQL) wired to fail on, for example, any CVSS >= 7.0 finding or a forbidden license. Threat-model coverage and severity policy are owned by `security`; the architect's job is to make the gate blocking and the threshold explicit.

Hold dynamic gates to a delta or a defined budget with a documented owner, because flaky absolute thresholds train teams to rerun until green, which silently disables the check.

## Wiring into CI and governance

- Make every structural function a required status check on the protected branch; a non-blocking warning is not a fitness function.
- Keep them fast (static checks in seconds) so they run on every PR, not nightly. Slow holistic checks (load tests) run on a separate triggered stage.
- When a violation is a deliberate, time-boxed exception, encode it as a scoped ignore with an expiry and `log_issue` to track the debt, link it to a remediation `create_milestone`; never widen the rule to make red go green.
- Record each rule's rationale with `save_decision`/`get_decision`; when an erosion crosses an agent boundary (a domain leak owned by another specialist), use `log_handoff` so ownership is explicit and `get_latest_activity` shows the trail.

## Common pitfalls

- Fitness functions that only warn or run nightly: erosion lands on main before anyone sees it. Gate the merge.
- A single absolute threshold dropped onto a legacy codebase, so the build is red from commit one and the check gets disabled. Use a base-branch delta ("no worse than before") to ratchet.
- ArchUnit run without `consideringAllDependencies`, missing field/annotation/generic references and passing illegal access.
- `import-linter` `root_package` pointed at the wrong module or contracts never run in CI, so the config exists but enforces nothing.
- Forbidding cycles in the test suite while the metric tools (madge/pydeps) are advisory only; pick one place that fails the build and keep both consistent.
- Performance/security budgets with no owner and no SLO behind them, so numbers are arbitrary and teams rerun until green. Derive from NFRs, assign an owner.
- Treating the rule set as fixed: it must evolve with the architecture and live in version control with an ADR per rule, not in a wiki page no pipeline reads.
- Suppressing a violation with a broad ignore instead of a scoped, expiring exception tracked as an issue.

## Definition of done

- [ ] Layering and dependency-direction rules exist as executable checks (ArchUnit / import-linter or tach / dependency-cruiser) and are a required, blocking CI status on the protected branch.
- [ ] Cyclic dependencies are forbidden and fail the build; no advisory-only cycle detection is the sole guard.
- [ ] Coupling is gated by a base-branch delta or a justified threshold (instability, distance from the main sequence, or propagation cost), so erosion cannot increase silently.
- [ ] Performance and security budgets run as dynamic fitness functions (Lighthouse CI / size-limit / k6 / pip-audit / Semgrep) with thresholds derived from NFRs and SLOs and an explicit owner.
- [ ] Every rule has a one-line rationale captured in an ADR and persisted via `save_decision`; the rule set is version-controlled.
- [ ] Exceptions are scoped, time-boxed, tracked with `log_issue` and a remediation `create_milestone`, never granted by loosening the rule.
- [ ] Cross-boundary erosion is handed off with `log_handoff`, and structural checks complete fast enough to run on every pull request.
