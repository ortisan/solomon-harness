# Flaky Tests

A flaky test passes and fails on the same code without any source change. It is not a nuisance, it is a gate failure: once a suite has a known flaker, every red run becomes ambiguous, engineers learn to re-run until green, and a real regression slips through behind the noise. This skill owns the flaky-test policy: the root-cause taxonomy, how to detect intermittent failures, how to quarantine without silently skipping, and the deflaking workflow that pins determinism and removes the quarantine. It does not own the coverage floor or the gate report; the floor lives in `coverage_a_floor_not_a_finish_line` (wired into branch protection by `ci_quality_gates`) and the report in `qa_report_the_required_output`. The deterministic-test rules a healthy test obeys live in `test_design_rules`; this skill is what you run when a test breaks them.

## Definition and cost

Quantify flakiness before arguing about it. Track the **flip rate** per test: failures on unchanged commits divided by total runs over a rolling window (CI history, or `pytest --last-failed` cross-referenced with git SHA). A test with flip rate above zero on a stable SHA is flaky by definition and gets a tracking issue via `log_issue`.

The cost is compounding. One flaky test at a 2 percent per-run failure rate, in a suite that re-runs on every push, produces a red pipeline several times a day; the team's response is a reflexive re-run, which is exactly the behavior that lets a genuine intermittent regression ship. Google's published data put roughly 1 in 7 of their tests as flaky at some point, and the dominant remediation cost was engineer attention, not compute. The policy below exists to cap that attention cost with an explicit owner and SLA, not to tolerate the flake.

## Root-cause taxonomy

Classify every flaker before fixing it; the fix differs by class, and the class drives the quarantine label so trends are visible.

- **Async/timing waits.** A `sleep(0.5)` race, polling a result before an event fires, or asserting on an order that the event loop does not guarantee. Symptom: fails under load or on a slow runner. Fix: wait on a condition, not a clock (`WebDriverWait` / explicit `await` of the actual future), never a fixed sleep.
- **Test order and shared state.** Tests pass alone, fail in suite, because one mutates module globals, a class attribute, a singleton, or a database row another reads. Surfaced by running in a randomized order (see Detection).
- **Nondeterministic time, random, and data.** Unpinned `datetime.now()`, unseeded `random`/`numpy`, dict/set iteration relying on insertion luck, or DB rows returned without an `ORDER BY`. These are the determinism rules in `test_design_rules`; a violation is the root cause here.
- **External dependencies.** A real network call, a live clock skew, a container that is not ready, a third-party sandbox. The standing rule from `test_design_rules` and the QA mocking duty is that external services are mocked at the boundary; a flaker that calls out is a missed mock, not a quarantine candidate.
- **Resource leaks and bleed.** An unclosed socket, a leaked temp file, a thread or asyncio task that outlives the test, port exhaustion, or fixture teardown that does not run on failure. Symptom: failures cluster late in the run or only after N tests. Fix with deterministic teardown (`yield` fixtures, `addfinalizer`, context managers).

## Detection

Find flakers on purpose; do not wait for them to embarrass a release.

- **Randomize order** with `pytest-randomly`. It shuffles test order and reseeds `random`/`numpy`/`PYTHONHASHSEED` each run, and prints the seed so a failure reproduces:

  ```bash
  pytest -p randomly                       # shuffled order, reseeded each run
  pytest -p randomly --randomly-seed=1234  # reproduce a specific shuffle
  ```

  An order-dependent or seed-dependent test fails here, exposing the shared-state and nondeterminism classes above. Run this in the nightly job (`ci_quality_gates`), not only on the developer's machine.

- **Surface intermittent failures** by re-running passing builds. A scheduled job that runs the suite N times against a pinned SHA and records per-test failure counts is the flaky tracker. `pytest-rerunfailures` reports which tests needed a rerun; `pytest-replay` captures the exact order for reproduction. Feed counts into a dashboard so flip rate is a tracked metric, not folklore. CI-native flaky detection (GitHub Actions test reports, or a service such as BuildPulse / Trunk Flaky Tests) automates the same loop.

## Quarantine policy

Quarantine is containment with a deadline, not a silent skip. A bare `@pytest.mark.skip` deletes the signal and the requirement coverage with it; that is forbidden. The quarantined test still runs, in a non-gating lane, owned and time-boxed.

