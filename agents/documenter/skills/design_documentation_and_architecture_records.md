## Design documentation and architecture records


- Record significant decisions as Architecture Decision Records (ADRs) using the MADR template: context, decision, status, consequences, alternatives considered. One decision per ADR, immutable once accepted; supersede rather than rewrite.
- Use the C4 model for architecture diagrams (Context, Container, Component; Code only when it earns its keep). Keep each level on its own page. Maintain diagrams as code (Structurizr DSL or Mermaid) so they regenerate.
- Design docs state the problem, constraints, non-goals, the chosen approach, rejected options with reasons, and open questions. Link the design doc to the issues and PRs that implement it.
- System architecture records name the design contracts (interfaces and invariants) that bound each component, consistent with the SOLID and modularity rules the engineering specialists follow.
