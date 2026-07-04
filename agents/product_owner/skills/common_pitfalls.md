## Common pitfalls


- Solutioning in the problem statement. Describe the pain; let engineering and architecture choose the how.
- Acceptance criteria that only describe the happy path. Boundary and failure paths are where defects live.
- Adjective requirements ("fast", "intuitive", "secure"). Replace every adjective with a number or a checkable condition.
- Silent scope creep by editing acceptance criteria mid-sprint instead of running the scope-change protocol.
- A Must-have list that exceeds capacity, guaranteeing a slip.
- Stories split by technical layer instead of by user-visible behavior.
- Success metrics with a target but no baseline or measurement window, which makes "success" unfalsifiable.
- Omitting guardrail metrics, so a feature wins on its primary metric while quietly regressing latency, cost, or error rate.
