---
name: moat-and-qualitative-assessment
description: Governs the evidence-based assessment of durable competitive advantage, covering the five moat sources with concrete tests, ROIC-above-WACC confirmation across a cycle, moat trajectory, and management quality read from the capital-allocation record. Use when judging whether a business can defend its returns or when a thesis rests on a claimed moat.
---

# Moat and Qualitative Assessment

This skill governs how the research_analyst judges durable competitive advantage: a moat claim is accepted only when a named source of advantage passes a concrete evidence test and the returns data confirm it, and the conclusion is written as a falsifiable, sourced, timestamped statement rather than a narrative. Story-first moat analysis is the most common failure mode in qualitative research, so every claim here is anchored to a number someone else could check.

## The five moat sources and their evidence tests

- Intangible assets. A brand counts only when it moves price: demonstrate a sustained price premium over a functionally comparable product in the same channel, or a record of list-price increases without share loss. Patents count when the expiry schedule in the 10-K exhibits protects current cash flow, not past products. Regulatory licenses count when new issuance is genuinely restricted and the restriction is documented.
- Switching costs. Test with retention data: gross churn, net revenue retention (above 110 percent is the working bar for enterprise software), renewal and attach rates, deposit duration for banks. Corroborate with the mechanics of migration — data gravity, integration depth, retraining cost — evidenced in customer-tenure disclosures or case studies, never merely asserted.
- Network effects. Test whether the product measurably improves with each additional user: cohort engagement rising with scale, take rates holding or rising as volume grows, high multi-homing cost. A large user count with flat per-user engagement is scale, not a network effect.
- Cost advantage. Requires unit-cost evidence against named peers — production cost per unit, cost per transaction, distribution density — plus an identified mechanism (scale, proprietary process, location, resource access). A cost gap with no mechanism is usually an accounting artifact or a cycle effect and should be assumed temporary.
- Efficient scale. A market that profitably supports only one or two operators (pipelines, rail spurs, niche exchanges): show that historical entry attempts destroyed returns for entrant and incumbent alike, and that the addressable market is too small to reward a rational second entrant.

## Quantitative confirmation

Narrative alone confirms nothing; the returns record must agree. Compute ROIC as NOPAT over invested capital (operating approach, goodwill included and excluded, both disclosed) and compare it with the WACC built in valuation_methods. The bar: ROIC above WACC sustained across a full business cycle — at least seven to ten years including a downturn. A spread of two to three points sustained is consistent with a narrow moat; five points or more with an identified source supports a wide one. Check gross-margin stability over the same window: a stable or rising gross margin with low variance versus peers indicates the advantage absorbs shocks. Pricing power must be demonstrated, not presumed: find actual past price increases in the MD&A or earnings-call transcripts and verify volumes held. A spread that appeared only in the last two years, or depends on one peak year, leaves the moat unproven.

## Trajectory and disconfirming evidence

Classify the moat as widening, stable, or eroding, each with direction evidence: the trend of the ROIC-WACC spread, market-share movement, customer-acquisition-cost trend, entrant activity, and substitute technology. Then search for disconfirmation deliberately: read the strongest competitor's filings, decompose the gross margin for mix effects masking erosion, and look for cohort or churn data that contradicts the retention story. A moat verdict written without stating what would disprove it is an opinion, not a verdict.

## Management quality through the capital-allocation record

Grade management by what they did with the cash, not by how they sound on calls.

- Buybacks versus price paid: compare the volume-weighted repurchase prices in the share-repurchase table of the 10-Q and 10-K with the intrinsic-value range from valuation_methods. Repurchasing below intrinsic value creates per-share value; buying at peaks and issuing at troughs destroys it.
- M&A track record: goodwill impairments are the public scorecard of past deals. Check post-deal ROIC dilution and whether "synergies" ever appeared in segment margins. Serial acquirers get their organic growth separated from acquired growth before any quality conclusion.
- Incentive alignment: read the DEF 14A proxy statement. Compensation tied to ROIC, per-share value, or economic profit aligns with owners; compensation tied to revenue growth or adjusted EBITDA alone rewards empire building. Note insider ownership and any related-party arrangements.

## Writing the verdict

The output is a falsifiable statement tied to numbers, for example: "Narrow moat from switching costs: net revenue retention 118 percent (FY2025 10-K, retrieved 2026-07-14), ROIC 14 percent against a 9 percent WACC over 2016-2025; falsified if NRR prints below 105 percent for two consecutive years or the ROIC spread turns negative outside a recession." Every figure carries a source and an ISO 8601:2019 retrieval timestamp per the research_sources_playbook, and the verdict is recorded in project memory via save_decision so later sessions inherit it.

## Common pitfalls

- Accepting brand awareness as a moat — many famous brands cannot price above private-label peers; only a demonstrated price premium counts.
- Confusing scale with network effects — size without rising per-user value is an efficiency story that a funded entrant can replicate.
- Calling a cyclical peak a moat — an ROIC spread that exists only in boom years disappears exactly when the valuation needs it.
- Grading management on communication polish — the repurchase table, the goodwill line, and the proxy are the record; the narrative is marketing.
- Publishing a verdict without a falsifier — an unfalsifiable moat claim cannot be revisited honestly when evidence turns.
- Skipping the strongest competitor's filings — a moat is relative, and the disconfirming data usually lives in the rival's numbers.

## Definition of done

- [ ] Each claimed moat source named and passed its concrete evidence test with cited data.
- [ ] ROIC computed and compared with WACC over at least seven years spanning a downturn, with the spread stated.
- [ ] Gross-margin stability measured against peers and pricing power evidenced by actual past price increases with volumes held.
- [ ] Trajectory classified as widening, stable, or eroding, with direction evidence and a deliberate disconfirmation search documented.
- [ ] Capital allocation graded: repurchase prices versus the intrinsic range, M&A outcomes via goodwill and post-deal ROIC, and proxy incentive metrics read.
- [ ] The moat verdict written as a falsifiable statement tied to numbers, fully sourced with ISO 8601:2019 timestamps, and saved to project memory.
