## Mandatory project competencies to honor in any design


These come from the project rules and bind every artifact you produce.

- **TDD is mandatory.** Design for testability: depend on interfaces, allow injection at every boundary, keep the Core Domain free of I/O so it is unit-testable without infrastructure.
- **QA.** Mock all external API calls and services in tests so suites are isolated and deterministic. Every contract you define ships with consumer-driven contract tests. Cover backtesting logic and parameters explicitly where the system has them.
- **ML / DRL designs.** Enforce zero data leakage by construction (strict train/validation/test and walk-forward splits, no future information in features). Require cross-validation and out-of-sample evaluation in the design. Mandate guards before critical tensor ops: validate tensor shapes, and protect against division-by-zero and float overflow/underflow.
- **Quant strategy designs.** Any model hypothesis the architecture supports must state target Sharpe ratio (for example >= 1.5 net of costs), maximum drawdown limit (for example <= 20%), minimum profit factor (for example >= 1.3), latency and slippage constraints (for example sub-50 ms decision-to-order, slippage modeled per instrument), the dataset and features used, and the network/model architecture. No backtest result is valid without realistic transaction costs and slippage.
- **Security - STRIDE.** Run a STRIDE pass on every Container and trust boundary: Spoofing (authentication), Tampering (integrity/signing), Repudiation (audit logging), Information disclosure (encryption, least privilege), Denial of service (rate limiting, quotas, timeouts), Elevation of privilege (authorization, isolation). Record the threats and mitigations; an unmitigated high-severity threat blocks acceptance.
- **Preserve existing docstrings and comments** unrelated to the change.
- **Humanizer tone** in every artifact: direct, concise, senior-engineer prose. No emojis or icons.
