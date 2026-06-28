## The PRD Contract template


Every PRD you publish must contain these sections in this order. Omit nothing; mark a section "N/A" with a one-line reason instead of deleting it.

1. Problem statement. The user pain in one paragraph. Who hurts, when, how often, and what it costs them. No solution language here.
2. Goals and non-goals. 3-5 measurable goals. An explicit non-goals list so reviewers know what you deliberately excluded.
3. Success metrics. One primary metric (the north-star for this change) plus 1-3 guardrail metrics that must not regress. Each metric has a baseline, a target, and a measurement window. Example: "Checkout completion 71 percent -> 78 percent within 4 weeks; p95 latency guardrail must stay under 400 ms."
4. Personas and context. The specific user(s) and the trigger situation. Link to research or prior decisions in project memory.
5. User stories. The backlog for this PRD (format below).
6. Acceptance criteria. Per story, in Given-When-Then (format below).
7. Scope boundaries. In-scope list, out-of-scope list, and explicit assumptions and dependencies.
8. Constraints and non-functional requirements. Performance budgets, security, compliance, accessibility, data retention. State numbers, not adjectives.
9. Open questions and risks. Each with an owner and a needed-by date.
10. Rollout and acceptance. Release gating, feature-flag plan, and the single sentence that defines "done shipped."

Keep the PRD to the smallest size that removes ambiguity. A 2-page PRD that engineering can build beats a 20-page one they skim.
