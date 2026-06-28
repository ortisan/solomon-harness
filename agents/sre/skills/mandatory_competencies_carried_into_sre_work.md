## Mandatory competencies carried into SRE work


These project rules apply to every change an SRE ships (tooling, pipelines, runbook automation, load harnesses):

- **TDD is mandatory** (Red, Green, Refactor). Write the failing test first, including for IaC modules, deployment scripts, and alerting logic. Follow SOLID and keep modules small with clear contracts. Preserve existing docstrings and comments unrelated to your change.
- **QA**: mandatory unit and integration tests for all new code and logic changes. Mock every external API and cloud service so tests run hermetically and offline. Verify any backtesting or simulation logic explicitly where present.
- **ML/quant guards** (whenever SRE touches numeric or model-adjacent automation, capacity forecasting, or autoscaler tuning): validate tensor/array shapes before critical operations, guard against division-by-zero and float overflow, use cross-validation and out-of-sample tests, and ensure zero data leakage. If you formulate any model hypothesis, state target Sharpe ratio, drawdown limit, profit factor, latency and slippage constraints, the dataset and features, and the model architecture.
- **Security (STRIDE)** during design of every pipeline and endpoint: Spoofing (authenticate service identities), Tampering (sign artifacts and configs), Repudiation (immutable audit logs), Information Disclosure (encrypt in transit and at rest, strip secrets from logs and error messages), Denial of Service (rate limits, timeouts, payload-size caps, load shedding — directly your availability concern), Elevation of Privilege (least privilege, RBAC on every endpoint). Keep credentials in a secret manager, never in git history.
- **Observability**: emit structured JSON logs carrying `trace_id` and `span_id`, instrument counters/gauges/histograms with service/region/operation tags, and propagate W3C trace context across service boundaries so SLIs are measurable end to end.
- **Git Flow and Conventional Commits**: develop on `feature/*` or `bugfix/*`, hotfix production from `hotfix/*` off main. Commit as `type(scope): description` in the imperative, first line under 72 characters, no emojis.
