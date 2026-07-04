# Documenter Definition of Done

The release gate for every documentation deliverable: the checklist below must hold before a page, guide, or reference ships. The pitfalls first — they are the specific ways documentation work gets marked done while failing that gate, and each one is grounds for sending the deliverable back.

## Common pitfalls

- A page marked done with no Diátaxis classification, or classified after drafting to match whatever got written — the type must drive the structure, not label it retroactively.
- `last_reviewed` bumped in front matter without re-running the commands or re-checking versions — a fresh date on unverified content defeats the staleness sweep it feeds.
- Code blocks pasted from a terminal session and never re-executed — "worked once on my machine" is not tested; execution in CI (doctest or extracted snippets) is the bar.
- Reference declared complete as hand-written prose while the OpenAPI spec disagrees — only spec-generated, CI-diffed output counts as done.
- Vale, markdownlint, or the link check skipped locally with the intent to fix in CI later — the gate is that they pass, not that they were scheduled.
- The wiki left unsynced after merge because `scripts/wiki-sync.sh` is a manual step — the deliverable includes the sync and the changelog entry, not just the page diff.

## Definition of done


- [ ] Page is classified as exactly one Diátaxis type and placed/named accordingly.
- [ ] Audience and task stated up front; answer front-loaded.
- [ ] Front matter present: owner, status, `last_reviewed`, validated version/commit.
- [ ] All commands and code blocks tested and copy-pasteable; placeholders defined.
- [ ] API reference generated from a Spectral-linted OpenAPI 3.1 spec; every endpoint covers auth, params, responses, errors, rate limits, and has a success and a failure example.
- [ ] Diagrams stored as source (Mermaid/PlantUML/Structurizr); every image has alt text.
- [ ] Decisions captured as MADR ADRs; design docs list non-goals and rejected options.
- [ ] Specialist artifacts include their mandatory fields (quant metrics, ML validation/guards, QA mocking, STRIDE).
- [ ] Vale, markdownlint, and link checking pass in CI; no banned cliches, no emojis.
- [ ] Readability within grade 8 to 10; active voice; glossary updated for new terms.
- [ ] Changelog and version updated; wiki synced via `scripts/wiki-sync.sh`.
