---
name: common-pitfalls
description: Catalogs the reasoning errors that corrupt fundamental research — anchoring, confirmation bias, recency bias, survivorship bias, base-rate neglect, narrative over numbers, valuation traps, stale data, and overfitting — with a written countermeasure for each. Use when drafting a research memo, sizing conviction, or sanity-checking a valuation before it reaches a recommendation.
---

# Common Analytical Pitfalls

This skill catalogs the recurring reasoning errors that corrupt fundamental investment research and gives the research_analyst a written countermeasure for each one before any conclusion reaches a recommendation.

Fundamental research produces a judgment under uncertainty, and that judgment is destroyed far more often by predictable distortions in how evidence is weighed than by missing data. For every pitfall below, name the error in the research file, state the damage, and record the discipline that neutralizes it as an explicit step. Treat the CFA Institute Code of Ethics and Standards of Professional Conduct (2014 revision) and Regulation FD (SEC, 2000) as the conduct floor: reason from primary, fairly disclosed information, and document the diligence basis for every recommendation.

## Anchoring

The error: fixing on the first number seen  -  last quarter's price target, the IPO valuation, sell-side consensus  -  and adjusting too little from it. The damage: estimates cluster around an irrelevant reference instead of intrinsic value, so the thesis silently inherits someone else's stale frame. The discipline: build the valuation bottom-up from primary filings (10-K, 10-Q under US GAAP, or the IFRS equivalent) before reading any external target, then log the anchor-free figure first and the consensus second so the divergence is visible and defended.

## Confirmation bias

The error: searching for evidence that supports the held view and discounting what contradicts it. The damage: the model hardens around a story the market may already have priced, and disconfirming facts arrive too late. The discipline: write the bear case and a falsifiable kill criterion before sizing conviction. State, in advance, the specific metric move (for example, gross margin contracting more than 200 bps for two consecutive quarters) that would force the thesis to be retired.

## Recency bias

The error: extrapolating the most recent quarter or the latest macro headline as if it were the new baseline. The damage: cyclical peaks look like permanent growth and troughs look like terminal decline. The discipline: anchor every trend to a full cycle of history, normalize margins across at least one downturn, and timestamp every input in ISO 8601:2019 form (YYYY-MM-DD) so the age of each data point is unambiguous.

## Survivorship bias

The error: studying only the companies, funds, or strategies that still exist, ignoring the ones that failed or delisted. The damage: base rates for success are overstated and the true distribution of outcomes is hidden. The discipline: source samples that include dead and acquired names, and state explicitly when a peer set excludes failures.

## Base-rate neglect

The error: judging a specific case (this turnaround, this acquirer) on its vivid narrative while ignoring how the reference class usually performs. The damage: low-probability outcomes are treated as likely. The discipline: state the outside view first  -  the historical hit rate for the category  -  then adjust for case-specific evidence, never the reverse.

## Narrative over numbers

The error: letting a compelling management story or a clean slide deck substitute for the cash-flow arithmetic. The damage: qualitative conviction outruns what the financials can support. The discipline: every qualitative claim must map to a line in the model; if a moat cannot be traced to pricing power, returns on invested capital, or unit economics, it does not enter the valuation.

## Valuation traps

The error: hiding the entire result in assumptions the model is least able to defend  -  a terminal value that is 70 to 85 percent of enterprise value, a perpetual growth rate above long-run nominal GDP, or steady-state margins above any the company has ever earned. The damage: precision masks a guess, and small input drift swings fair value by double digits. The discipline: cap perpetual growth at or below long-run nominal GDP, cross-check the implied exit multiple against history, sensitize the two or three inputs that move the answer most, and reconcile any margin expansion to a named operating driver. Where borrowed capital matters, model the debt load and debt-to-equity path explicitly rather than burying gearing in the discount rate.

## Stale or unsourced data

The error: carrying numbers whose origin or vintage nobody can reconstruct. The damage: an audit cannot reproduce the conclusion, and one wrong cell propagates everywhere. The discipline: every figure carries a source citation and a retrieval date; classify each name to its GICS 2023 sector so comparables are consistent; reject any input that cannot be traced to a filing, transcript, or named dataset.

## Overfitting and data-mining

The error: torturing the data until a backtested pattern appears, then presenting the survivor as a finding. The damage: in-sample fit collapses out of sample and capital is committed to noise. The discipline: form the hypothesis before touching the test set, and hand any statistical or signal claim to the quant_trader and ml_engineer agents for out-of-sample and cross-validation checks with zero look-ahead. The research_analyst does not ship a quantitative edge that has not survived their review.

## Common pitfalls

- Anchoring to an external target: it imports a stale frame; value the business before reading consensus.
- Confirmation bias: it hides disconfirming facts; pre-commit a written bear case and kill criterion.
- Recency bias: it mistakes a cycle phase for a baseline; normalize across a full cycle.
- Survivorship bias: it inflates success base rates; sample dead and delisted names too.
- Base-rate neglect: it overweights vivid stories; state the outside view first.
- Narrative over numbers: it lets a deck replace arithmetic; tie every claim to a model line.
- Valuation traps: terminal value and rosy margins bury the answer in soft inputs; cap growth and sensitize.
- Stale or unsourced data: it blocks reproduction; cite source and ISO 8601:2019 date on every figure.
- Overfitting: it ships noise as edge; hand signals to quant_trader and ml_engineer for out-of-sample review.

## Definition of done

- [ ] Each material assumption is stated bottom-up from primary filings, with the consensus shown separately.
- [ ] A falsifiable bear case and a numeric kill criterion are written before conviction is sized.
- [ ] Margins and growth are normalized across at least one full cycle, not the latest quarter.
- [ ] Peer and sample sets include failed, delisted, or acquired names, and the GICS 2023 classification is recorded.
- [ ] Terminal value share of enterprise value is disclosed; perpetual growth is at or below long-run nominal GDP; the top inputs are sensitized.
- [ ] Borrowed-capital exposure is modeled as debt load and debt-to-equity, not folded silently into the discount rate.
- [ ] Every figure carries a source citation and an ISO 8601:2019 retrieval date; no unsourced inputs remain.
- [ ] Any quantitative signal has passed out-of-sample and cross-validation review by quant_trader and ml_engineer with no look-ahead.
- [ ] The diligence basis meets the CFA Institute Standards (2014) and Regulation FD (2000) conduct floor.
