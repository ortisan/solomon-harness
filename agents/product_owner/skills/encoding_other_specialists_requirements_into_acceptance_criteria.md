---
name: encoding-other-specialists-requirements-into-acceptance-criteria
description: Governs encoding another specialist's non-functional requirement into a PRD as a measurable Given-When-Then acceptance criterion, sourced and attributed to that specialist rather than invented or softened into prose. Use when a PRD touches a quant, ML, QA, security, or SRE constraint.
---

# Encoding Other Specialists' Requirements Into Acceptance Criteria

This skill governs how the product_owner carries another specialist's non-functional requirement into a PRD as a measurable, pass-or-fail acceptance criterion rather than soft prose. You write the PRD, but the constraints belong to the specialists who own them; your job is to name the right specialist's bar and state it as something QA can run and fail, never to design the solution yourself.

## The encoding rule

When a PRD touches a specialist's domain, the acceptance criteria must carry that specialist's requirement verbatim and measurably. The translation has three moves: source the number from the owning specialist, attach a unit and a threshold, and write it in Given/When/Then so a test can be derived directly. A criterion a tester cannot turn into an assertion is not done; it is a wish.

Default to the Given/When/Then form because it forces a precondition, a trigger, and an observable result. "The system should be secure" is unfallible. "Then no log line in the request path contains a value matching the PII patterns" is a test.

## Per-domain bars to encode

- Quant trading / DRL features. State the Model Hypothesis as testable criteria: target Sharpe ratio, drawdown limit (max acceptable peak-to-trough), profit factor, latency and slippage constraints, the dataset and features used, and the network or model architecture. Example line: "Then the backtest reports Sharpe >= 1.5, max drawdown <= 15 percent, profit factor >= 1.3, on out-of-sample data, with slippage modeled at the stated bps." A quant PRD without these numbers is incomplete.
- ML / data features. Require cross-validation and out-of-sample evaluation, and assert zero data leakage between train and test. Require runtime guards as criteria: tensor/array shapes validated before critical operations, and explicit checks against division-by-zero and float overflow. "Then training and evaluation share no overlapping records and the leakage check passes."
- QA expectations. State that all external API calls and services are mocked in tests, that unit and integration tests exist for every logical change, and that backtesting logic and parameters have dedicated tests. Set the coverage and test-type expectation as a release gate.
- Security requirements. For any feature handling input, auth, data, or external interfaces, require a STRIDE pass and turn each relevant category into criteria: Spoofing (identity/auth), Tampering (integrity), Repudiation (audit logging), Information disclosure (no PII/secrets in logs or responses), Denial of service (rate limits, resource bounds), Elevation of privilege (authorization checks). Name the categories that apply and what the mitigation must prove.
- SRE / reliability. Encode the SLO numbers the sre owns: latency percentiles (p95, p99), availability target, error budget, and recovery objectives (RTO/RPO). "Then p95 latency for the endpoint is < 400ms under the stated load" is testable; "fast" is not.
- Engineering and architecture. Reflect the TDD mandate and design-contract boundaries in the rollout section: the change ships behind tests, and the component boundaries named in the PRD are the contracts engineering builds against.

## Worked example: a security and an SRE bar as acceptance criteria

A feature exports a customer activity report. The security specialist's constraint is "no PII in logs"; the sre's constraint is "p95 < 400ms". Both are non-functional, both are owned by someone other than you, and both must land in the PRD as criteria a test can fail.

```
Story: Export customer activity report

Non-functional acceptance criteria (sourced from specialists):

# Security — Information disclosure (owner: security, from STRIDE pass)
Given a request that generates a customer activity report,
When the export handler runs and emits log lines at any level,
Then no log line contains email, full name, government id, or card number
     (assert against the agreed PII pattern set), and a test injects a record
     with known PII and asserts those values never appear in captured logs.

# Reliability — latency SLO (owner: sre)
Given the report endpoint under the stated representative load (N concurrent users),
When 1,000 export requests are issued,
Then p95 response time is < 400ms and p99 is < 800ms, measured by the load test,
     and the test fails the build if the p95 budget is exceeded.

# Security — Spoofing / Elevation of privilege (owner: security)
Given a user authenticated as customer A,
When they request customer B's activity report,
Then the response is 403 and no row of B's data is returned.
```

Each criterion names the owning specialist, carries a concrete threshold and unit, and reads as a test. The PII rule is not "handle data carefully"; it is an injected record and an assertion over captured logs. The latency rule is not "be performant"; it is a p95 number measured under a defined load with a build-failing gate. You did not design the log redaction or the caching strategy that meets the SLO; you stated the bar the responsible specialist set and made it falsifiable.

## Common pitfalls

- Softening a hard requirement into prose. "The system should protect user data" cannot be tested; the security category and its assertion must survive into the criteria intact, or the gate disappears.
- Inventing the number yourself. Latency, Sharpe, drawdown, and coverage targets belong to the owning specialist; a product_owner-guessed threshold either blocks delivery needlessly or passes something unsafe.
- Stating a target with no unit or measurement method. "p95 < 400ms" with no load definition is unmeasurable; name the load, the percentile, and where it is measured.
- Encoding the requirement but not gating on it. A criterion that is written but not a release gate is decoration; tie it to the build or the Definition of Done so failing it blocks the merge.
- Designing the solution in the PRD. Specifying the redaction filter or the cache layer oversteps the role and makes you accountable for an implementation the specialist owns.
- Dropping the source. A criterion with no named owner cannot be questioned or updated when the bar changes; always attribute it to the specialist who set it.

## Definition of done

- [ ] Every specialist constraint that applies is present as an acceptance criterion, not as prose.
- [ ] Each non-functional criterion is written in Given/When/Then so a test can be derived directly.
- [ ] Each criterion carries a concrete threshold with a unit and a measurement method (e.g. p95 under stated load, Sharpe on out-of-sample data).
- [ ] Each criterion names the owning specialist (security, sre, ml_engineer, quant_trader, qa) as its source.
- [ ] Security-relevant features list the applicable STRIDE categories and what each mitigation must prove.
- [ ] The numbers came from the owning specialist, not from a product_owner guess.
- [ ] Each criterion is wired to a release gate or the Definition of Done, not merely recorded.
- [ ] No criterion prescribes the implementation; each states an outcome the responsible specialist owns.
