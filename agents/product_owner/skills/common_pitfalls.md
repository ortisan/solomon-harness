---
name: common-pitfalls
description: Lists the recurring product-definition failures a reviewer must reject before a PRD or its stories ship - solutioning, happy-path-only criteria, adjective requirements, silent scope creep, over-capacity Must lists, and unfalsifiable metrics. Use when reviewing a PRD or story set.
---

# Product Owner Common Pitfalls

The recurring product-definition failures a reviewer must reject before a PRD or its stories leave the product_owner. Each bullet names the failure and why it costs the delivery; the closing checklist is the gate proving a deliverable avoids them.

## Common pitfalls


- Solutioning in the problem statement. Describe the pain; let engineering and architecture choose the how.
- Acceptance criteria that only describe the happy path. Boundary and failure paths are where defects live.
- Adjective requirements ("fast", "intuitive", "secure"). Replace every adjective with a number or a checkable condition.
- Silent scope creep by editing acceptance criteria mid-sprint instead of running the scope-change protocol.
- A Must-have list that exceeds capacity, guaranteeing a slip.
- Stories split by technical layer instead of by user-visible behavior.
- Success metrics with a target but no baseline or measurement window, which makes "success" unfalsifiable.
- Omitting guardrail metrics, so a feature wins on its primary metric while quietly regressing latency, cost, or error rate.

## Definition of done

- [ ] The problem statement describes the pain with no solution language; the "how" is left to engineering and architecture.
- [ ] Every story's Given-When-Then criteria cover at least one boundary and one failure path, not only the happy path.
- [ ] No adjective requirement survives: every "fast", "intuitive", or "secure" has become a number or a checkable condition.
- [ ] Any mid-sprint change to acceptance criteria went through the scope-change protocol and was logged with `save_decision`.
- [ ] The Must-have list fits the capacity engineering sized; overflow was renegotiated openly, not absorbed.
- [ ] Every story is a vertical slice of user-visible behavior; no frontend/backend layer splits remain in the backlog.
- [ ] The primary success metric carries a baseline, a target, and a measurement window, with guardrail metrics for latency, cost, and error rate listed beside it.
