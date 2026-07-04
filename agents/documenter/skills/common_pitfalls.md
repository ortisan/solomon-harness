# Documenter Common Pitfalls

The documentation anti-patterns a reviewer rejects on sight, and the release checks that prove a deliverable avoids them. These are the cross-cutting failure modes that recur across every Diátaxis quadrant — branching tutorials, hand-maintained reference, unsourced screenshots, unpinned versions, duplicated facts, marketing tone; page-level anatomy and lifecycle mechanics live in their own skills.

## Common pitfalls


- Tutorials that branch into options and become unfollowable. Keep them linear and guaranteed to succeed.
- Reference written by hand and drifting from the API. Generate it from the spec.
- Screenshots of fast-changing UI with no source and no alt text. Prefer text and diagrams-as-code; automate screenshots where you must use them.
- "Latest"-only docs with no version pinning, so a user on an older release follows wrong steps.
- Duplicated config tables in five pages. Single-source and include.
- Marketing tone, hedging, and filler. Say what the system does and what the reader must do.

## Definition of done

- [ ] The tutorial was run start to finish on a clean environment by someone other than the author, with no branching choices and every step succeeding.
- [ ] API reference is generated from the Spectral-linted OpenAPI spec, and the CI regeneration diff is clean — no hand-edited drift in the committed output.
- [ ] Every page's front matter pins the product version or commit it was validated against; no page documents an unpinned "latest".
- [ ] Any screenshot has committed capture automation or is replaced by text or a diagram-as-code source (Mermaid, PlantUML, Structurizr); every image carries alt text.
- [ ] Each repeated fact (config table, default, limit) lives in one source file pulled in by include; a search for the value finds exactly one authoritative copy.
- [ ] Vale passes with no marketing tone, hedging, filler, or banned cliches; the prose states what the system does and what the reader must do.
