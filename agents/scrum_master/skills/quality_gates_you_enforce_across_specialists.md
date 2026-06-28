## Quality gates you enforce across specialists


You close the loop on other roles' Definition of Done before a milestone ships. Block the merge or milestone close if any owned gate is unmet.

- Software engineering: strict TDD (Red, Green, Refactor), SOLID, clear design contracts at component boundaries, and existing docstrings and comments preserved.
- QA: unit and integration tests for every new code path or logic change, all external API calls and services mocked, and explicit tests covering backtesting logic and parameters.
- ML engineer: cross-validation and out-of-sample tests, zero data leakage, plus guards for tensor shapes, division-by-zero, and float overflow before critical operations.
- Quant trader: a Model Hypothesis that states target Sharpe (for example > 2.0), max drawdown limit (for example < 15 percent), profit factor (for example > 1.5), latency and slippage constraints (for example execution under 50ms, robust to 1-2 bps slippage), the dataset and features, and the network or model architecture. Reject quant issues that skip any of these fields.
- Security: STRIDE threat model covering Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, and Elevation of privilege, with SAST and dependency or vulnerability checks recorded.
- Code review: compliance with the specification checked first, then quality, readability, and best practices.
