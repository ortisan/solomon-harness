---
name: financial-statement-quality-and-forensics
description: Governs the earnings-quality screen run before any valuation, covering accrual-versus-cash-flow divergence, revenue recognition red flags, expense capitalization games, balance-sheet stress, and Beneish M-score and Altman Z triage. Use when reading a new filing or adjusting reported figures to owner earnings before they enter a DCF or a multiple.
---

# Financial Statement Quality and Forensics

This skill governs the earnings-quality screen the research_analyst runs before any valuation: reported figures are claims to be tested against cash flow, footnotes, and segment data, and only the adjusted owner-earnings figure — never the headline number — is allowed into a DCF or a multiple. A valuation built on distorted inputs is precisely wrong, so this screen always precedes the work in valuation_methods.

## Accruals versus cash flow

The strongest single signal is divergence between reported earnings and the cash that backs them. Compute cash conversion — cash flow from operations divided by net income — on a trailing-twelve-month basis; a ratio persistently below 0.8 for two or more years means earnings are being manufactured by accruals faster than the business collects cash, and demands an explanation before anything else. Compute the accrual ratio in the Sloan (1996) form: net income minus cash flow from operations minus cash flow from investing, divided by average total assets. Readings above +10 percent of assets sit in the historically worst-performing decile and are a standing flag. Track the three-year growth of net income against the three-year growth of operating cash flow; when the earnings line pulls away from the cash line, find the balance-sheet account absorbing the difference.

## Revenue recognition red flags

Receivables growing faster than revenue for two or more consecutive quarters is the classic pull-forward signature. Compute days sales outstanding per quarter (receivables divided by quarterly revenue, times 91) and read the trend, not the level. Channel-stuffing markers: quarter-end shipment surges described in the MD&A, newly extended payment terms, rising returns and rebate reserves, and inventory building at disclosed distributors. Under ASC 606 and IFRS 15, watch contract assets (unbilled receivables) growing faster than billed revenue, late upward revisions to margin assumptions on percentage-of-completion contracts, and unapproved change orders or claims carried in backlog — each books profit management has not yet earned. Deferred revenue shrinking while reported revenue grows means the company is eating its backlog.

## Expense games

Capitalization versus expensing moves today's cost into tomorrow's amortization: compare capitalized software development, contract, and customer-acquisition costs as a share of revenue against two or three named peers, and treat a rising share with no business-model change as earnings management. One-time items that recur are operating expenses: a restructuring charge appearing in three consecutive years gets rebuilt into a three-to-five-year average and put back into the cost base. Track the spread between GAAP and adjusted EPS over five years; a widening spread means the adjustments are becoming the business. Depreciation games — useful-life extensions, falling depreciation relative to gross PP&E — lift earnings without producing cash and reverse as maintenance capex eventually catches up.

## Balance-sheet stress

Working-capital swings can fake a strong cash quarter: operating cash flow driven by a one-quarter payables stretch, receivables factoring, or a supply-chain finance program (disclosed under ASU 2022-04 since 2023) reverses. Inventory growing faster than cost of goods sold flags either demand weakness or obsolete stock awaiting a write-down. Hunt off-balance-sheet obligations in the commitments and contingencies note: purchase obligations, guarantees, receivables sold with recourse, unconsolidated entities. Pull covenant definitions from the credit-agreement exhibits and compute headroom: less than half a turn of net-debt-to-EBITDA headroom, or interest coverage within 20 percent of the floor, means the equity behaves like an option, and the valuation must say so. Map the maturity wall against unlevered free cash flow.

## Screens as triage, never verdicts

The Beneish M-score (eight variables; a score above -1.78 flags a manipulator-like profile, driven mainly by DSRI, AQI, SGI, and TATA) and the Altman Z-score (below 1.81 distress zone, above 2.99 safe in the original manufacturing form; use the Z''-score for non-manufacturers) are triage tools. A failing score directs which footnotes to read first; it never concludes fraud. A passing score clears nothing — both models miss manipulators routinely, so the footnote reading below is mandatory either way.

## Footnotes, segments, and the owner-earnings rule

Mandatory reading on every pass: the revenue-recognition policy note, related-party transactions, commitments and contingencies, the segment note (a stable consolidated margin can hide an eroding core segment cross-subsidized by a peaking one), auditor changes, and the critical audit matters required in US filings since 2019. Then apply the rule that closes this skill: reported figures are adjusted to owner earnings before entering any valuation. Normalize recurring "one-time" charges into the cost base, expense aggressive capitalization, subtract maintenance capex (estimated from depreciation and management disclosure when the split is not given), and reverse unsustainable working-capital benefits. Document every adjustment line by line with its source and an ISO 8601:2019 retrieval timestamp per the research_sources_playbook; the owner-earnings figure is what valuation_methods consumes.

## Common pitfalls

- Valuing headline EPS without an earnings-quality pass — the valuation inherits every distortion in the inputs and multiplies it through a multiple or a terminal value.
- Treating one flagged metric as proof of fraud — a growing company legitimately builds receivables and accruals; the flag directs deeper reading, and only corroboration across accounts concludes.
- Using M-score or Z-score as verdicts — both are probabilistic screens with known false positives and misses; they rank reading priority, nothing more.
- Reading only consolidated statements — segment disclosures are where a deteriorating core hides behind a strong division.
- Comparing US GAAP and IFRS figures unadjusted — development-cost capitalization under IAS 38 alone can move margins several points between otherwise identical firms.
- Skipping the credit-agreement exhibits — covenant proximity changes the equity from a claim into an option, and no income-statement metric reveals it.

## Definition of done

- [ ] Cash conversion and the Sloan accrual ratio computed over at least three years, with divergences explained by named accounts.
- [ ] DSO, contract-asset, and deferred-revenue trends checked against revenue growth for pull-forward signatures.
- [ ] Capitalization policy benchmarked against named peers; recurring "one-time" charges rebuilt into the operating cost base.
- [ ] Off-balance-sheet obligations quantified from the footnotes; covenant headroom and the maturity wall computed from filing exhibits.
- [ ] Beneish M-score and Altman Z computed and used only to prioritize footnote reading.
- [ ] Revenue-policy, related-party, segment, and critical-audit-matter notes read and summarized.
- [ ] Owner-earnings adjustment documented line by line, each with a source URL, document date, and ISO 8601:2019 retrieval timestamp.
- [ ] An earnings-quality verdict (clean, adjusted, or unreliable) recorded before any valuation work begins.
