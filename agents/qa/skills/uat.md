## UAT


- Derive UAT cases from acceptance criteria and user stories, not from the implementation.
- Each case has: preconditions, steps, test data, expected result, actual result, pass/fail, and tester sign-off.
- Run on a production-like environment with realistic, anonymized data. Never run UAT against unit mocks.
- Record defects with severity (Blocker/Critical/Major/Minor/Trivial) and reproduction steps. Blockers and Criticals gate release.
