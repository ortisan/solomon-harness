## Coverage (a floor, not a finish line)


- Measure with `pytest-cov` (line and branch): `--cov --cov-branch --cov-report=term-missing --cov-report=xml`.
- Thresholds: 80% line coverage minimum project-wide via `--cov-fail-under=80`; 90%+ on core domain, risk, and money-handling modules. Fail CI below the floor.
- Branch coverage is the real target. 100% line with partial branch coverage hides untested conditionals.
- Coverage measures executed lines, not asserted behavior. Defend the suite with mutation testing (`mutmut` or `cosmic-ray`) on critical modules; a surviving mutant means a missing assertion. Target a mutation score of 70%+ on core logic.
- Exclude only generated code and genuine no-ops, with an explicit `# pragma: no cover` and a one-line reason. Never raise the floor by excluding hard code.
