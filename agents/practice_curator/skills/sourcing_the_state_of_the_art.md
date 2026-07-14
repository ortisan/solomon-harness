---
name: sourcing-the-state-of-the-art
description: Governs how the practice_curator finds, dates, and credibility-ranks evidence — a two-independent-source minimum, a four-tier credibility ladder from standards bodies to vendor docs, and mandatory dating — before a best-practice claim can back a finding. Use when sourcing evidence for an audit finding or a benchmarking yardstick before it drives a proposal.
---

# Sourcing the State of the Art

Every best-practice claim the curator makes must rest on at least two dated, credible sources, gathered and ranked before the claim is allowed to drive a finding. This skill governs how the practice_curator finds, dates, and grades evidence so that an audit's statement of "the current standard is X" is a checkable fact rather than an opinion. It is the evidence engine for `auditing_delivered_work` and the supplier of the yardsticks named in `benchmarking_across_domains`. Without a recorded source set, a claim cannot back a finding.

## The two-source minimum

A single source is an anecdote. Require at least two independent, dated, credible sources that agree before a practice is treated as current. Independent means not the same author or organization republished: two blog posts that both summarize the same conference talk count as one source, not two. When the two strongest sources disagree, the practice is contested — record both positions and let `auditing_delivered_work` downgrade the observation to its insufficient evidence bucket rather than picking a side. The point of the minimum is to make staleness and bias visible before they reach a proposal.

## Credibility ranking

Rank sources by credibility, highest trust first, and require at least one of the two from the top three tiers:

1. Primary standards bodies and their published documents: IETF RFCs, ISO/IEC and IEEE standards, W3C recommendations, NIST publications, OWASP project pages, and the official language or framework specifications and release notes (PEP documents for Python, TC39 proposals for JavaScript, the framework's own versioned docs).
2. Peer-reviewed literature: conference and journal papers such as NeurIPS, ICML, and ICLR for machine learning. arXiv preprints are acceptable as supporting evidence but not as the sole source, because a preprint has not been peer reviewed.
3. Actively-maintained reference implementations and their official documentation at a pinned version: a maintained library's changelog, or the canonical implementation a standard points to.
4. Vendor engineering docs and well-known practitioner books with a named author and a stated edition.

Below this line sits blog hearsay, undated forum answers, and content with no named author. Never use it as one of the two required sources; it can suggest a lead, but the claim must be confirmed by something higher in the ranking. Credibility is judged per source and per topic: a vendor's blog is authoritative for that vendor's own API and weak for a neutral cross-tool comparison.

## Dating a source

A practice is "state of the art" only relative to a date, so every source must carry one. To date a source, read the RFC's publication month, the paper's year, the library's release or tag date and the exact version it documents, the specification's edition, or the page's last-reviewed stamp. For documentation without a visible date, pin to the version number and resolve that version's release date from the changelog or git tag. Reject undated sources for any currency claim.

Treat a source as stale when a newer major version, a superseding standard, or a newer edition exists. Two concrete examples: citing RFC 6819 for OAuth threat advice is stale once RFC 9700 (January 2025) supersedes it, and citing TensorFlow 1.x graph-session patterns in 2026 is stale against TensorFlow 2.x with Keras 3 and PyTorch 2.x. A source that was authoritative three years ago is not automatically authoritative today; the dating step is what catches that drift.

## Recording evidence in project memory

Capture every accepted source set with `save_decision` in project memory: the practice being claimed, the two or more sources with their titles and identifiers or URLs, each source's publication or version date, and its rank in the credibility order. This record is what `auditing_delivered_work` cites in each finding and what `benchmarking_across_domains` reuses, so the same standard is not re-researched for every PR. A claim with no recorded decision is not allowed to back a finding, and a recorded decision with fewer than two qualifying sources is held as insufficient evidence.

## Common pitfalls

- Backing a claim with one source, which makes a single author's opinion read as a settled standard.
- Counting two republications of the same underlying material as two sources, defeating the independence requirement.
- Using an undated page or an undated forum answer for a currency claim, so staleness cannot be detected.
- Treating an arXiv preprint as peer-reviewed and using it as the only source, when it has not cleared review.
- Ranking a vendor blog as a neutral authority for a cross-tool comparison, importing the vendor's bias.
- Not pinning a documentation source to a version, so it silently drifts when the docs are updated.
- Skipping `save_decision`, leaving the finding's evidence unrecorded and the audit non-reproducible.

## Definition of done

- [ ] Each claimed best practice has at least two independent, dated, credible sources that agree.
- [ ] At least one of the two sources sits in the top three credibility tiers; blog hearsay is never a required source.
- [ ] Every source carries a resolved date, derived from publication, edition, or pinned version.
- [ ] Any source superseded by a newer standard, version, or edition is flagged stale and not used as current.
- [ ] Contested or single-source practices are marked for the insufficient evidence bucket, not asserted as standard.
- [ ] The full source set, with dates and credibility ranks, is recorded via `save_decision` in project memory.
- [ ] The recorded evidence is reusable by `auditing_delivered_work` and `benchmarking_across_domains` without re-research.
