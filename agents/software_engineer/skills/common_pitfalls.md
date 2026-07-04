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
