# TDD: Red, Green, Refactor

This skill governs how the software engineer writes code: strict test-driven
development, where a failing test precedes every line of production code. Run the
loop tightly — one behavior per cycle, minutes per cycle, not hours — and treat
any code without a covering test as unfinished work, not debt to schedule later.

## The test-first law

No production code exists until a failing test demands it. The rule has three
working parts, in the shape of the classic three laws: write no production code
except to pass a failing test; write no more of a test than is sufficient to
fail (a compile or import error counts as failing); write no more production
code than is sufficient to pass. The point is not ceremony. Test-first forces
the API to be designed from the consumer's side, guarantees every behavior has a
specification, and keeps each diff small enough to reason about.

## The cycle

1. Red. Write one failing test that names the behavior you want. Run it and
   confirm it fails for the right reason: an assertion failure, not an import or
   collection error. A test that has never failed proves nothing — it may be
   asserting nothing, or not running at all.
2. Green. Write the least code that makes the test pass. Hardcoding to get green
   is allowed and expected; the next test forces generalization. Do not add code
   for behavior no test demands.
3. Refactor. With the bar green, remove duplication, rename for intent, extract
   functions, and simplify. Run the full suite after every refactor step. Never
   refactor on red — a red bar means you have lost the ground truth of what
   still works.

Rules that keep the loop honest:

- Watch the test fail before you make it pass. Skipping the red step hides false
  positives.
- Use the test as the first consumer of your API. Awkward setup in a test is a
  design smell, not a test problem.
- For a bug, the cycle starts with a failing regression test that reproduces the
  defect. Fix only after it is red. That test stays in the suite forever.
- Commit at green points so you always have a working fallback.

## Test naming and shape

- Name tests for behavior and condition:
  `test_withdraw_raises_when_balance_insufficient`, not `test_withdraw_2`. The
  suite output should read as a specification of the module.
- Structure each test Arrange, Act, Assert. One logical assertion — one
  behavior — per test; when a test needs a second unrelated assert, it is two
  tests. No branching or loops with hidden assertions inside test bodies.
- Use `pytest.mark.parametrize` for input tables instead of copy-pasted tests.
  Use fixtures for setup, not module-level globals.
- FIRST: Fast, Independent, Repeatable, Self-validating, Timely. Tests must not
  depend on order, wall-clock time, network, or shared mutable state.
- Cover the edges: empty, single, max, boundary, negative, None, duplicate, and
  the unhappy path. The happy path alone is not done.

## When to mock

- Mock all external API calls and services so unit tests are hermetic: HTTP with
  `responses`/`respx`, time with `freezegun`, randomness by seeding or injecting
  the RNG, filesystem with `tmp_path`, databases behind their port interface.
- Mock at architectural boundaries (the ports), not internal collaborators you
  own. Over-mocking internals couples tests to structure, so a harmless refactor
  breaks dozens of tests for no behavioral reason.
- Assert on observable behavior and outputs, not private call counts, unless the
  interaction itself is the contract (for example, "the handoff was logged
  exactly once").
- For anything with backtest or financial logic, add explicit tests that pin the
  parameters and the expected numeric results.

## Coverage and mutation spot checks

- Target 90 percent line and branch coverage on changed code. Coverage is a
  floor that catches untested branches, never proof of correctness: a green
  suite with weak assertions is worse than no suite.
- Spot-check assertion strength with mutation testing: run `mutmut` on the
  changed module, or apply a manual mutation — flip a comparison, off-by-one a
  boundary, delete a guard clause. If the suite stays green, the tests exercise
  the line but check nothing; fix the test, not the score. The full mutation
  policy lives in the `test_pyramid_and_mutation_testing` skill.

## Common pitfalls

- Writing the implementation first and back-filling tests that confirm the code
  instead of specifying behavior.
- Never seeing red, so a broken assertion or a misnamed fixture silently passes
  forever.
- Refactoring on a red bar and losing the ground truth of what still works.
- Mocking internal collaborators you own, so refactors fail loudly for no
  behavioral reason.
- Multiple unrelated behaviors asserted in one test, so a failure does not
  localize.
- Chasing the coverage number with assertion-free tests that exercise lines
  without checking results.
- Skipping the regression test on a bug fix, so the defect returns with the next
  refactor.
- Cycles that run for hours: one giant red test written up front, then a day of
  code to reach green, which is waterfall with extra steps.

## Definition of done

- [ ] Every new behavior and every bug fix began as a failing test that was seen
      to fail for the right reason.
- [ ] Tests are named for behavior and condition, follow Arrange-Act-Assert, and
      assert one behavior each.
- [ ] External services, time, randomness, filesystem, and databases are mocked
      at the boundary; the suite passes offline.
- [ ] The full suite is green; changed code meets 90 percent line and branch
      coverage.
- [ ] At least one mutation spot check on the changed module was killed by the
      suite.
- [ ] Refactoring happened only on green; commits land at green points.
- [ ] Bug fixes carry a permanent regression test.
