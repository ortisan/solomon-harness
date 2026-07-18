---
name: skill-authoring-craft
description: Governs the craft of a skill's body — the words and structure decided once scope_and_mandate.md's scaffolding mechanics and agents/AGENTS.md's format contract are already satisfied — covering predictability as the root virtue, the information-hierarchy ladder for placing content in-skill or behind a pointer into docs/adrs, docs/specs, or an external skill source, the sentence-level no-op pruning test, leading words as token-efficient anchors, and the named failure modes (premature completion, duplication, sediment, sprawl, no-op, negation). Use when drafting a new skill's body, reviewing an existing skill for bloat or drift, or judging whether a specific sentence earns its place in a skill file.
---

# Skill Authoring Craft

`scope_and_mandate.md` owns the scaffolding mechanics of a new agent — the directory layout, the confinement checks, the registry sync points. `agents/AGENTS.md`'s "Skill file format" section owns the format contract — the frontmatter shape, the 600-word floor, the two closing sections every skill must carry. Neither tells you how to write the words in between. This skill governs that craft: what belongs in a skill's body, what gets pushed to a pointer instead, what gets cut outright, and which words the agent will actually reach for when it runs the skill. Do not restate the mechanics or the format contract here — cross-reference both and keep this file to the craft judgment they leave open.

## Predictability is the root virtue

A skill exists to wrangle determinism out of a stochastic system. Predictability means the agent takes the same process on every run, not that it produces the same output — a skill governing `architecture_scan_loop` should predictably scan the same categories of drift every time even though the drift it finds varies run to run. Cost and brevity are symptoms of predictability, not competing goals to trade against it: a shorter skill body is not automatically better if the cut costs the agent its grip on the process. Every rule below — the hierarchy, the pruning test, leading words, the failure modes — is a lever on this one virtue, not an independent style preference to weigh separately.

One predictability question compozy's source spends real ink on does not apply here: whether a skill's description competes for context on every turn versus sitting inert until a human types its name. Solomon skills carry no such choice. Each specialist's Active Skills list, generated into `agents/<name>/agents/<name>.md` by `scripts/document-skills.py`, is fixed at compile time — every skill an agent has loads whenever that agent runs, full stop. There is no autonomous mid-session firing to reason about and no invisible user-only mode to weigh against it. The craft question this skill governs is not whether to load the skill; it is whether the agent takes the same path through the body once it is loaded, and that question is exactly as live for a fixed Active Skills list as it would be for any other invocation model.

## The information hierarchy

Content sits at one of three rungs, ranked by how immediately the agent needs it:

1. In-skill step — an ordered action written directly in the body. Steps are the top rung: what the agent does, and in what order. End every step on a completion criterion the agent can check itself against, and make it checkable ("every modified model accounted for") rather than a mood ("understanding reached") — a vague bound is where a step gets waved through before it is genuinely finished.
2. In-skill reference — a definition, rule, or fact written directly in the body but consulted on demand rather than executed in sequence. This is often a legitimately flat peer-set (every check in a review, every field in a config) rather than a smell; most of this file itself sits at this rung.
3. External reference — material pushed out of the skill file entirely, reached by a pointer the agent follows only when it fires. Solomon's own vocabulary for this rung already exists, so use it rather than inventing a parallel one: an architecturally significant, costly-to-reverse decision belongs in `docs/adrs/` and gets pointed at by number and title, the pattern `architectural_decision_records.md` and `design_documentation_and_architecture_records.md` already follow; an issue-level requirement or acceptance-criteria set belongs in `docs/specs/`; and a skill pulled with `solomon-harness skills add` from a source configured in `skill-sources.json` is external reference by construction, since it lives in a different repository entirely.

The decision at each rung is the same trade in both directions: push too little down and the top of the skill bloats past what any single run needs; push too much down and the agent never reads material it actually needed inline. Resolve it by branch — if every run through the skill needs a fact, keep it in the body; if only some runs reach it, disclose it behind a pointer. A pointer's wording, not its target, decides whether the agent follows it: a must-read ADR referenced by a vague "see the ADR" fires less reliably than one named by number and title, so fix the wording before you consider pulling the material back inline.

## Pruning: the no-op test, sentence by sentence

