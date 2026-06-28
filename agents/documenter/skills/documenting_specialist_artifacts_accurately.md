## Documenting specialist artifacts accurately


When you document another specialist's work, capture the mandatory fields that role is required to produce. Missing fields make the doc non-compliant.

- Quant trading strategy / Model Hypothesis: record target Sharpe ratio, drawdown limit, profit factor, latency and slippage constraints, the dataset and features used, and the network or model architecture. A strategy doc without all of these is incomplete.
- ML / DRL work: record the validation method (cross-validation and out-of-sample test design), the explicit zero-data-leakage controls, and the safety guards (tensor-shape validation before critical ops, division-by-zero and float-overflow checks). State which guards exist, not just that the model works.
- QA artifacts: document that all external API calls and services are mocked, the unit and integration coverage for the change, and the specific backtesting-logic tests and their parameters.
- Security artifacts: document threat models by STRIDE category (Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege), the SAST and dependency/vulnerability scan results, and the mitigation for each finding.
- Software engineering artifacts: document the TDD evidence (Red-Green-Refactor), the SOLID/modularity decisions, and the design contracts between components; preserve existing docstrings and comments unrelated to the change.
- Business value and product artifacts: state the user or business problem, the measurable outcome, the baseline and target metric that proves it, and the owner accountable for the result. Keep one phrasing of value per artifact so it reads the same to engineering and to the business.
