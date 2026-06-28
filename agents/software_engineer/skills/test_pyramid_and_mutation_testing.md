# Test Pyramid and Mutation Testing

Build a test suite shaped like a pyramid from inside the TDD loop: a wide base of fast, isolated, deterministic unit tests, a thinner middle of integration tests against real dependencies or well-chosen fakes, a small top of end-to-end tests, and mutation testing on top of all three to prove the suite actually kills defects instead of merely executing lines. This is the developer how-to for distribution, layer boundaries, and the mutation-score gate; for the broader QA-side strategy cross-reference the qa agent's `the_test_pyramid_target_distribution`, `integration_and_e2e_testing`, and `mutation_testing`, and `tdd_red_green_refactor` for driving each test from a red state.

## The shape, and why

Target roughly 70% unit, 20% integration/component, 10% end-to-end by test count. The ratio is a feedback-speed budget, not dogma: cost and flakiness rise by an order of magnitude per layer up, so you push every assertion to the lowest layer that can hold it.

| Layer | Count | Per-test budget | Runs when | Dependencies |
| --- | --- | --- | --- | --- |
| Unit | ~70% | < 50 ms | every save | none, all in-process |
| Integration/component | ~20% | < 2 s | every push / pre-merge | one real boundary (DB, broker) via Testcontainers |
| End-to-end | ~10% | seconds | pre-merge / nightly | the whole system wired |

The decision behind the shape: a bug caught by a unit test costs you a sub-second loop; the same bug caught at e2e costs minutes plus a flake investigation. An inverted pyramid (the "ice-cream cone", lots of slow e2e, few unit) produces a suite developers stop running locally, so feedback moves to CI and the loop dies.

## Base: fast, isolated, deterministic unit tests

A unit test exercises one behavior of one unit with every collaborator either real-and-pure or substituted by a hand-written fake. No network, no clock, no filesystem, no random, no sleep. With `pytest` 8.4.x the whole unit suite should finish in single-digit seconds so it runs on every save.

```python
# tests/unit/test_position_sizing.py
import pytest
from solomon_harness.risk import position_size

@pytest.mark.parametrize(
    "equity, risk_pct, stop_distance, expected",
    [
        (10_000, 0.01, 5.0, 20.0),   # nominal
        (10_000, 0.01, 0.0, 0.0),    # zero stop -> guard, not div-by-zero
        (0, 0.01, 5.0, 0.0),         # no equity
    ],
)
def test_position_size(equity, risk_pct, stop_distance, expected):
    assert position_size(equity, risk_pct, stop_distance) == expected
```

Determinism is enforced, not hoped for. Inject the clock and randomness through the unit's constructor or arguments so a test pins them; never let production code read `datetime.now()` or `random` directly. Pin nondeterminism with `freezegun` (`@freeze_time("2026-06-28")`) and force order independence with `pytest-randomly` (it reseeds and shuffles every run, so an order-dependent test fails loudly instead of passing by luck). A test that needs `sleep`, a retry timeout, or a "run it again" is not a unit test; fix the seam or move it up a layer. See `flaky_tests` in the qa agent for triage once one slips through.

## Middle: integration and component tests against real boundaries

The middle layer verifies the seams units cannot: SQL that actually runs, a migration that applies, a serializer round-trip, a message consumed off a real broker. Test against a real dependency in a container, not a mock of the driver, because mocks encode your assumptions about the dependency and pass even when those assumptions are wrong. Use `testcontainers` 4.x to spin up the genuine engine and throw it away after.

```python
# tests/integration/test_decision_repository.py
import pytest
from testcontainers.postgres import PostgresContainer
from solomon_harness.repository import DecisionRepository

@pytest.fixture(scope="module")
def pg_url():
    with PostgresContainer("postgres:17-alpine") as pg:
        yield pg.get_connection_url()

def test_round_trips_a_decision(pg_url):
    repo = DecisionRepository(pg_url)
    repo.migrate()
    saved = repo.save(title="cut leverage", rationale="vol spike")
    assert repo.get(saved.id).rationale == "vol spike"
```

Decision rules for this layer: use a container when the behavior under test is the boundary itself (SQL dialect, transactions, real serialization). Use a hand-written fake (an in-memory implementation of your own port) when the boundary is incidental and you only need a collaborator that behaves; this keeps the test fast and the contract explicit. Reach for a mock only at the true outermost edge — a third-party HTTP API you do not own — and even then prefer a contract test against a recorded interaction. The hexagonal seam this exploits is in `hexagonal_architecture_ports_and_adapters`; mocking discipline at the edge is in the qa agent's `mocking_and_isolation_mock_all_external_services`.

## Top: a thin layer of end-to-end tests

E2E proves the wired system does the one thing that matters end to end: the critical path, plus a smoke test per major flow. Keep it to the smallest set that would catch a wiring or config break that every lower test passed. These are the slowest and flakiest tests you own, so they earn their place by covering integration of the whole, not branch coverage of any part. Pin them against an ephemeral environment, retry the harness setup but never the assertion, and quarantine (do not delete) a flaky e2e until it is fixed.

## Mutation testing: prove the suite kills defects

