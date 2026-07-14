---
name: coverage-a-floor-not-a-finish-line
description: Governs code coverage as a merge floor rather than proof of correctness, covering line versus branch versus path coverage, coverage.py/pytest-cov configuration, and diff coverage on PRs. Use when setting a coverage threshold, configuring cov-branch/fail-under, or judging a green coverage number.
---

# Coverage: a Floor, Not a Finish Line

Code coverage measures which lines and branches a test run executed; it is a cheap, fast signal that tells you where the suite has never set foot, and nothing more. Treat it as a floor the `/solomon-review` gate enforces so untested code cannot merge, never as evidence the code is correct. This skill owns coverage measurement and the coverage gate: the `coverage.py`/`pytest-cov` configuration, the line-vs-branch distinction, diff coverage on PRs, and where the floor sits. It deliberately stops at the limit of what execution can prove. Whether the executed code is actually checked is assertion quality, owned by `mutation_testing`; whether the gate is wired into branch protection is owned by `ci_quality_gates`.

## Line vs branch vs path coverage

Three metrics, increasing strength:

- Line (statement) coverage: was this line executed at least once. The weakest metric. A line inside an `if` counts as covered the moment the `if` is taken once, even though the `else` was never run.
- Branch (decision) coverage: was each edge out of each decision taken, both the true and the false exit of every conditional. This is the meaningful floor because most defects hide in the untaken branch: the unhandled `None`, the early return, the error path. A suite at 100% line and 70% branch has whole decision outcomes nobody ran.
- Path coverage: was every combination of branches through a function exercised. Complete but combinatorially explosive (N independent conditionals give 2^N paths), so it is impractical as a global gate. Approximate it only on the highest-risk functions using the design techniques in `test_design_rules`; do not try to gate the repo on it.

Gate on branch coverage. `coverage.py` reports it under "partial" branches in `term-missing`, naming the line and the missed jump target (`12->15`), which points straight at the untaken outcome.

## Configuring `coverage.py` / `pytest-cov`

Pin the configuration in `pyproject.toml` so the floor is versioned config, not a CLI flag a developer can drop. The `--cov-branch` switch (or `branch = true`) is mandatory; without it you are gating on the weakest metric.

```toml
[tool.pytest.ini_options]
addopts = "--cov=src --cov-branch --cov-report=term-missing --cov-report=xml"

[tool.coverage.run]
branch = true
source = ["src"]
omit = ["*/__main__.py", "*/migrations/*"]   # entrypoints and generated DDL, not logic

[tool.coverage.report]
fail_under = 80          # project floor; the gate exits non-zero below this
show_missing = true
skip_covered = false     # keep fully-covered files visible so a drop is obvious
precision = 1
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "\\.\\.\\.",           # typing.Protocol / stub bodies
    "raise AssertionError",
]
```

Rules that keep the number honest:

- `fail_under` is the gate. CI runs `pytest` (which picks up `addopts`) and the non-zero exit blocks the merge. The 80% project floor and 90%+ on core, risk, and money-handling modules match `ci_quality_gates`; enforce the higher per-package floor with a separate `coverage report --include="src/risk/*" --fail-under=90` step rather than averaging it into the global number, where weak core coverage hides behind well-tested utilities.
- `exclude_lines` removes lines that cannot meaningfully be tested (type-checking blocks, abstract stubs, defensive `NotImplementedError`). It narrows the denominator honestly; it does not hide real logic.
- `# pragma: no cover` is the per-line escape hatch and must carry a one-line reason and survive review. It is legitimate on a genuinely unreachable defensive branch or a platform-specific block; it is abuse when used to step over a hard-to-test conditional. Grep the diff for new pragmas in review the way you would grep for `# type: ignore`.

## High coverage is not good tests

Coverage answers "did this line run", never "did a test check what it did". A test with no assertion still marks every line it touches as covered:

```python
def withdraw(balance: int, amount: int) -> int:
    if amount > balance:          # line 2
        raise InsufficientFunds()  # line 3
    return balance - amount        # line 4

def test_withdraw():
    withdraw(100, 30)   # 100% line coverage of the happy path, ZERO assertions
```

