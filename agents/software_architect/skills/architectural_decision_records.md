## Architectural Decision Records


One decision per ADR. Immutable once accepted. To change a decision, write a new ADR and set the old one's status to `Superseded by ADR-NNNN`; never edit an accepted record's substance.

Store ADRs as `docs/adr/NNNN-kebab-title.md`, numbered monotonically, starting at 0001. Use MADR or Nygard format. Minimum sections:

- **Status** — Proposed, Accepted, Deprecated, or Superseded (with the link).
- **Context** — the forces in play: requirements, constraints, NFR targets, deadlines, team skills. State facts, not the choice.
- **Decision** — the position taken, in active voice: "We will use ...".
- **Consequences** — what becomes easier and what becomes harder. The trade-off and the cost are mandatory; an ADR with only upsides is incomplete and signals you have not found the real cost yet.
- **Options considered** — at least two alternatives with the reason each was rejected. A single-option ADR is a rationalization, not a decision.

Write an ADR when the decision affects structure, is costly to reverse, or future maintainers will ask "why on earth did they do this". Examples: choosing a persistence engine, sync vs async integration, monolith vs service split, an auth scheme, a public API contract style. Skip ADRs for naming conventions, library micro-choices, and anything trivially reversible.

Pitfalls: writing the ADR after the code ships (decision theater); burying the real reason ("the vendor sponsored us") behind a technical rationalization; letting status fields go stale so nobody can tell which records are live.
