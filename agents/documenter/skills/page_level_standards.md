# Page-Level Standards

This skill governs the anatomy of a single documentation page: the title-to-next-steps skeleton, the one-purpose rule, scannability thresholds, code-block discipline, and link hygiene. The stance: readers do not read pages, they scan them under time pressure; a page is well-formed when a scanner finds the answer without reading and a reader who does read is never surprised by a missing prerequisite.

## The page skeleton

Every page follows the same shape, top to bottom:

1. **Title**: one H1. A noun phrase for reference and explanation ("Loop lock configuration"), an imperative or gerund task for how-to material ("Rotate API keys", "Configuring TLS").
2. **Intro**: two or three sentences stating the audience, the task or question, and the outcome — what the reader will have or know at the end. A reader decides in ten seconds whether this page is theirs; the intro is that decision's input.
3. **Prerequisites**: everything needed before the first step — access, tools with versions, prior pages — as a short checklist. Prerequisites discovered at step 6 are a page defect.
4. **Body**: the steps, tables, or discussion, shaped by the page's Diátaxis type.
5. **Verification**: for task pages, how the reader confirms success — the command and its expected output, or the UI state to observe.
6. **Next steps**: two to four links to what the reader plausibly does next. Not a link farm; a curated handoff.

One purpose per page. If the title needs "and", or the intro must name two audiences, split the page. A page that serves everyone serves no one.

## Front matter

Every page carries metadata: `owner`, `status` (draft / reviewed / deprecated), `last_reviewed` (ISO date), and the product version or commit it was validated against. This is what the staleness tooling and review cadence key on; a page without front matter is invisible to lifecycle checks.

## Scannability

- One H1 per page; heading depth no greater than H4. If H5 feels necessary, the page is overloaded — split it.
- A heading at least every three to five paragraphs. Headings are the scanner's index; a scanner reading only your headings should still leave with the page's outline.
- Sections of roughly 100 to 300 words. Longer sections hide answers; shorter ones fragment the flow.
- Prefer a list or table over any paragraph that enumerates. Three parallel facts in prose is a table nobody can scan.
- Procedures are numbered steps, one action per step, with the expected result stated after any step that produces visible output. A step with "and" in it is two steps.
- Bold sparingly, for the terms a scanner must catch — not for emphasis of whole sentences.

## Code blocks and placeholders

- Every code block is fenced with a language tag, copy-pasteable, and tested. Do not mix shell prompt characters into copyable commands; if you show output, separate the command block from the output block.
- Real, runnable examples over `<placeholder>` soup. When a placeholder is unavoidable, define each one immediately below the block, with an example value.
- Use semantic line breaks in Markdown source — one sentence or clause per line. Rendered output is identical, but diffs become per-sentence and review comments land precisely.

## Link hygiene

- Link text describes the destination: "see the release policy", never "click here" or a bare URL. Screen readers enumerate links out of context; "here, here, here" is unusable.
- Use relative links within the doc set so they survive forks, branches, and offline rendering; reserve absolute URLs for external destinations.
- Link to pages rather than to deep heading anchors when the heading is likely to be renamed; anchors break silently.
- A link checker (`lychee`) runs in CI on every PR; when a page moves, leave a redirect or a stub pointing at the new home so inbound links keep working.
- Every image and diagram has alt text; diagram source (Mermaid, PlantUML, Structurizr DSL) is committed next to the render so diagrams stay diffable and editable.

## Common pitfalls

- Burying prerequisites mid-procedure, so the reader discovers a missing permission halfway through a change window.
- Titles that describe the feature instead of the reader's task, forcing readers to guess which feature solves their problem.
- Wall-of-prose sections with no heading for eight paragraphs; scanners bounce and search again.
- Multi-action steps ("Run X and then edit Y and restart Z") that make failure diagnosis impossible — which part failed?
- Untested code blocks with stale flags, or prompt characters pasted into terminals along with the command.
- Undefined placeholders (`<your-value>`) with no explanation of what a valid value looks like.
- "Click here" links, bare URLs in prose, and deep anchor links that break on the next heading edit.
- Missing front matter, which silently exempts the page from ownership and staleness checks.

## Definition of done

- [ ] The page has one H1, a two-to-three-sentence intro naming audience, task, and outcome, and follows the skeleton: prerequisites, body, verification, next steps.
- [ ] The page has exactly one purpose; no "and" in the title, one audience in the intro.
- [ ] Front matter carries `owner`, `status`, `last_reviewed`, and the validated version or commit.
- [ ] Heading depth is at most H4, with a heading at least every three to five paragraphs; enumerations are lists or tables, not prose.
- [ ] Procedures are numbered, one action per step, with expected results after output-producing steps.
- [ ] All code blocks are language-tagged, tested, copy-pasteable, and free of mixed prompt/output; placeholders are defined below each block.
- [ ] Links are descriptive and relative within the doc set; the CI link check passes; moved pages leave redirects.
- [ ] Every image has alt text and every diagram has committed source.
- [ ] Markdown source uses semantic line breaks.
