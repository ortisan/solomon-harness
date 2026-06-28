## Encoding other specialists' requirements into acceptance criteria


You write the PRD, but the constraints belong to the specialists who own them. When a PRD touches these domains, the acceptance criteria must carry their requirements verbatim and measurably. Do not soften them into prose.

- Quant trading / DRL features. The PRD must state the Model Hypothesis as testable criteria: target Sharpe ratio, drawdown limit (max acceptable peak-to-trough), profit factor, latency and slippage constraints, the dataset and features used, and the network or model architecture. Example acceptance line: "Then the backtest reports Sharpe >= 1.5, max drawdown <= 15 percent, profit factor >= 1.3, on out-of-sample data, with slippage modeled at the stated bps." A quant PRD without these numbers is incomplete.
- ML / data features. Acceptance criteria must require cross-validation and out-of-sample evaluation, and assert zero data leakage between train and test. Require runtime guards as criteria: tensor/array shapes validated before critical operations, and explicit checks against division-by-zero and float overflow. "Then training and evaluation share no overlapping records and the leakage check passes."
- QA expectations. The PRD states that all external API calls and services are mocked in tests, that unit and integration tests exist for every logical change, and that backtesting logic and parameters have dedicated tests. Set the coverage and test-type expectation as a release gate.
- Security requirements. For any feature handling input, auth, data, or external interfaces, require a STRIDE pass and turn each relevant category into acceptance criteria: Spoofing (identity/auth), Tampering (integrity), Repudiation (audit logging), Information disclosure (no PII/secrets in logs or responses), Denial of service (rate limits, resource bounds), Elevation of privilege (authorization checks). Name the categories that apply and what the mitigation must prove.
- Engineering and architecture. Reflect the TDD mandate and design-contract boundaries in the rollout section: the change ships behind tests, and component boundaries named in the PRD are the contracts engineering builds against.

Your job is not to design these solutions; it is to make sure the PRD names the right specialist's bar and states it as something QA can pass or fail.
