# Test Design Rules

Case-level test design decides whether a green suite actually proves anything. This skill owns the mechanics of turning one behavior into the right set of cases: how to partition an input domain, which boundaries are non-negotiable, how to collapse a combinational explosion to a defensible minimum, and how to assert an invariant instead of a single example. It is the technique layer beneath `test_planning_and_traceability`: that skill scores risk and decides which criteria warrant which depth; this skill generates the concrete cases once that decision is made. At the /solomon-review gate, a reviewer reads tests against these rules to judge whether a passing run is evidence or theatre.

## Test structure rules

Non-negotiable shape for every case, regardless of technique below:

- One behavior per test. The name states it: `test_<unit>_<condition>_<expected>`, e.g. `test_fee_below_min_raises_valueerror`.
- Arrange-Act-Assert, visibly separated by blank lines. No assertions in Arrange.
- Deterministic always. Pin seeds (`random.seed`, `numpy.random.default_rng(seed)`, `PYTHONHASHSEED=0`), freeze time with `freezegun` or `time-machine`, and never depend on execution order. Add `pytest-randomly` to surface order coupling; flake handling is owned by `flaky_tests`.
- Test the public contract (ports), not private internals. Tests bound to implementation rot on every refactor.
- Assert specific values and error types: `pytest.raises(SpecificError, match=...)`, never bare `assert result` or broad `Exception`.
- Parametrize instead of copy-paste; each case carries an `id`.

## Equivalence partitioning

Split each input domain into classes the system treats identically, then test one value per class. A function taking an age `0-150` has at least four partitions: valid `0-150`, invalid negative, invalid `>150`, invalid non-integer. Picking `42`, `-1`, `200`, and `"x"` covers the behavior; adding `43`, `44`, `45` adds cost and no coverage. Partition the output domain too when several inputs map to distinct result classes (a discount tier, an HTTP status band). Each invalid partition gets its own case, because a single malformed input can mask a second one. Reference these partitions as the `Technique` column in the RTM owned by `test_planning_and_traceability`.

## Boundary value analysis and the canonical boundary set

Defects cluster at partition edges. For high-risk numeric inputs use three-value BVA: `boundary-1`, `boundary`, `boundary+1`. A minimum charge of `100` is tested at `99`, `100`, `101`. Two-value BVA tests the two values straddling the edge — the last value of one partition and the first of the next (for a minimum of `100`: `99` and `100`) — the lighter variant for medium-risk paths.

This is the canonical boundary checklist. Every input-handling test references it; siblings point here rather than re-listing it:

- empty (`""`, `[]`, `{}`, empty file, empty stream)
- single element (off-by-one in loops and slicing)
- max (length limits, `sys.maxsize`, column width, `INT_MAX`)
- zero (and the division-by-zero path)
- negative
- `None` / null
- `NaN` (note `NaN != NaN`; assert with `math.isnan`)
- `inf` and arithmetic overflow
- unicode and encoding (combining marks, emoji, `utf-8` vs `latin-1`, BOM, normalization NFC/NFD)
- timezone and DST edges (UTC vs local, the spring-forward gap, leap second, `2038` epoch rollover)

Numeric and parsing paths must add `NaN`, `inf`, and overflow. Finance paths inherit the silent-failure cases from `backtesting_verification_specific_because_finance_bugs_are_silent`.

```python
import math
import pytest

@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (99, "below_min"),     # boundary - 1
        (100, "ok"),           # boundary
        (101, "ok"),           # boundary + 1
        (0, "below_min"),      # zero
        (-1, "invalid"),       # negative
    ],
    ids=["below_min", "at_min", "above_min", "zero", "negative"],
)
def test_charge_validation_boundaries(amount, expected):
    assert classify_charge(amount) == expected

@pytest.mark.parametrize(
    "bad", [None, math.nan, math.inf, -math.inf],
    ids=["none", "nan", "posinf", "neginf"],
)
def test_charge_validation_rejects_nonfinite(bad):
    with pytest.raises(ValueError, match="finite"):
        classify_charge(bad)
```

## Decision tables for combinational logic

When the outcome depends on a combination of conditions (eligibility, pricing, feature gating, permission rules), list conditions as rows and rules as columns. The full rule count is the product of the condition value counts; collapse infeasible combinations and don't-care cells, then require at least one test per surviving rule.

Worked count: three booleans give `2^3 = 8` rules. If `is_admin=True` forces the result regardless of `is_owner` and `is_locked`, those four `is_admin=True` rows collapse into one don't-care rule, leaving 5 tested rules with explicit expected outcomes.

