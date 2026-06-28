# Documentation Best Practices

Standards for producing technical and business documentation, user guides, API/developer docs, and design records that stay accurate, findable, and maintainable.

## Operating principles


- Docs-as-code: source docs in the repo next to the code they describe, in Markdown or reStructuredText. Every change ships through a branch, a PR, and review. No doc lives only in a wiki UI or a shared drive.
- Write for one reader and one job per page. State the audience and the task in the first two sentences. If a page serves two audiences, split it.
- Front-load the answer (inverted pyramid). Put the conclusion, the command, or the decision first; put rationale and edge cases after.
- Single-source facts. A value, limit, or endpoint is defined in exactly one place and included or linked elsewhere. Duplicated facts drift.
- Minimum viable documentation: a short, correct page beats a long, stale one. Delete content you cannot keep current.
