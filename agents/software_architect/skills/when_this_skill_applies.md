# Software Architect Best Practices

Purpose: a concrete standard for producing C4 diagrams, Architectural Decision Records, design contracts, and non-functional requirements that hold up under review and survive contact with implementation.

## When this skill applies


Use it whenever you define or change system structure: introducing a service, a database, an integration, a cross-cutting concern (auth, caching, messaging), or any decision that is expensive to reverse. If a change is local to one module and reversible in an afternoon, document it in code and a commit message, not in an ADR. Reserve architecture artifacts for decisions with system-wide blast radius.
