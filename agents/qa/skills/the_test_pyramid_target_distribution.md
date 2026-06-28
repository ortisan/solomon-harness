# The Test Pyramid Target Distribution

Decide how a suite's mass is split across unit, integration, and end-to-end tests, and detect when that split has gone wrong from data rather than feel. This skill owns the level mix and the diagnosis of a bad shape; it does not design the cases at each level (`test_design_rules` owns that) and does not explain how to write the upper layers (`integration_and_e2e_testing` owns that). The shape gates quality at `/solomon-review` because the mix determines how fast the suite runs on every push, how precisely a failure localizes the defect, and how much flake the gate carries. A suite can hit a high `pytest-cov` number and still be the wrong shape: 600 slow E2E tests give weak failure localization and a 40-minute pipeline, so reviewers stop trusting red and start re-running it.

## Cohn's pyramid and the 70/20/10 heuristic

Mike Cohn's test pyramid (Succeeding with Agile, 2009) orders tests by scope and cost: a wide base of cheap, fast, isolated unit tests, a narrower band of integration tests, and a thin cap of UI/E2E tests. The widely cited ~70% unit / ~20% integration / ~10% E2E split is a budget and a sanity check, not a quota to enforce per module. The point is the gradient: most defects should be caught by the fastest, most precise layer that can see them, and each layer up costs more in runtime and flake while losing failure-localization precision.

Treat the percentages as a band, not a target to hit exactly. A parser-heavy library legitimately sits at 90% unit; a thin API gateway with little logic of its own legitimately carries more integration. What is never legitimate is the base being narrower than the layers above it. Push every assertion down to the lowest level that can make it: if a validation rule can be checked in a unit test, checking it again in an E2E test buys nothing and adds a slow, brittle duplicate (`integration_and_e2e_testing` calls out that redundancy).

## Anti-patterns: ice-cream cone and hourglass

Two broken shapes recur, both named by Alister Scott:

- Ice-cream cone (inverted pyramid): most tests are E2E or manual, few are unit. Every logic change is verified by driving the whole system, so the suite is slow (minutes per test), flaky (network, timing, shared state), and gives a stack trace that points at "checkout failed" instead of the function that broke. CI wall-clock balloons, retries creep in to get green, and the gate loses credibility.
- Hourglass: a fat unit base and a fat E2E cap with almost no integration middle. Units pass because collaborators are mocked, E2E sometimes passes, but the seams the mocks stand in for, the SQL the ORM actually emits, the serializer, the real HTTP contract, are never exercised by a fast test. Integration faults surface only at the expensive E2E layer or in production. The fix is to move seam coverage down into Testcontainers-backed integration tests (`integration_and_e2e_testing`), not to add more E2E.

Both are slow and flaky for the same root reason: work that a millisecond unit test or a few-second integration test should do is being done by a multi-second E2E test that touches a network, a browser, and shared state.

## Google's small/medium/large sizing

"Roughly 70% unit" is subjective until you define the levels objectively. Google's test sizes (Software Engineering at Google, ch. 11) do that by constraining resources, not by counting assertions:

| Size | Process | Network | Filesystem/DB | Time guidance | Sleep/clock |
|------|---------|---------|---------------|---------------|-------------|
| Small (unit) | single process/thread | none (localhost forbidden) | none | < ~100 ms, target ms | not allowed |
| Medium (integration) | multi-process, single machine | localhost only | local container/db allowed | < ~1 s typical, secs | discouraged |
| Large (E2E) | multiple machines | real network allowed | real services | seconds to minutes | last resort |

This makes the level a property you can audit, not a label. A "unit" test that opens a socket or hits Postgres is mis-sized and belongs in the medium band, which is exactly how an hourglass hides: tests labelled unit are quietly doing integration work, or vice versa. Tag each test with its size and let the constraint, no I/O for small, localhost-only for medium, decide the bucket.

## Per-level budgets: speed and determinism

Set hard budgets per level and treat a breach as a defect in the test, not an acceptable cost:

- Unit (small): sub-millisecond to low single-digit milliseconds, zero I/O, no socket, no real clock, no sleep. The whole unit suite runs in seconds and on every save. If a unit test needs the database, the design has a seam in the wrong place; mock the boundary (`mocking_and_isolation_mock_all_external_services`) or move the test to integration.
- Integration (medium): up to ~1 second each, real backing services in containers, state isolated per test by transaction rollback or truncation. The full integration suite stays under a few minutes so it runs on every PR.
- E2E (large): seconds to low minutes, reserved for revenue- or compliance-critical journeys. Determinism is enforced with condition-based waits and a controllable clock, never fixed sleeps (mechanics owned by `integration_and_e2e_testing` and `flaky_tests`).

