# Software Engineer Best Practices

Purpose: the working standard for implementing features and fixes in solomon-harness with strict TDD, clean Python, SOLID design, disciplined debugging, and Git Flow with conventional commits.

## Scope and non-negotiables

- Every logical change is driven by a test first. No production code is written before a failing test exists for it.
- Work only on `feature/*` or `bugfix/*` branches cut from `develop`. Never commit to `main` or `develop` directly.
- The core technology is Python. Use `pytest` for tests, `ruff` for lint and format, `mypy --strict` for types, `pytest-cov` for coverage.
- Preserve existing docstrings and comments unrelated to your change. Do not delete or rewrite them unless the user asks.
- Before coding a non-trivial feature, write `PLAN.md` (target files, edge cases, verification criteria) as the workflow requires.

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

## Clean code

- Functions do one thing at one level of abstraction. Keep them short; if a function needs section comments, split it.
- Cap nesting at two levels. Use guard clauses and early returns instead of `else` pyramids.
- Keep cyclomatic complexity at or below 10 per function. Check with `ruff` (C901) or `radon cc`. Split anything higher.
- Names carry intent. No single-letter names outside short comprehensions or math. No abbreviations that need a glossary. Booleans read as predicates (`is_active`, `has_pending`).
- No magic numbers or strings. Promote them to named constants or enums.
- Type-annotate every public function signature (PEP 484). Run `mypy --strict`. Do not let `Any` leak across module boundaries.
- Self-documenting code first; comments explain why, not what. Delete dead code and commented-out blocks rather than shipping them.
- Apply the rule of three before abstracting. Duplicating twice is fine; extract on the third occurrence so you abstract the real pattern, not a guess.
- Prefer pure functions and immutable data. Push side effects (IO, network, clock) to the edges so the core stays testable.

## SOLID, applied in Python

- Single Responsibility. A module or class has one reason to change. If you describe it with "and", split it.
- Open/Closed. Extend behavior by injecting strategies or new adapters, not by editing a growing `if/elif` switch. Add a case by adding a class, not by patching the old one.
- Liskov Substitution. Subtypes must honor the base contract: same accepted inputs, no stricter preconditions, no surprising exceptions. If a subclass throws `NotImplementedError` for an inherited method, the hierarchy is wrong.
- Interface Segregation. Define small `typing.Protocol` interfaces per use case. A consumer should not depend on methods it never calls.
- Dependency Inversion. Depend on abstractions, inject them through constructors. This maps directly to the Hexagonal model below.

## Hexagonal architecture (ports and adapters)

This role's design boundary. Keep the core domain clean.

- The core domain holds entities and business rules and imports zero frameworks, ORMs, HTTP clients, or database drivers.
- Driving (incoming) ports define how the outside invokes the domain. Driven (outgoing) ports define what the domain needs from infrastructure.
- Adapters translate: REST controllers, CLI handlers, and queue listeners drive the domain; database clients, HTTP gateways, and file clients implement the outgoing ports.
- Swapping a database, or REST for gRPC, must require only a new adapter. If a domain change is forced by an infrastructure swap, the dependency arrow points the wrong way.
- Ports speak in domain models and primitives, never in transport- or table-shaped structures. This is also why the domain is trivial to unit test: substitute fake adapters.

## Robust, defensive code

- Validate inputs at the boundary against a strict schema before the domain sees them. Never trust external clients, network payloads, or stored fields.
- Guard against division-by-zero and float overflow before any ratio, normalization, or accumulation. Return or raise a defined error instead of producing `inf`/`nan` silently.
- Validate array and tensor shapes before matrix or batched operations when touching numeric or ML code, so a shape mismatch fails with a clear message, not a deep stack trace.
- Catch specific exceptions, never bare `except:`. Do not swallow errors; either handle them meaningfully or let them propagate. Fail fast and loud over corrupting state quietly.
- Use parameterized queries; never build SQL by string concatenation with input.
- Keep secrets in environment variables or a secret manager. Never hardcode or commit credentials. Strip stack traces and internal details from messages returned to external callers.

## Security: STRIDE during design

Walk the STRIDE categories while planning any feature that touches input, auth, data, or external boundaries, and note mitigations in `PLAN.md`:

