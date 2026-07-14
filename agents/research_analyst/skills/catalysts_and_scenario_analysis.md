---
name: catalysts-and-scenario-analysis
description: Governs the path-and-probability layer of a thesis, covering a catalyst taxonomy with horizons, bear, base, and bull scenarios each tied to an explicit valuation and probability, expected-value arithmetic with an asymmetry requirement, and pre-mortem falsifiers. Use when a static valuation needs a realization path or when new information forces a scenario review.
---

# Catalysts and Scenario Analysis

This skill governs how the research_analyst converts a static valuation into a path with probabilities: named catalysts with horizons, bear, base, and bull scenarios each tied to an explicit valuation and an explicit probability, expected-value arithmetic with an asymmetry requirement, and a pre-mortem that states in advance what kills the thesis and what evidence would show it early. A value estimate without a path is a number waiting for time to erode its IRR.

## Catalyst taxonomy and horizons

Every thesis names its catalysts by class, each with a typical horizon, a direction, and the observable that confirms it happened.

- Earnings events (zero to three months): quarterly prints, guidance revisions, segment re-disclosures. Frequent but crowded — the market prices the consensus, so the catalyst is the gap between your owner-earnings view and the Street's model, not the print itself.
- Capital-allocation announcements (three to eighteen months): buyback authorizations, dividend initiations, spin-offs, divestitures, debt paydown milestones. Read intent in the proxy and the credit agreement before assuming one is coming.
- Regulatory decisions (six to twenty-four months): drug approvals, antitrust rulings, tariff and rate decisions. Often binary — these force wide scenario spreads and argue for smaller sizing input, never for averaging the outcomes into a single blended target.
- Industry cycle turns (twelve to thirty-six months): capacity exits, inventory normalization, pricing recovery. Slow, but confirmable early through leading indicators — order books, utilization rates, scrappage — which belong in the falsifier list.
- Forced-seller flows (days to weeks): index deletions, fund liquidations, post-spin-off selling by holders barred from the new listing. Price pressure detached from fundamentals; the catalyst is the seller finishing, and float and ownership filings tell you when.

## Building the scenario set

Build at least bear, base, and bull, and tie each to an explicit valuation produced by the valuation_methods skill — no scenario carries a price that was not derived there. The bear case uses stressed owner earnings, trough multiples, and tested covenant headroom; the base case is the central triangulated estimate; the bull case must name its drivers (price, volume, margin, multiple) rather than adding optimism to the base. Assign each scenario an explicit probability; the set sums to 1.0, the base typically carries 50 to 60 percent, and every probability is written down with the reasoning that produced it. A scenario is drivers plus a valuation plus a probability — a price target with none of these is decoration.

## Expected value and the asymmetry requirement

Compute expected value as the probability-weighted sum of scenario valuations and compare it with the current price. Positive expected value is necessary but not sufficient: require a skewed payoff, with upside distance to the probability-weighted favorable outcomes at least twice the downside distance to the bear case at the entry price, and three-to-one when confidence in the probabilities is low. A marginally positive EV built on symmetric outcomes is model noise, not an edge. Probabilities here are judgments and are labeled as judgments; when a probability claim rests on a historical base rate ("issuers that announce this kind of buyback outperform"), that is a statistical claim and is handed to quant_trader for backtest validation, or to ml_engineer when a statistical model is required. The research_analyst never presents an unvalidated frequency as measured fact.

## Pre-mortem discipline

Before publishing, assume the thesis is dead in twenty-four months and write down what killed it. For each cause, record the earliest observable evidence — a specific line item, a KPI, a competitor action, a regulatory docket entry — and how often it will be checked. These falsifiers go into the research note verbatim, so a later reader can audit whether the early warnings were watched or ignored.

## Scenario reviews and project memory

When new information lands — an 8-K, a guidance change, a docket update, a forced-seller event completing — re-run the scenario set rather than patching one number. Record the original scenario set in project memory via save_decision, and record each revision as a new decision that supersedes the old one via supersede_decision; the original is never edited. The superseding chain is the audit trail of what was believed, when, and on what evidence — a quietly edited scenario table destroys exactly the accountability this skill exists to create.

## Common pitfalls

- Positive EV without asymmetry — a near-symmetric payoff clears the EV bar on optimistic inputs alone and evaporates under small probability errors.
- Catalyst-free value theses — cheap can stay cheap for years; without a named path, time is a cost and the IRR decays even when the value estimate is right.
- Decorative probabilities — round numbers assigned after the conclusion was reached invert the method; the probability reasoning must be written before the EV is computed.
- Blending binary outcomes into one target — averaging approval and rejection produces a price that occurs in no world and misleads sizing.
- Editing the original scenario record — revisions supersede in memory; edits erase the audit trail.
- Presenting judged probabilities as measured frequencies — base-rate claims require quant_trader validation before they can be stated as fact.

## Definition of done

- [ ] Each catalyst named with its taxonomy class, horizon, direction, and confirming observable.
- [ ] Bear, base, and bull scenarios each tied to an explicit valuation from valuation_methods, with drivers stated.
- [ ] Probabilities explicit, summing to 1.0, labeled as judgments, with the reasoning recorded.
- [ ] Expected value computed against the current price and the asymmetry requirement checked at entry.
- [ ] Pre-mortem written: each kill cause paired with its earliest observable evidence and a check cadence.
- [ ] Statistical or backtestable claims routed to quant_trader, and statistical-model work to ml_engineer, before being stated as validated.
- [ ] The scenario set saved to project memory, with every revision superseding the prior record rather than editing it.
