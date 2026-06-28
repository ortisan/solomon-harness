## QA Report (the required output)


Publish per verification cycle. Include:

- Scope: branch under test, target branch, commit SHA, build id, environment.
- Results: total, passed, failed, skipped, flaky, with the run command and duration.
- Coverage: line and branch percentages, delta vs the previous run, modules below threshold.
- Backtest verification: metrics validated, leakage and cost checks, determinism check result.
- Defects: id, severity, status, owner.
- Risk and gate decision: explicit Go / No-Go with the reasons.
- Traceability: requirement or story id mapped to the tests that cover it.

Write it in plain, direct language. State the gate decision up front.
