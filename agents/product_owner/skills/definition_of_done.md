## Definition of done


A PRD and its stories are done when:
- [ ] PRD contains all ten template sections, with any N/A justified in one line.
- [ ] Primary success metric has a baseline, a target, and a measurement window; guardrail metrics are listed.
- [ ] Goals and non-goals are explicit; out-of-scope list is present.
- [ ] Every story follows the As-a/I-want/so-that format and passes INVEST.
- [ ] Every story has Given-When-Then acceptance criteria covering happy, boundary, and failure paths, with specific values.
- [ ] Domain constraints are encoded as testable criteria where applicable: quant (Sharpe, drawdown, profit factor, latency, slippage, dataset/features, architecture), ML (cross-validation, out-of-sample, zero leakage, shape/overflow/divide-by-zero guards), QA (external services mocked, unit + integration tests), security (relevant STRIDE categories named with mitigations).
- [ ] Priority is set with a named method (MoSCoW/RICE/WSJF) and the inputs are recorded.
- [ ] Dependencies, assumptions, risks, and open questions each have an owner.
- [ ] Decisions and milestones are persisted to project memory.
- [ ] Text follows the humanizer style: direct, concise, no emojis, no AI cliches.