Budgets are what keep the shape honest over time: a suite drifts toward the ice-cream cone one slow test at a time, and a per-level runtime ceiling in CI is what catches the drift early.

## Detecting an inverted pyramid from data

Do not eyeball the shape; measure it. Mark every test with its level using `pytest` markers, register them in `pyproject.toml` so a typo fails fast, and let CI count and time each band.

```python
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "unit: small, no I/O, sub-ms",
    "integration: medium, localhost/container services",
    "e2e: large, full deployed path",
]
```

```python
@pytest.mark.unit
def test_fee_rounds_half_up():
    assert round_fee(Decimal("1.005")) == Decimal("1.01")

@pytest.mark.integration
def test_order_repo_round_trips(db):  # Testcontainers Postgres fixture
    ...

@pytest.mark.e2e
def test_checkout_journey(page):       # Playwright
    ...
```

Count per marker and sum runtime per band in CI, then compare against the budget:

```bash
pytest -m unit -q | tail -1
pytest --collect-only -q -m unit | wc -l        # count per level
pytest -m e2e --durations=0 -q                  # runtime per test
```

| Shape | Unit (count / total time) | Integration | E2E | Suite wall-clock | Verdict |
|-------|---------------------------|-------------|-----|------------------|---------|
| Healthy | 1,400 / 9 s | 380 / 95 s | 70 / 140 s | ~4 min | Pyramid; fails fast and precisely |
| Inverted (ice-cream cone) | 180 / 6 s | 120 / 70 s | 900 / 32 min | ~34 min | E2E-heavy; slow, flaky, poor localization |
| Hourglass | 1,300 / 8 s | 40 / 12 s | 520 / 19 min | ~20 min | Missing middle; seam faults escape to E2E |

The count tells you the static shape; the runtime tells you the felt cost. The two red rows are diagnosable at a glance: E2E count exceeding integration count is the cone, and integration count collapsing between a fat base and a fat cap is the hourglass. Track these numbers per release in the QA report (`qa_report_the_required_output`) so drift is visible as a trend, and persist the agreed per-level budgets with `save_decision` so the gate is reproducible rather than re-argued each cycle. When mutation testing (`mutation_testing`) reports a cluster of no-coverage mutants, route the missing path to the correct level using this distribution rather than reflexively adding another E2E.

## Common pitfalls

- Reading 70/20/10 as a mandate and adding throwaway unit tests to hit a percentage; the ratio is a diagnostic of where logic lives, not a quota.
- "Unit" tests that open sockets or hit a real database. They are mis-sized medium tests; the mislabel is how an hourglass passes review.
- Re-asserting unit-level logic in E2E "to be safe". Slow, flaky duplication with weak localization; assert it once at the lowest capable layer.
- Filling the integration gap of an hourglass with more E2E tests instead of Testcontainers integration tests; you deepen the slow cap instead of rebuilding the middle.
- Judging shape by `pytest-cov` percentage. Coverage is orthogonal to shape: 95% line coverage delivered by 900 E2E tests is still an ice-cream cone.
- No per-level markers, so the shape cannot be counted and drift is invisible until CI takes 30 minutes.
- Fixed `sleep` in E2E tests to mask timing, which inflates the E2E runtime budget and hides flake (see `flaky_tests`).

## Definition of done

- [ ] Every test carries a level marker (`@pytest.mark.unit` / `integration` / `e2e`) registered in `pyproject.toml`, and the level matches Google small/medium/large resource constraints (no I/O in unit, localhost-only in integration).
- [ ] Per-level budgets are enforced: unit tests are sub-millisecond with zero I/O, integration tests under ~1 s with isolated state, E2E reserved for critical journeys.
- [ ] CI counts tests per marker and sums runtime per band, comparing against the budget, and the breakdown is published in the QA report each cycle.
- [ ] The shape is verified to be a pyramid (base widest, E2E count below integration count) and is neither an ice-cream cone nor an hourglass, judged from the count/runtime table, not from coverage percent.
- [ ] No logic is asserted redundantly across levels; each assertion lives at the lowest capable layer, with upper-layer mechanics deferred to `integration_and_e2e_testing`.
- [ ] The agreed per-level budgets and band thresholds are persisted with `save_decision` so the gate is reproducible across releases.
