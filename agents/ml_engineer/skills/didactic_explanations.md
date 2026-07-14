---
name: didactic-explanations
description: Governs how models, metrics, and findings are explained to non-specialist decision-makers, translating metrics into decision language with natural frequencies and contextual scales. Use when writing a stakeholder-facing explanation of a model, metric, or finding, or reviewing one for jargon or misleading framing.
---

# Didactic Explanations

This skill governs how models, metrics, and findings are explained to non-specialist decision-makers. Simplify the language, never the truth: the listener should leave knowing what the model does, how well, how sure we are, and where it fails — and nothing they leave with should have to be walked back later.

## Translate metrics into decision language

Lead with what the number means for the decision, then name the metric:

- "The model catches 85 of every 100 customers who actually churn" first; "recall is 0.85" second. State the price in the same breath: "to do that, it also flags 30 who would have stayed."
- Use natural frequencies, not chained percentages (Gigerenzer's rule): "12 in 1,000" lands where "1.2 percent" and "a 20 percent relative increase" mislead. Percentage-of-percentage phrasing ("a 15 percent improvement in precision") is banned in favor of the counts it implies.
- Present the confusion matrix as counts per 1,000 cases with the cost of each cell attached, so the trade-off is readable without knowing the words "precision" or "recall".

## Provide contextual scales

A number without a scale is noise to a non-specialist. Anchor every headline figure:

- State whether the value is strong for this problem class: a Sharpe ratio of 1.8 is excellent for a daily equity strategy and unremarkable for market-making; AUC 0.75 is strong for churn and alarming for fraud detection where 0.95 is table stakes.
- Give comparison anchors the listener already trusts: the naive baseline, the current system, and where available, human performance on the same task.
- Prefer "twice as many correct flags as the current rules" over any raw metric delta.

## The "so what" rule

Every chart and every finding ends with one explicit line: why this matters and which decision it changes. "Churn concentrates in month two — so the retention budget moves from month six to month two" is the deliverable; the chart is its evidence. A finding with no stated decision consequence gets cut from the summary, not padded.

## Explaining without distortion

The simplifications that flip into falsehoods, and their honest replacements:

- Feature importances and SHAP values describe association within the model, not causation in the world. Say "customers with short tenure are flagged more", never "short tenure causes churn". If the stakeholder will act as if it were causal, say explicitly that this needs a designed test.
- Report uncertainty as ranges in the same units as the decision: "we expect 12 to 18 percent churn in this segment", not "15 percent" with false precision, and not a bare "plus or minus the standard error".
- The failure modes travel with the headline: state where the model is weak (worst segments from the error analysis) in the same summary that states the average, so the first surprise does not arrive in production.
- Analogies are allowed one at a time and must come with their breaking point: "it works like a credit score — but unlike a credit score, it drifts as behavior changes, so it is re-checked monthly."
- Never present a point forecast for an inherently distributional outcome; show the range and the odds the decision-maker actually faces.

## Layered depth

Structure every explanation in three layers so each audience reads to its own depth: one sentence (the decision-ready claim), one paragraph (mechanism and main caveat, jargon-free), and an appendix (formal definitions, formulas, and references for the technical reviewer). Intuition precedes formalism everywhere: a formula may appear only after its meaning has been stated in words and, where possible, with a worked example using the reader's own quantities. Vocabulary discipline: any term the listener would have to look up either gets a five-word gloss inline or gets cut.

## Common pitfalls

- Reporting "recall 0.85" without the false-positive price, letting the listener assume it is free.
- Relative risk without absolute base rates ("doubles the risk" of something affecting 2 in 10,000).
- Presenting SHAP or importance rankings as causal levers for intervention.
- A Sharpe, AUC, or R2 quoted with no statement of what is good in this context.
- Point estimates delivered without ranges, then treated as commitments downstream.
- An analogy left running past its validity, quietly teaching a wrong mental model.
- Simplifying by omitting the known failure modes rather than by clarifying the language.
- Charts sent without a "so what" line, delegating interpretation to the least-informed reader.

## Definition of done

- [ ] Every headline metric translated into decision language with natural frequencies and its cost stated alongside its benefit.
- [ ] Every number anchored to a contextual scale: baseline, current system, and what counts as strong for this problem class.
- [ ] Every chart and finding carries an explicit one-line decision consequence.
- [ ] Associational findings labeled as such; no causal phrasing without a designed test behind it.
- [ ] Uncertainty expressed as ranges in decision units; failure modes and worst segments stated with the headline.
- [ ] Explanation layered: one sentence, one paragraph, technical appendix; formulas only after the intuition.
- [ ] A domain-naive reader could restate the conclusion correctly, and a technical reviewer finds nothing to walk back.