- Mark with a dedicated `quarantine` marker that the gating run deselects and the nightly job runs and reports:

  ```ini
  # pyproject.toml
  [tool.pytest.ini_options]
  markers = ["quarantine: known-flaky, non-gating, must carry owner + fix-by SLA"]
  ```

  ```bash
  pytest -m "not quarantine"   # the required gate: green is trustworthy again
  pytest -m quarantine         # nightly visibility lane, results tracked not gating
  ```

- Every quarantined test carries an owner and a fix-by SLA in the marker, and a `log_issue` tracking the id. No anonymous, open-ended quarantine.
- A bounded `--reruns` on a narrow, justified set is acceptable as a stopgap only when it is visible and tracked; it must never be the silent default on the whole suite, which is what hides nondeterminism back inside the gate.
- The quarantine lane is non-gating on `feature/*` and nightly, but a flaky test on a `release/*` branch blocks the release until fixed or proven unrelated to the shipped change. The gate wiring for this is owned by `ci_quality_gates`.

## Deflaking workflow

Reproduce, fix the root cause, then remove the quarantine. Worked example: a quarantine block with owner and SLA, then the deterministic fix.

```python
import pytest

# QUARANTINED 2026-06-20 — owner: @qa-jordan — fix-by: 2026-07-04 (ISSUE-318)
# Class: nondeterministic time + unseeded random. Non-gating; runs nightly.
@pytest.mark.quarantine
def test_daily_settlement_window():
    expiry = compute_expiry(random.random())
    assert is_in_settlement_window(datetime.now()) is True
```

1. **Reproduce deterministically.** Pin the failing order and seed from `pytest-randomly` output (`--randomly-seed=1234`), then pin the clock and RNG so the failure is repeatable rather than probabilistic.
2. **Fix the root cause**, not the symptom. The fix below removes the two nondeterminism sources the comment named; the determinism techniques themselves are owned by `test_design_rules`.
3. **Remove the quarantine** only after the test passes a deflake gauntlet: green across many randomized-order, randomly-seeded runs (for example `pytest -p randomly --count=50` with `pytest-repeat`). Close the `log_issue` and drop the marker in the same commit.

```python
from freezegun import freeze_time  # or time-machine for tz/async-heavy suites

@freeze_time("2026-06-27T14:30:00Z")
def test_daily_settlement_window():
    expiry = compute_expiry(seed=1234)            # injected seed, no global random
    assert is_in_settlement_window(NOW) is True   # frozen clock, deterministic
```

Record the resolved root-cause class with `save_memory` so a recurring class (say, async waits in one module) becomes a design fix, not a per-test game of whack-a-mole. Hand the cleared quarantine list to the release owner via `log_handoff`.

## Common pitfalls

- Re-running the whole suite with `--reruns` as the default so every flaker is auto-papered; nondeterminism is now inside the gate and a real intermittent regression rides through.
- `@pytest.mark.skip` used as "quarantine"; the test no longer runs at all and its requirement coverage silently drops, invisible in a green run.
- A quarantine with no owner and no fix-by date; it becomes permanent and the lane fills with dead tests no one reads.
- Fixing the symptom (raising a `sleep`, widening a tolerance) instead of the class (wait on the event, pin the clock); the flake returns on a slower runner.
- Declaring a test deflaked after one green run instead of a many-run randomized gauntlet; the 2-percent flake is still a 2-percent flake.
- Only ever running tests in file order, so order-coupling never surfaces until it breaks a release; `pytest-randomly` was not wired into the nightly job.
- Treating a flaker that makes a real network or live-clock call as flaky rather than as a missing boundary mock (`test_design_rules`).

## Definition of done

- [ ] Every quarantined test carries a `quarantine` marker, an owner, a fix-by SLA, a root-cause class, and a linked `log_issue`; none use a bare `skip`.
- [ ] The gating run executes `-m "not quarantine"` and a nightly lane runs and reports `-m quarantine`; no blanket `--reruns` hides flakiness in the gate.
- [ ] `pytest-randomly` runs in the nightly job and the seed/order of any failure is captured for reproduction.
- [ ] Flip rate per test is tracked over a rolling window, and a flaker on a stable SHA opens a tracking issue.
- [ ] Each deflake reproduces deterministically (pinned seed via `--randomly-seed`, frozen clock via `freezegun`/`time-machine`), fixes the root-cause class, and passes a many-run randomized gauntlet before the marker is removed.
- [ ] The resolved root-cause class is recorded with `save_memory`; a `release/*` candidate hands off a cleared quarantine list via `log_handoff`, with no open flaky blocker.
