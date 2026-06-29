# Research Sources Playbook

The research_analyst answers any investment question by stating it precisely, reading primary sources before any commentary, ranking every source by credibility, and writing only claims that carry a citation and an ISO 8601:2019 retrieval timestamp.

## The method

Run the same disciplined sequence for every question, whether it is "can this issuer service its debt load" or "what growth is the market already pricing in":

1. Define the question. Reduce a vague prompt to a falsifiable claim with a horizon and a unit. "Is the company healthy" becomes "Did trailing-twelve-month free cash flow cover interest expense and dividends in the last four 10-Q filings." Name the metric, the period, and the threshold that decides the answer before you open a single source.
2. Go to primary sources first. The originating document outranks anyone describing it. For a U.S. issuer that means the filing itself on SEC EDGAR, not a news recap of the filing. Pull the exact line item, note the page or XBRL tag, and quote the number rather than paraphrasing it.
3. Tier source credibility. Tag each source Tier 1, Tier 2, or Tier 3 (defined below) before it informs a conclusion. A Tier 3 claim never moves a thesis on its own; it only flags something to confirm against a higher tier.
4. Synthesize with citations and timestamps. Every assertion in the output links to the source URL, the document date, and the retrieval timestamp. Financial figures cite their accounting basis (US GAAP or IFRS) and period end, because a restated quarter changes the answer.
5. Record the finding. Persist the conclusion, its sources, and the decision into solomon-memory via save_decision or save_memory so the next session resumes from evidence, not from recollection.

## Primary sources and where to look

- Company filings on SEC EDGAR. The 10-K is the audited annual report (business, risk factors, MD&A, full statements); the 10-Q is the unaudited quarterly update; the 8-K reports material events within four business days under Regulation FD 2000 (guidance, executive change, M&A, going-concern doubt). Use EDGAR full-text search (introduced 2021) to find a phrase across every filer at once, for example a specific covenant term or customer name.
- Earnings call transcripts. Read management's prepared remarks for the framing and the analyst Q&A for what they avoid answering. Cross-check spoken figures against the matching 8-K exhibit, since the press release is the source of record and the transcript can contain transcription errors.
- Investor-relations pages. Use for the supplemental deck, the segment bridge, and the guidance table, but treat IR material as issuer-selected; confirm any headline number against the filing.
- Macro and rates context. Pull the U.S. Treasury yield curve for the risk-free discount rate and the term structure, and FRED for series such as CPI, the federal funds rate, and unemployment. Cite the series ID and the exact observation date.
- Classification. Map the company to its sector with GICS 2023 so comparables and screens are consistent.

## Source-credibility tiering

- Tier 1: primary filings and official records — SEC EDGAR documents, central-bank and Treasury data, audited statements. These can settle a question.
- Tier 2: established financial press and reputable sell-side or data vendors with a named author and a correction policy. Useful for context and for surfacing facts to confirm against Tier 1.
- Tier 3: promotional, anonymous, or unverifiable material — message-board posts, paid newsletters, unattributed blogs. Quarantine these: log what they claim, attribute nothing to them, and either confirm against a higher tier or discard.

## Tooling: when to reach for each

- WebSearch first to locate the canonical source and find the EDGAR or IR URL; never quote a search snippet as the source.
- WebFetch to retrieve and read a known URL — a filing index page, a FRED series, a press release. It is the default for static, public documents.
- claude-in-chrome when a source needs an interactive session: a transcript portal behind a click-through, a JavaScript-rendered IR data table, or a viewer that WebFetch cannot read. Use it for rendering, not for bypassing access controls.
- solomon-memory to read prior decisions before researching (avoid repeating work) and to write the finding after, so each conclusion is durable and traceable.

## Common pitfalls

- Citing a news article in place of the filing it summarizes — the recap can drop a footnote or a restatement that flips the conclusion.
- Quoting a number without its period end and accounting basis — a US GAAP figure and an adjusted non-GAAP figure for the same line are not comparable.
- Treating an investor-relations deck as neutral — issuer-selected highlights omit the unfavorable context that the 10-K is required to disclose.
- Promoting a Tier 3 claim into the thesis because it is vivid — anonymous or promotional sources are unverifiable and bias the result.
- Recording a finding with no retrieval timestamp — sources change and pages get revised, so an undated claim cannot be audited later.
- Mixing comparables across inconsistent sector definitions — without a single classification such as GICS 2023, the peer set is silently wrong.

## Definition of done

- [ ] The question is written as a falsifiable claim with a metric, period, and decision threshold.
- [ ] Every figure traces to a Tier 1 primary source on SEC EDGAR or an equivalent official record.
- [ ] Each source is tagged Tier 1, Tier 2, or Tier 3, and no Tier 3 source carries a conclusion on its own.
- [ ] Every claim has a source URL, document date, and an ISO 8601:2019 retrieval timestamp, with the accounting basis noted for financial figures.
- [ ] Macro inputs cite the FRED series ID or the Treasury yield-curve observation date.
- [ ] The conclusion and its sources are persisted to solomon-memory for the next session.
