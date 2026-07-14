---
name: documenting-specialist-artifacts-accurately
description: Governs transcribing a specialist's artifact (backtest, threat model, dashboard, QA report) into documentation without rounding, softening, or upgrading its claims, and lists each artifact type's mandatory fields. Use when writing up a specialist deliverable for publication.
---

# Documenting Specialist Artifacts Accurately

This skill governs how the documenter writes up another specialist's output — a backtest, a threat model, a dashboard, a test report — without distorting its claims. The stance: the documenter is a faithful transcriber with an audit function, not a translator into optimism. Every number is copied from the source artifact, every caveat travels with its claim, and a summary that the artifact cannot support does not ship.

## Verify against the source artifact

Never document from a specialist's verbal or chat summary alone. Open the artifact itself — the backtest run record in memory, the threat-model document, the dashboard's panel definitions, the CI test output — and transcribe from there:

- Copy exact values with their units and the period they cover. "Sharpe 1.42 (out-of-sample, 2023-01 to 2025-12, daily)" is a claim; "strong risk-adjusted returns" is not.
- When the specialist's prose summary and their own artifact disagree, stop. Do not pick the friendlier number and do not average the two; return it to the owning agent to reconcile, and document only the reconciled value.
- Give every material claim a provenance line: the artifact identifier (backtest run id, memory record id, report path, commit), the date it was produced, and the owning agent. This follows the `research_analyst` convention — every claim carries a source and a timestamp — applied to internal artifacts.
- Reproduce thresholds and targets alongside results, so the reader can judge pass or fail without hunting: "max drawdown 8.3% against a 10% limit" beats "drawdown within limits".

## Mandatory fields by artifact type

Each specialist role is required to produce specific fields; a write-up that omits them is non-compliant, and the documenter's job includes noticing the omission:

- **Quant strategy / Model Hypothesis** (`quant_trader`): target Sharpe ratio, drawdown limit, profit factor, latency and slippage constraints, the dataset and features used, and the network or model architecture. Report in-sample and out-of-sample results separately, and never present in-sample numbers as performance.
- **ML / DRL work** (`ml_engineer`): the validation method (cross-validation design, out-of-sample tests), the explicit zero-data-leakage controls, and the safety guards — tensor-shape validation before critical operations, division-by-zero and float-overflow checks. State which guards exist, not merely that the model works.
- **QA artifacts** (`qa`): confirmation that all external API calls and services are mocked, the unit and integration coverage for the change, and the specific backtesting-logic tests with their parameters.
- **Security artifacts** (`security`): the threat model organized by STRIDE category (Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege), SAST and dependency-scan results, and the mitigation for each finding. Severity words are quoted as rated: a "critical" stays "critical" in every retelling.
- **Observability artifacts** (`observability`): for each documented dashboard or alert, what it measures, the exact query, the units, and the threshold or SLO it relates to. A screenshot without its query is decoration, not documentation.
- **Software engineering artifacts** (`software_engineer`): TDD evidence (the Red-Green-Refactor trail), the modularity and design-contract decisions, and confirmation that unrelated docstrings and comments were preserved.
- **Business and product artifacts** (`product_owner`): the user or business problem, the measurable outcome, the baseline and target metric that proves it, and the accountable owner. Keep one phrasing of the value per artifact so engineering and business read the same sentence.

## Distortion modes to refuse

These are the specific ways a faithful number becomes a misleading one; a reviewer should reject each on sight:

- Rounding in the flattering direction, or switching units and periods mid-document (a monthly Sharpe presented next to annualized targets).
- Dropping confidence intervals, sample sizes, or "in the checks run" qualifiers. If the artifact says "no leakage detected by the controls applied", the write-up does not say "there is no leakage".
- Upgrading modality: "suggests" becoming "shows", "shows" becoming "proves". The documented claim keeps the strength the specialist gave it.
- Cherry-picking the timeframe or the metric that looks best while omitting the mandated ones (reporting profit factor while the drawdown limit was breached).
- Replacing a tail metric with an average (mean drawdown where the field is maximum drawdown).
- Softening security language or burying a high-severity finding below cosmetic ones.
- Summarizing a failed or partial result as "largely successful" — state what passed, what failed, and what remains open.

## Common pitfalls

- Documenting from the chat summary instead of the artifact, inheriting whatever optimism the summary added.
- Missing mandatory fields silently: a strategy write-up without slippage constraints reads complete to a lay reader, and the documenter is the last check that catches it.
- No provenance, so a number cannot be traced back when it is questioned three releases later.
- Mixing the specialist's measured claims with the documenter's own inferences without marking whose claim is whose.
- Presenting targets as results — "target Sharpe 1.5" drifting into "achieved Sharpe 1.5" through paraphrase.
- Copying stale artifacts: documenting last month's dashboard JSON while the panels have changed; check the artifact's date against `last_reviewed`.

## Definition of done

- [ ] Every material claim was verified against the source artifact, not a summary, and carries a provenance line: artifact id, date, owning agent.
- [ ] Exact values, units, and periods are transcribed; thresholds and limits appear next to results.
- [ ] All mandatory fields for the artifact's type (quant, ML, QA, security, observability, engineering, business) are present, or the omission is flagged to the owner and blocks the write-up.
- [ ] In-sample and out-of-sample results are separated; averages never stand in for tail metrics; severity ratings are quoted verbatim.
- [ ] Caveats, qualifiers, and claim modality from the artifact survive into the documentation unchanged.
- [ ] Discrepancies between an artifact and its author's summary were reconciled by the owner before publication.
- [ ] Failed and open items are stated plainly alongside successes.
