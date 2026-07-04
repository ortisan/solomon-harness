# Operating Principles

This skill defines the documenter's core stance: documentation is a product with users and metrics, written for one analyzed audience per page, single-sourced, front-loaded, and edited without mercy. Every other documenter skill applies these principles to a specific artifact type; when two rules conflict, resolve toward the principle here.

## Docs are a product

Documentation has users, a backlog, and success metrics; run it like the product it is:

- Instrument it. The metrics that matter: time-to-first-success for the quickstart, search terms that return no useful result, the pages behind support tickets, and per-page feedback where the platform offers it. Traffic alone is not a quality signal — a much-visited troubleshooting page can mean the product is failing well before it means the docs are succeeding.
- Prioritize by reader impact: traffic multiplied by task criticality. Fixing the install guide beats polishing an explanation page nobody is blocked on.
- Close the loop: a support question answered twice becomes a docs issue; a docs issue is triaged, fixed, and verified like a code bug.

## Audience analysis

Before writing, answer three questions about the primary reader: what is their role, what do they already know, and what are they trying to do right now. Then:

- Write each page for exactly one reader in one situation, and state the audience and the task in the first two sentences so the wrong reader bounces cheaply.
- If a page must serve two audiences — an operator and an integrator, a beginner and an expert — split it. A page hedging between audiences pads itself with content each half must skip.
- Calibrate assumed knowledge explicitly through prerequisites, not implicitly through jargon. "You have a running SurrealDB instance" is a prerequisite; unexplained internal vocabulary is a wall.

## Docs-as-code

Source documentation in the repository, next to the code it describes, in Markdown. Every change ships through a branch, a pull request, and review; CI lints prose, checks links, and executes examples. No canonical doc lives only in a wiki UI or a shared drive — in this repo even the wiki is authored in `docs/wiki/` and pushed by `scripts/wiki-sync.sh`, so the repository stays the source of truth and wiki edits are reviewable diffs.

## Single source of truth

A fact — a limit, a port, an endpoint, a version — is defined in exactly one place and included or linked everywhere else. Duplicated facts do not stay identical; they drift, and the reader who hits the stale copy has no way to know it is the stale one. Corollaries:

- Prefer generated content (API reference from the spec, CLI reference from `--help` output) over transcribed content; transcription is duplication with extra steps.
- When you find the same table in three pages, the fix is one source and three links or includes, not three synchronized edits.
- Repair at the source. Patching the downstream copy leaves the generator wrong and reintroduces the bug at the next sync.

## Front-load the answer

Structure every unit — page, section, paragraph, sentence — as an inverted pyramid: conclusion first, then rationale, then edge cases. Put the command before the explanation of the command, the decision before the history that produced it. Readers arrive mid-task; the ones who need the background will keep reading, and the ones who do not should not have to.

## Edit ruthlessly

The first draft explains the topic to the writer; the edit makes it useful to the reader.

- Budget a cutting pass: a 20 to 30 percent reduction in word count with no loss of meaning is the normal outcome of one honest edit, not an ambitious one.
- Every sentence earns its place by telling the reader something they need for the task at hand. Throat-clearing openers, restated context, and hedges go first.
- Minimum viable documentation: a short page that is correct and current beats a long page that is comprehensive and stale. Scope pages to what you can keep true.
- Deletion is editing. A page you cannot maintain is a liability; remove it and leave a pointer to what replaced it.

## Common pitfalls

- Writing for an imagined "general reader", which produces pages too basic for experts and too dense for beginners at the same time.
- Measuring documentation by volume shipped — page count and word count reward exactly the wrong behavior.
- Treating docs feedback and support signals as noise instead of a backlog; the same question answered in chat five times is a missing page with a known title.
- Canonical content drafted in a wiki UI or a shared document, bypassing review and version control, then drifting from the repo's truth.
- Copying a value "just this once" into a second page; that is the moment drift begins.
- Background-first structure that makes the reader excavate for the command they came for.
- Publishing the unedited first draft because it is "done"; the cutting pass is where the page becomes readable.
- Keeping a stale page because deleting feels like losing work; git history keeps the work, readers keep the confusion.

## Definition of done

- [ ] The page states its audience and task in the first two sentences and serves exactly one reader in one situation.
- [ ] The change is prioritized and justified by reader impact (traffic, tickets, TTFS), not by author convenience.
- [ ] The content lives in the repository and shipped through a reviewed pull request with docs CI green.
- [ ] Every fact is defined in one source; new content links or generates rather than duplicates, and fixes landed at the source.
- [ ] The answer — command, decision, or conclusion — appears before its rationale at page, section, and paragraph level.
- [ ] A cutting pass was performed; filler, hedges, and restated context are gone.
- [ ] Pages that this change obsoletes are deleted or redirected, not left to rot beside their replacements.