Line 4 is covered and the test is green, but it asserts nothing: change `balance - amount` to `balance + amount` and the test still passes. Coverage cannot detect a missing `assert`, a wrong expected value, or a swallowed exception. This is the metric's hard ceiling, and the reason coverage is a floor and not a finish line. The signal coverage structurally cannot give you, whether the executed code is actually pinned by a check, comes from mutation testing: a surviving mutant is a located, missing assertion. See `mutation_testing` for the score, tooling, and ratchet; do not re-derive it from a coverage number.

## Branch a line-only suite misses

The same function shows why line coverage alone is a false floor. A single happy-path test reports 100% line coverage:

```python
def fee(amount: int, premium: bool) -> int:
    base = 0
    if premium:            # branch: premium True / False
        base = 5
    return amount + base

def test_fee():
    assert fee(100, True) == 105   # line coverage 100%, branch coverage 50%
```

Every line ran, so a line-only gate is green. But the `premium=False` edge (the implicit `else` where `base` stays 0) was never taken; `--cov-branch` flags it as a partial branch and `fee(100, False) == 100` is untested. Flip the default fee logic and the line-only suite never notices. Turning on `--cov-branch` converts this from a silent gap into a gate failure.

## Diff / patch coverage on PRs

A project-wide floor lets new code coast on the legacy suite: a PR can add an untested module and the aggregate barely moves, staying above `fail_under`. Gate the patch, not just the project, so every PR carries its own tests. Use `diff-cover` against the merge base on the `coverage.xml` the suite already emits:

```bash
# in the PR job, after pytest has written coverage.xml
diff-cover coverage.xml --compare-branch=origin/develop --fail-under=90
```

This fails when lines added or changed in the diff fall below 90% covered, independent of the project number. Make it a required check on `feature/*` PRs alongside the global floor (`ci_quality_gates` owns wiring it into branch protection and the aggregation job). The two together mean the project floor holds the line and the patch floor ratchets new code higher than the legacy average, so coverage trends up instead of being diluted.

## Setting the floor without gaming it

- Anchor the project floor to the current measured value and ratchet it up, never down. A floor lowered to make a red build green erodes silently; record any change with `save_decision` so the gate has an audit trail, per `ci_quality_gates`.
- Resist the push to 100%. The last few percent is defensive and dead code; chasing it produces assertion-free tests written only to color lines, which is the exact anti-pattern above. A branch-covered 85% with strong assertions beats a line-covered 100% with none.
- Coverage tells you where you have not tested; it cannot tell you whether what you tested is right. Pair the branch floor here with the mutation-score floor (70%+ on core logic) from `mutation_testing` and the requirements-coverage gate from `test_planning_and_traceability`. Those three are different questions: did code run, is it asserted, was the requirement verified. Report all three in `qa_report_the_required_output`; never let one stand in for another.

## Common pitfalls

- Gating on line coverage with `--cov-branch` off, so untaken `else` branches and error paths count as a passing floor.
- Reading high coverage as test quality. Assertion-free tests reach 100% line coverage and verify nothing; coverage cannot see a missing `assert`.
- Only a global `fail_under`, no diff gate, so new code rides the legacy suite's average and ships untested.
- `# pragma: no cover` or `exclude_lines` used to skip hard-to-test logic rather than genuinely unreachable code, inflating the number.
- Averaging core and peripheral modules into one figure, hiding weak coverage on risk and money paths behind well-tested utilities.
- Lowering `fail_under` to turn a red build green with no `save_decision` record; the floor decays one PR at a time.
- Treating the coverage number as the assertion-quality signal instead of running `mutation_testing`.

## Definition of done

- [ ] `pyproject.toml` configures `coverage.py` with `branch = true` / `--cov-branch`, `source`, an `exclude_lines` list, and `fail_under` set to the project floor (80%, 90%+ on core/risk/money modules enforced separately).
- [ ] The gate runs branch coverage and exits non-zero below the floor; `term-missing` partial-branch output is reviewed, not just the headline percentage.
- [ ] A `diff-cover` (or equivalent patch-coverage) check fails the PR when changed lines fall below the patch threshold, so new code carries its own tests.
- [ ] Every `# pragma: no cover` and `exclude_lines` entry covers genuinely untestable or unreachable code and carries a reviewed reason; none skips real logic.
- [ ] The floor is anchored and ratcheted upward only; any change is recorded via `save_decision`.
- [ ] Assertion quality is gated by `mutation_testing` and requirements coverage by `test_planning_and_traceability`; the coverage number is never reported as a substitute for either, and all three appear in `qa_report_the_required_output`.