Run every sentence through one test before it survives a draft: does this sentence change the agent's behavior versus what it would already do without being told? A sentence that fails — "be thorough," "make sure to check your work" — costs context and returns nothing, because the agent was already going to produce the thorough-ish version of that behavior regardless. When a sentence fails the test, delete the whole sentence. Do not trim it to a shorter version of the same no-op; a shortened restatement of nothing is still nothing, just cheaper to write and just as costly to read. This is a per-sentence discipline, not a per-paragraph one — a paragraph can carry three load-bearing sentences and one freeloader, and the freeloader has to go on its own merits, not survive because its neighbors passed.

Left unchecked, a skill without this discipline accumulates sediment: layers of instructions nobody removes because adding felt safe and deleting felt risky, until the live guidance is buried under stale guidance describing a process the codebase no longer follows. The fix is not a periodic rewrite; it is running the no-op test on every sentence each time the skill is touched for any reason — the same habit this agent already applies to `agents/AGENTS.md` roster entries, turned on prose instead of registry rows.

## Leading words

A leading word is a compact, already-pretrained concept the agent thinks with while running the skill — a single token doing the work of a restated phrase, because it recruits meaning the model already carries instead of spelling the meaning out fresh each time. This repository already runs on several: red/green (the TDD cycle in `agents/AGENTS.md`), claim/lease (per-issue locking), single-driver lock (loop concurrency). Each replaces a paragraph of explanation with one word once that word has been defined a single time, and each anchors both ends of a skill: in the body it pulls the agent toward the same behavior every time the word recurs, and in a description or roster listing it links the same shared vocabulary a specialist's prompts and docs already use, so the right skill fires on the right cue. When a skill spells out the same idea in three different places, that repetition is the signal a leading word is missing — look for the noun the team already uses for it before inventing new phrasing, since a coined term recruits no priors and costs definition tokens a reused term gets for free.

## Failure modes, and the fix for negation

Beyond premature completion (a step waved through on a vague completion criterion, covered above), duplication (one meaning asserted in two places, so a change requires editing both and the second copy eventually drifts out of sync), sediment (stale layers nobody prunes), and sprawl (a skill long enough to hurt readability even when every line is live and non-duplicated, cured only by pushing reference down the hierarchy and splitting by branch), one failure mode needs its own rule: negation. Steering by prohibition backfires — "don't think of an elephant" names the elephant and makes it more present in the reader's attention, not less; "never skip the completion criterion" plants skipping as the available action right next to the instruction not to take it. The fix is to prompt the positive: state the target behavior directly ("end every step on a checkable completion criterion") so the banned behavior is never named at all. Keep a bare prohibition only where the behavior genuinely cannot be phrased as a positive target — a hard guardrail, not a style default — and even then pair it with the positive action to take instead, so attention lands on what to do rather than on the thing to avoid.

## Common pitfalls

- Restating `scope_and_mandate.md`'s directory layout or `agents/AGENTS.md`'s frontmatter rules inside this file instead of pointing at them — that creates two sources of truth for the same mechanics, and one silently drifts as the other is edited.
- Trimming a no-op sentence to a shorter no-op instead of deleting it outright — a compressed restatement of nothing is still nothing.
- Writing a prohibition ("never do X") where a positive instruction does the same job, which drags the banned behavior into the agent's attention instead of suppressing it.
- Inlining an ADR's or spec's full content instead of pointing at `docs/adrs/<n>-<slug>.md` or `docs/specs/<slug>.md` by number and title — this duplicates a decision or requirement that then drifts out of sync with its source of record.
- Coining a new leading word where a term already in `agents/AGENTS.md`, an ADR, or the codebase's own vocabulary already carries the meaning — the coined word recruits no priors and costs definition tokens the reused word would have gotten for free.
- Treating the fixed Active Skills list as a reason to skip the predictability question — a skill still needs a checkable completion criterion on each step even though it never competes for autonomous mid-session firing.

## Definition of done

- [ ] Every sentence in the body passes the no-op test: it changes the agent's behavior versus the default, or it has been deleted.
- [ ] Every step, where the skill has steps, ends on a completion criterion that is checkable, not a mood.
- [ ] Material only some runs need is disclosed behind a pointer named by number and title into `docs/adrs/`, `docs/specs/`, or an external skill source — not inlined for every run.
- [ ] No prohibition appears without a positive instruction beside it, and no prohibition exists where a positive rewrite would do the same job.
- [ ] No sentence restates a rule already owned by `scope_and_mandate.md`'s scaffolding mechanics or `agents/AGENTS.md`'s format contract.
- [ ] `scripts/check-skill-depth.py` passes on the file: 600-word body floor, matching frontmatter name and description, and both closing sections present.
