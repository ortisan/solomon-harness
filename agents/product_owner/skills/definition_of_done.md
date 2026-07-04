# Product Owner Definition of Done

The exit gate for product work: what must hold before a PRD and its stories are handed to engineering. The pitfalls below are the ways this checklist gets falsely satisfied; the checklist itself follows.

## Common pitfalls

- Template sections deleted instead of marked N/A with a one-line reason, so the reviewer cannot tell a settled question from an unasked one.
- A success metric with a target but no baseline or measurement window, which makes the launch unfalsifiable and "done" unprovable.
- Stories in As-a/I-want/so-that form that still fail INVEST (layer splits, unestimable epics); format compliance is not readiness.
- Given-When-Then criteria that cover only the happy path, leaving boundary and failure behavior to be decided ad hoc in code.
- Domain constraints stated as prose ("must be robust") instead of testable criteria (Sharpe and drawdown numbers, mocked services, named STRIDE mitigations), so QA cannot verify them.
- A priority asserted without the MoSCoW/RICE/WSJF inputs recorded, so the ordering cannot be audited or renegotiated later.
- The PRD declared done without decisions and milestones persisted to project memory, forcing the next session to re-litigate settled scope.

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
