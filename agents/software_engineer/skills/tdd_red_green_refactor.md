## TDD: Red, Green, Refactor


Run the loop tightly. One behavior per cycle, minutes per cycle, not hours.

1. Red. Write one failing test that names the behavior you want. Run it and confirm it fails for the right reason (assertion failure, not import or collection error). A test that has never failed proves nothing.
2. Green. Write the least code that makes the test pass. Hardcoding to get green is allowed and expected; the next test forces generalization. Do not add code for behavior no test demands.
3. Refactor. With the bar green, remove duplication, rename for intent, extract functions, and simplify. Run the full suite after every refactor step. Never refactor on red.

Rules that keep the loop honest:
- Watch the test fail before you make it pass. Skipping the red step hides false positives.
- Use the test as the first consumer of your API. Awkward setup in a test is a design smell, not a test problem.
- For a bug, the cycle starts with a failing regression test that reproduces the defect. Fix only after it is red. That test stays in the suite forever.
- Commit at green points so you always have a working fallback.

Test quality (FIRST and AAA):
- Fast, Independent, Repeatable, Self-validating, Timely. Tests must not depend on order, wall-clock time, network, or shared mutable state.
- Structure each test Arrange, Act, Assert. One logical assertion (one behavior) per test. No branching or loops with hidden assertions inside test bodies.
- Use `pytest.mark.parametrize` for input tables instead of copy-pasted tests. Use fixtures for setup, not module-level globals.
- Name tests for the behavior and condition: `test_withdraw_raises_when_balance_insufficient`, not `test_withdraw_2`.
- Cover the edges: empty, single, max, boundary, negative, None, duplicate, and the unhappy path. The happy path alone is not done.

Mocking and isolation (QA competency applies to your tests too):
- Mock all external API calls and services so unit tests are hermetic: HTTP with `responses`/`respx`, time with `freezegun`, randomness by seeding or injecting the RNG, filesystem with `tmp_path`, databases behind their port interface.
- Mock at architectural boundaries (the ports), not internal collaborators you own. Over-mocking internals couples tests to structure and makes refactors fail loudly for no reason.
- Assert on observable behavior and outputs, not on private call counts, unless the interaction itself is the contract.
- For anything with backtest or financial logic, add explicit tests that pin the parameters and expected numeric results.

Coverage discipline:
- Target 90 percent line and branch coverage on changed code. Treat coverage as a floor that catches untested branches, never as proof of correctness.
- A green suite with weak assertions is worse than no suite. Prefer fewer strong tests over many shallow ones.