- Spoofing: authenticate identities, verify session tokens.
- Tampering: integrity checks, signatures, least-privilege filesystem permissions.
- Repudiation: immutable audit logs for security-relevant actions.
- Information Disclosure: encrypt in transit and at rest, mask sensitive fields, keep them out of logs.
- Denial of Service: rate limits, timeouts, payload size caps.
- Elevation of Privilege: least privilege and RBAC checks at every endpoint.

## Debugging method

Debug like a scientist, not by guessing.

1. Reproduce deterministically. Capture the exact input and environment. Encode the reproduction as a failing test before you touch the code.
2. Read the traceback bottom-up; the deepest frame in your code is usually the cause, not the framework frame above it.
3. Form one hypothesis, change one variable, predict the result, run, and observe. Do not shotgun multiple edits at once.
4. Binary-search the problem space: bisect inputs, comment out halves, or run `git bisect` to find the commit that introduced the regression.
5. Use `breakpoint()`/`pdb` and targeted structured logging over scattered prints. Remove debug noise before committing.
6. Fix the root cause, not the symptom. A `try/except` that hides the error is not a fix.
7. Confirm the new regression test goes green and the full suite stays green. The test you added is the proof the bug is dead.

When the cause is non-obvious or the fix encodes a design decision, record it in project memory with `save_decision` so the next agent sees the rationale.

## Git Flow and conventional commits

- Branch from `develop`: `feature/<short-slug>` for new capability, `bugfix/<short-slug>` for defects. `release/<version>` branches off `develop` to stabilize a release; `hotfix/<version>` branches from `main` for production-critical patches.
- Merge `feature/*` and `bugfix/*` back into `develop` through a reviewed pull request. Merge `release/*` and `hotfix/*` into both `main` and `develop` so fixes are never lost, and tag the release on `main`.
- Keep branches short-lived. Rebase on `develop` to stay current before integrating; resolve conflicts locally and never merge a red branch.
- Commit in small, coherent steps, ideally at green points. Each commit builds and passes tests on its own.
- Conventional Commits format: `type(scope): description`.
  - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`.
  - Subject in imperative mood ("add retry guard", not "added"), under 72 characters (50 is the sweet spot), no trailing period, no emoji.
  - Body explains why and any trade-off, wrapped at 72 columns. Footer carries `BREAKING CHANGE:` and issue references.
  - Match type to intent: a `refactor` commit changes no behavior and adds no test for new behavior; a `feat`/`fix` ships with its tests in the same or an adjacent commit.

## Common pitfalls for this role

- Writing the implementation first and back-filling tests. It produces tests that confirm the code instead of specifying behavior.
- Never seeing red, so a broken assertion or a misnamed fixture silently passes.
- Refactoring on a red bar and losing the ground truth of what still works.
- Mocking internals you own, so a harmless refactor breaks dozens of tests.
- Patching a symptom (swallowing the exception, adding a null check at the call site) instead of the root cause.
- Importing a framework, ORM, or HTTP client into the core domain and quietly breaking the hexagon.
- Large mixed commits that bundle a feature, a refactor, and formatting, so review and `git bisect` become useless.
- Leaving `print`/`breakpoint()` or commented-out code in the diff.
- Chasing 100 percent coverage with assertion-free tests that exercise lines without checking results.

## Definition of done

- A failing test existed first for every behavior, was observed red, and now passes.
- Full `pytest` suite is green; changed code has at least 90 percent line and branch coverage with meaningful assertions.
- All external services are mocked; tests are deterministic and order-independent.
- `ruff` (lint and format) and `mypy --strict` pass with no new warnings.
- Public functions are typed and named for intent; nesting and complexity are within the stated limits.
- Edge cases, error paths, and divide-by-zero/overflow/shape guards are covered where applicable.
- Core domain stays framework-free; new infrastructure sits behind a port and its adapter.
- STRIDE review noted in `PLAN.md` for boundary-touching features; no secrets in code or history.
- Bug fixes ship with a permanent regression test.
- Work is on a `feature/*` or `bugfix/*` branch with conventional commits, integrated via reviewed pull request; existing unrelated docstrings and comments are intact.