| # | is_admin | is_owner | is_locked | expected    |
|---|----------|----------|-----------|-------------|
| 1 | T        | -        | -         | allow       |
| 2 | F        | T        | F         | allow       |
| 3 | F        | T        | T         | deny_locked |
| 4 | F        | F        | F         | deny        |
| 5 | F        | F        | T         | deny        |

Each surviving row maps to one parametrized case. A few happy-path cases over a decision table is the classic gap where the production bug hides.

## State-transition testing

For stateful flows (order lifecycle, auth session, retry/backoff, payment capture) draw the state machine and cover every valid transition once, plus the invalid transitions that must be rejected. An order `created -> paid -> shipped -> delivered` has valid edges to test and illegal jumps (`created -> delivered`, `delivered -> paid`) that must raise rather than silently succeed. Missing the illegal-transition tests is how a refund gets applied to an unshipped order. Model it as a transition table and parametrize over `(from_state, event, expected_state_or_error)`.

## Pairwise and combinatorial reduction

When several independent parameters multiply the matrix beyond what is worth running, generate an all-pairs (2-wise) set so every pair of parameter values appears at least once, at a fraction of the full cross-product. Use `allpairspy` in Python or Microsoft PICT. Then add back, by hand, the specific full combinations that risk analysis in `test_planning_and_traceability` flagged as high-impact.

```python
from allpairspy import AllPairs

params = [
    ["chrome", "firefox", "safari"],
    ["free", "pro", "enterprise"],
    ["US", "EU", "APAC"],
]
cases = list(AllPairs(params))  # ~9 cases vs 27 in the full cross-product
```

Reducing by all-pairs is defensible; deleting cases at random to fit a time budget is not.

## Property-based testing with hypothesis

For parsers, serializers, encoders, math, and any function with a stated invariant, assert the invariant over generated inputs instead of hand-picked examples. `hypothesis` searches the space and, on failure, shrinks to a minimal counterexample (e.g. the empty string, `0`, or a single surprising codepoint) so the defect is obvious. Pin any shrunk failure with `@example` so it stays a permanent regression case.

```python
from hypothesis import given, example, strategies as st

@given(st.text())
@example("")          # shrunk counterexample from a prior failure, pinned
def test_encode_decode_roundtrip(s):
    # invariant: decode is the left inverse of encode
    assert decode(encode(s)) == s

@given(st.lists(st.integers()))
def test_sort_is_idempotent_and_preserves_multiset(xs):
    once = my_sort(xs)
    assert my_sort(once) == once          # idempotent
    assert sorted(once) == sorted(xs)     # no element invented or dropped
```

Property tests complement the example-based techniques above; they do not replace the decision-table and boundary cases that pin known-critical behavior. Record the invariant as the verifying artifact in the RTM.

## Common pitfalls

- Testing many values from the same equivalence class while leaving a whole partition (the invalid one) untouched.
- Skipping the boundary checklist for a "simple" function: empty, `None`, and `NaN` are where the simple function breaks.
- Asserting `NaN == NaN` (always false) instead of `math.isnan`; the test passes by accident.
- A decision table verified only on happy-path rows, so the collapsed-but-still-feasible rules ship untested.
- State machines tested only on the legal path, leaving illegal transitions to succeed silently in production.
- Combinatorial blow-up "fixed" by deleting cases at random rather than an all-pairs set plus named high-risk combinations.
- A property test with a trivial invariant (`len(out) >= 0`) that can never fail; the invariant must constrain the result.
- Asserting on a bare truthy result or catching broad `Exception`, hiding both the value and the error type.

## Definition of done

- [ ] Every input domain is partitioned into valid and invalid equivalence classes, with one case per class.
- [ ] High-risk numerics use three-value BVA, and inputs are checked against the canonical boundary set (empty, single, max, zero, negative, None, NaN, inf/overflow, unicode/encoding, timezone/DST).
- [ ] Combinational logic has a decision table with infeasible/don't-care cells collapsed and at least one test per surviving rule.
- [ ] Stateful flows cover every valid transition plus the invalid transitions that must be rejected.
- [ ] Parameter explosions are reduced with an all-pairs set (`allpairspy`/PICT) and high-risk full combinations added back by hand.
- [ ] Parsers, serializers, and math carry a `hypothesis` property test asserting a real invariant, with any shrunk counterexample pinned via `@example`.
- [ ] Each test follows the structure rules (one behavior, AAA, deterministic seeds/clock, public-contract assertions, specific error types) and the technique is recorded for `test_planning_and_traceability` to link in the RTM.