Line and branch coverage tell you a line ran, not that an assertion would fail if that line were wrong. Mutation testing closes the gap: the tool injects small faults (flip `<` to `<=`, swap `+`/`-`, replace a return with `None`, drop a `not`) and reruns your tests. A mutant the tests fail on is *killed*; one that survives is a line your suite executes but does not actually check. Mutation score = killed / (killed + survived); a *timeout* or *no-coverage* mutant is not a kill.

Python with `mutmut` 3.x (the 3.0 rewrite caches per-mutant and parallelizes), configured in `pyproject.toml`:

```toml
[tool.mutmut]
paths_to_mutate = ["src/solomon_harness/"]
tests_dir = ["tests/unit/"]   # mutants must die to FAST tests, or the run takes hours
```

```bash
mutmut run                 # generate, apply, and test mutants
mutmut results             # summary: killed / survived / timeout
mutmut show <id>           # the exact diff that survived -> the missing assertion
mutmut browse              # interactive survivor review
```

Run mutation against the *unit* layer only. Mutmut reruns the suite once per mutant, so a slow or broad suite makes the run cost explode; a tight, deterministic base is what makes mutation testing affordable. JS/TS uses `Stryker` (`@stryker-mutator/core` 9.x) and Java uses `PITest` 1.19.x; the gate logic is identical.

```jsonc
// stryker.config.json
{
  "testRunner": "vitest",
  "mutate": ["src/**/*.ts", "!src/**/*.spec.ts"],
  "incremental": true,                       // only re-test changed files
  "thresholds": { "high": 85, "low": 75, "break": 75 }  // build fails under 75
}
```

```xml
<!-- PITest: fail the build under threshold, mutate only the diff -->
<configuration>
  <mutationThreshold>80</mutationThreshold>
  <targetClasses><param>com.example.risk.*</param></targetClasses>
</configuration>
<!-- mvn org.pitest:pitest-maven:scmMutationCoverage  (changed files only) -->
```

## Gating a pull request on mutation score

Whole-repo mutation is too slow for a per-PR gate and unfair to legacy code. Gate the *diff*: run mutation only on lines the PR changed and require a score on that diff. Practical thresholds — 80% mutation score on changed code as the hard break, with surviving mutants printed in the PR so the author sees the exact unchecked branch. This makes the metric drive a real assertion ("add a test that fails when this `<=` becomes `<`") instead of coverage theater. Keep a slower full-repo mutation run nightly to catch erosion. Treat mutation score as a quality gate that complements, not replaces, the coverage floor in the qa agent's `coverage_a_floor_not_a_finish_line`.

## In the TDD loop

Mutation testing is a refactor-phase check, not a red-green step. Drive the behavior red-green-refactor per `tdd_red_green_refactor`; once green and refactored, run `mutmut run` on the changed module. A survivor means your green was too easy — the production line could be wrong and your test would still pass — so write the assertion that kills it before you open the PR. New code should arrive at review already mutation-clean.

## Common pitfalls

- An inverted pyramid: many slow e2e tests, few unit tests. Developers stop running it locally and feedback collapses to CI. Reject; push assertions down.
- Unit tests that hit network, disk, the wall clock, or `random` without injection. They are slow integration tests in disguise and flake nondeterministically. Reject and demand an injected seam.
- Integration tests that mock the database driver instead of using a real engine via Testcontainers. They pass against assumptions, not reality, and miss dialect and transaction bugs.
- Chasing 100% line coverage while mutation score sits at 50%. The suite executes lines without asserting on them; coverage is green and defects ship.
- Running mutation against the full suite including integration/e2e. Runtime explodes to hours and the gate gets disabled. Mutate against the fast unit layer only.
- Gating PR mutation on the whole repo rather than the diff. Slow, noisy with legacy survivors, and the team mutes it.
- Equivalent mutants (a change that cannot alter behavior) counted as failures. Mark them ignored with justification; do not write a meaningless test to "kill" them.
- A retried or `sleep`-padded assertion to make a test pass. That hides a real race; fix the seam or quarantine, never retry the assertion.

## Definition of done

- [ ] Test count is roughly 70% unit / 20% integration / 10% e2e; new behavior is covered at the lowest layer that can hold the assertion.
- [ ] The unit suite is fully isolated (no network/disk/clock/random), deterministic under `pytest-randomly`, and runs in single-digit seconds.
- [ ] Nondeterminism (time, randomness) is injected through seams and pinned in tests (`freezegun`), never read directly by production code.
- [ ] Integration tests run against a real boundary via `testcontainers`, or a hand-written in-memory fake of an owned port; mocks are confined to third-party edges.
- [ ] E2E is limited to critical-path smoke flows; flaky e2e is quarantined, not deleted, and assertions are never retried.
- [ ] Mutation testing (`mutmut` / Stryker / PITest) runs on the changed unit code; survivors are reviewed and either killed with a new assertion or marked equivalent with justification.
- [ ] The PR gate enforces >= 80% mutation score on the diff and prints surviving mutants; a nightly full-repo run guards against erosion.
- [ ] Every new behavior reached green from an observed red and is mutation-clean before review, per `tdd_red_green_refactor`.
