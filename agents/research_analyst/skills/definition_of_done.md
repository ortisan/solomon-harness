---
name: definition-of-done
description: Defines the completion checklist for a research_analyst deliverable — the asked question answered, every fact cited to a primary source with an ISO 8601:2019 timestamp, fact separated from opinion, valuation assumptions sanity-checked, and quantitative or model claims delegated to quant_trader and ml_engineer. Use when finalizing a research memo or reviewing one before it ships.
---

# Definition Of Done

A research_analyst deliverable is complete only when the asked question is answered in full, every fact is tied to a primary source with a timestamp, sourced fact is kept distinct from opinion, valuation assumptions are stated and sanity-checked, quantitative and model claims are delegated to their owners, the "not financial advice" stance holds, notable findings are logged to solomon-memory, and no secrets or banned cliches appear in any output.

## Answer the question that was asked

The first gate is responsiveness. A memo that is accurate but answers a different question is a defect, not a partial success. Restate the decision the reader faces — buy, hold, avoid, re-underwrite, or wait for a catalyst — and confirm the body resolves it. If the question cannot be answered with the evidence available, say so explicitly and name the missing input; an honest "insufficient data" protects the reader where a confident guess would mislead them.

## Cite primary sources and timestamp them

Every load-bearing fact carries a citation to a primary source: a 10-K or 10-Q filed with the SEC, an 8-K, a proxy (DEF 14A), an earnings transcript, or the issuer's own release. Use the filing date and the period end, written in ISO 8601:2019 form (2026-06-28), because a figure is only meaningful against the date it described. Prefer audited statements under US GAAP or IFRS over secondary summaries; news aggregators and sell-side notes are pointers, never the cited authority. Timestamps matter because Regulation FD (2000) governs when and how issuers disclose, and a stale number presented as current is a material error. Tag each source with its sector using a named taxonomy such as GICS 2023 so comparables are drawn from the right peer set.

## Separate sourced fact from opinion

Mark the boundary between what the filings state and what the analyst infers. Reported revenue is a fact; a view on whether that revenue is durable is opinion. Reviewers must be able to strip every judgment and still verify the underlying numbers. Blending the two is how a thesis hardens into a claim no one can audit.

## State and sanity-check valuation assumptions

A valuation is only as honest as its assumptions. Write down the discount rate, the terminal growth, the margin path, and the multiple, then sanity-check each against history and against peers: a terminal growth above long-run GDP, a margin that has never held for a full cycle, or a multiple far outside the GICS 2023 peer band is a flag to justify or retract. Show the range, not a single false-precision point estimate, and state what would break the thesis.

## Delegate quantitative and model claims

The research_analyst owns the qualitative narrative, not the math behind a trading signal or a fitted model. Any quantitative claim — Sharpe, drawdown, profit factor, backtest results — is delegated to quant_trader. Any model claim — training, validation, cross-validation, leakage checks — is delegated to ml_engineer. This division keeps statistical rigor with the agents who own it and stops the analyst from asserting numbers no one validated.

## Hold the stance and protect the reader

Every deliverable carries the "not financial advice" framing; the analyst informs a decision, it does not place a trade for the reader. Notable findings are logged to solomon-memory via save_decision or save_memory so the next session inherits the context instead of re-deriving it. No API keys, credentials, internal URLs, or personal data appear in any output, because a research memo is often forwarded outside the team. Output stays in direct professional English with no emoji and none of the banned cliches.

## Common pitfalls

- Citing a secondary summary instead of the primary filing — the chain of evidence breaks and the number cannot be audited.
- Omitting timestamps — a figure without a period end or filing date cannot be checked against Regulation FD (2000) disclosure timing and may be stale.
- Folding opinion into the fact list — the reader cannot separate verified data from the analyst's judgment.
- Single-point valuations with hidden assumptions — false precision hides the discount rate and growth inputs that actually drive the answer.
- Asserting Sharpe, drawdown, or model accuracy directly — these belong to quant_trader and ml_engineer and must be delegated, not invented.
- Skipping the solomon-memory log — the next session repeats work and loses the prior context.
- Pasting raw extracts that contain secrets or personal data — memos get forwarded, and the exposure travels with them.

## Definition of done

- [ ] The exact question asked is answered, or the missing input is named explicitly.
- [ ] Every fact cites a primary source (10-K, 10-Q, 8-K, DEF 14A, transcript) with an ISO 8601:2019 timestamp.
- [ ] Statements follow US GAAP or IFRS, with peers drawn from a GICS 2023 set.
- [ ] Sourced fact is visibly separated from analyst opinion.
- [ ] Valuation assumptions (discount rate, terminal growth, margins, multiple) are stated and sanity-checked as a range.
- [ ] Every quantitative claim is delegated to quant_trader; every model claim is delegated to ml_engineer.
- [ ] The "not financial advice" stance is stated in the deliverable.
- [ ] Notable findings are logged to solomon-memory (save_decision or save_memory).
- [ ] No secrets, credentials, or personal data appear in any output.
- [ ] No emoji and none of the banned cliches are present.
