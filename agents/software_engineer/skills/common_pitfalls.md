---
name: common-pitfalls
description: Lists the implementation failure modes a reviewer must reject on sight in this project's TDD, hexagonal Python codebase, from test-after coding to hexagon-breaking imports and print statements left in a diff. Use when reviewing a pull request or self-checking a diff before requesting code review.
---

# Software Engineer Common Pitfalls

The implementation failure modes a reviewer must reject on sight in this project's TDD, hexagonal Python codebase. Each pitfall maps to a check in the closing gate below: before requesting review, confirm the diff clears every item.

## Common pitfalls


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

- [ ] Every new behavior began as a failing pytest test observed red for an assertion failure before its production code was written; no test in the diff merely confirms an existing implementation.
- [ ] Mocks stand only at architectural boundaries (HTTP, time, randomness, filesystem, databases behind their port); no patch targets an internal collaborator the team owns.
- [ ] Every bug fix changes the root cause and carries a regression test reproducing the original defect; no swallowed exception or call-site null check papers over a symptom.
- [ ] Domain and application modules in the diff import no framework, ORM, or HTTP client; the hexagon's dependency arrow still points inward.
- [ ] Each commit is a single conventional-commit-typed concern; no commit mixes a feature, a refactor, and formatting, so `git bisect` stays usable.
- [ ] The diff contains no `print`, `breakpoint()`, or commented-out code.
- [ ] No refactor happened on a red bar; the full pytest suite is green at every commit point.
- [ ] Coverage on changed code comes from meaningful assertions: a mutation spot check on a changed line (flip a comparison, drop a guard) makes the suite fail.
