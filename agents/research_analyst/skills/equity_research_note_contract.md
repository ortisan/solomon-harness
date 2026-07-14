---
name: equity-research-note-contract
description: Defines the research_analyst's standard output artifact, covering the required sections of an equity research note, the evidence bar of sourced and timestamped figures, the value range with margin of safety, and the handoff lines to quant_trader, ml_engineer, and the strategy agents. Use when writing, reviewing, or consuming a research note, or when routing a claim it contains.
---

# Equity Research Note Contract

This skill governs the research_analyst's standard output artifact: every completed piece of company research is delivered as a research note with fixed sections in a fixed order, an evidence bar of sourced and timestamped figures, a value range instead of a point target, and explicit handoff lines that route each claim to the agent that owns its validation. The note is a contract with its consumers — a strategy agent, a reviewer, or a future session — and a note missing a section is incomplete work, not a stylistic choice.

## Required sections, in order

1. Thesis in three sentences: what the market believes, why it is wrong, and what closes the gap. If it cannot be said in three sentences, the thesis is not yet understood.
2. Business description: what is sold, to whom, and at what unit economics, with the revenue mix by segment and geography taken from the segment note of the latest 10-K, not from an aggregator profile.
3. Earnings-quality verdict: clean, adjusted, or unreliable, imported from financial_statement_quality_and_forensics, with the owner-earnings bridge showing each adjustment from reported figures.
4. Moat verdict: none, narrow, or wide, plus trajectory (widening, stable, eroding), imported from moat_and_qualitative_assessment, together with its falsifier.
5. Valuation triangulation: DCF, relative multiples, and sum-of-the-parts per valuation_methods, converging on a value RANGE with the sensitivity table, plus the margin of safety at the current price. A single point target fails the contract.
6. Scenario table: bear, base, and bull with explicit probabilities summing to 1.0, the valuation each implies, the expected value, and the asymmetry ratio, per catalysts_and_scenario_analysis.
7. Catalysts with horizons: each with its taxonomy class, expected window, and the observable that confirms it happened.
8. Risks and falsifiers: the pre-mortem output — what kills the thesis and the earliest evidence that would show it, with a check cadence.
9. Position recommendation with sizing input: direction, conviction tier, the asymmetry ratio, and liquidity constraints such as average daily volume. The note supplies sizing inputs; it never sets the position size — that decision belongs to the strategy owner consuming the note.
10. Sources with access dates: every figure in the note mapped to a source URL, document date, ISO 8601:2019 retrieval timestamp, and credibility tier per the research_sources_playbook.

## The evidence bar

Every number in the note is sourced and timestamped, with no exceptions for "well-known" figures. Primary filings outrank aggregators: a figure that exists in a 10-K, 10-Q, or 8-K is cited from SEC EDGAR itself, not from a data vendor or a news recap, because aggregators drop footnotes and restatements. Financial figures state their accounting basis (US GAAP or IFRS) and period end; non-GAAP figures appear only next to their reconciliation. Macro inputs cite the FRED series ID or the Treasury observation date. A note containing an unsourced number is returned for repair, not published with a caveat.

## Handoff lines

The note routes claims instead of overreaching, and says so explicitly in the text:

- Any backtestable or statistically validated claim — expected returns, hit rates, factor exposures, historical base rates — goes to quant_trader, who owns the testing harness. Until quant_trader confirms it out of sample, the note labels the claim a forward judgment, never a validated result.
- Any statistical model — forecasting, classification, anything beyond arithmetic on filed figures — goes to ml_engineer, and the note records the request rather than an improvised model output.
- Strategy construction that consumes the note — portfolio inclusion, position sizing, entry and exit rules — goes to long_run_strategist or swing_trader. The note is their input; its recommendation section feeds their process and does not preempt it.

## Recording in project memory

The note's verdicts — earnings quality, moat, value range, and recommendation — are recorded in project memory via save_decision, and the note itself via save_memory, so the next session resumes from the note rather than reconstructing it. When new information changes a verdict, the revision is written as a new record that supersedes the old one via supersede_decision; the original stays intact as the audit trail. A note that lives only in a chat transcript has not been delivered.

## Common pitfalls

- Publishing a point target instead of a range — a single number projects precision the inputs cannot support and hides the sensitivity that drives the decision.
- A thesis section that runs past three sentences — length there signals the mispricing has not actually been isolated.
- Valuing before the earnings-quality verdict — a valuation on unadjusted reported figures inherits every distortion the forensics skill exists to catch.
- Citing an aggregator when the primary filing is available — the recap can silently omit the restatement or footnote that flips the verdict.
- Setting a position size inside the note — sizing belongs to the strategy owner; the note that dictates size collapses the boundary between research and portfolio construction.
- Skipping the memory write — an unrecorded verdict cannot be superseded, audited, or resumed, and the next session repeats the work.

## Definition of done

- [ ] All ten sections present in the fixed order, none empty and none merged.
- [ ] The thesis is exactly three sentences covering belief, error, and gap-closer.
- [ ] Earnings-quality and moat verdicts imported from their skills, each with its falsifier attached.
- [ ] The valuation is a range with a sensitivity table and a stated margin of safety at the current price.
- [ ] The scenario table's probabilities sum to 1.0 and the asymmetry ratio is stated.
- [ ] Every figure carries a source URL, document date, ISO 8601:2019 retrieval timestamp, and tier, with primary filings preferred over aggregators.
- [ ] Handoff lines present: unvalidated statistical claims to quant_trader, model work to ml_engineer, strategy construction to long_run_strategist or swing_trader.
- [ ] Verdicts and the note recorded in project memory, with revisions superseding rather than editing prior records.
