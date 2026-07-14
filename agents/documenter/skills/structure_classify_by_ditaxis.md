---
name: structure-classify-by-ditaxis
description: Governs classifying every page into exactly one Diátaxis quadrant - tutorial, how-to guide, reference, or explanation - before drafting, detecting mixed-page smells in review, and migrating a legacy corpus. Use when starting a page, reviewing for mixed audiences, or planning a restructure.
---

# Structure: Classify by Diátaxis

Every page is exactly one of the four Diátaxis types — tutorial, how-to guide, reference, or explanation — and is named, located, and written so the type is obvious before the reader clicks. This skill governs how to classify a page before drafting it, how to detect a mixed page in review, and how to migrate a legacy corpus onto the framework. Classification is the first editorial decision, not a label applied afterward: a reader on a deadline must reach the right kind of page in two clicks.

## The four quadrants

Diátaxis (Daniele Procida, diataxis.fr) organizes documentation along two axes: whether the reader is acting or understanding, and whether the reader is studying or working. The four quadrants serve four distinct reader needs, and each demands a different voice:

- **Tutorial** — learning-oriented. A guided lesson that a beginner completes successfully every time. Concrete, linear, no choices, no alternatives, no theory beyond the minimum needed to keep moving. The author carries all responsibility for the learner's success; if a learner can fail by following it, the tutorial is broken.
- **How-to guide** — task-oriented. A recipe that solves one real problem for a competent user. It starts from a goal ("Rotate API keys"), assumes working knowledge, may branch on the reader's situation ("if you deploy with Docker, ..."), and stops the moment the goal is reached.
- **Reference** — information-oriented. Dry, complete, and structured like the machinery it describes: endpoints, config keys, CLI flags, schemas. It states facts with consistent shape and terminology; it never teaches, persuades, or narrates scenarios. Generate it from the source of truth wherever possible.
- **Explanation** — understanding-oriented. The "why": design rationale, trade-offs, history, alternatives considered. It is read away from the keyboard. Architecture overviews and the discussion around ADRs live here.

## Decision tests

Classify with these questions, in order, before writing a word:

1. Is the reader learning by doing, with you responsible for their success? Tutorial.
2. Does the reader arrive with a goal and working knowledge, needing reliable steps? How-to guide.
3. Will the reader look one fact up mid-task and leave within a minute? Reference.
4. Is the reader trying to understand something, with nothing to execute right now? Explanation.

Break ties by what the reader does next. If the honest answer is "it teaches the concept and lists all the flags", that is two pages, each linking to the other.

## Mixed-page smells

Reject these in review; each signals a page serving two masters:

- A tutorial that pauses mid-step for three paragraphs of theory. Move the theory to an explanation page and link it from the step.
- A how-to guide that opens by teaching fundamentals ("What is OAuth?"). Its audience already knows; link a tutorial for readers who do not.
- Reference tables interrupted by step sequences, or steps that embed exhaustive option tables. Split them: steps stay in the how-to, tables move to the reference.
- An explanation page with numbered commands. If there is something to run, it belongs in a tutorial or how-to.
- A title that needs "and": "Installing and configuring and troubleshooting X" is three pages.

## Migrating a legacy corpus

Do not rewrite everything at once; migrate in bounded passes:

1. Inventory every page and tag each section (not each page — mixed pages are the problem) with a quadrant. A sheet with URL, section, quadrant, and owner is enough.
2. Fix the information architecture first, grouping navigation by quadrant, so every new page has an obvious home and the migration has a target shape.
3. Split the worst offenders first — highest traffic times most mixed — one page per pull request, preserving inbound URLs with redirects or stub pages that point at the split results.
4. Relocate displaced content instead of deleting it; theory buried in a tutorial is usually good raw material for an explanation page.
5. Enforce classification at review time for all new pages, so the backlog only shrinks.

## Common pitfalls

- Classifying by author intent ("I wrote it as a guide") instead of reader need; the decision tests describe the reader's situation, not the prose.
- Tutorials with branches ("choose A or B"). A beginner cannot choose; choose for them and cover the alternative in a how-to guide.
- Reference pages that editorialize ("we recommend..."); recommendations are how-to or explanation content and they undermine the reference's neutrality.
- Treating Diátaxis as a folder-renaming exercise: reorganizing navigation without splitting mixed pages changes nothing for the reader.
- Big-bang migrations that break inbound links and stall halfway; migrate page by page behind redirects.
- An empty explanation quadrant. When "why" content has nowhere to live, it leaks into tutorials and reference pages and creates the mixed pages above.

## Definition of done

- [ ] Every new or edited page is classified as exactly one Diátaxis quadrant, and the classification is stated in the pull request description.
- [ ] The title and location signal the type: imperative or gerund task titles for how-to guides, noun phrases for reference and explanation.
- [ ] No mixed-page smell from the list above survives review; displaced content is moved and linked, not deleted.
- [ ] Tutorials are verified end to end by someone other than the author and succeed without intervention.
- [ ] Cross-quadrant needs are met with links, not by inlining foreign content.
- [ ] Legacy migrations preserve inbound URLs via redirects or stubs, and the inventory sheet reflects the new state.
