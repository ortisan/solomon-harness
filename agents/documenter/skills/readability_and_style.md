# Readability and Style

This skill governs the prose itself: plain-language rules with measurable targets, voice and tense, terminology discipline, and the style linters that enforce all of it in CI. The stance: style is not taste — pick one published guide, set numeric thresholds, and let Vale reject violations mechanically so reviewers spend their attention on substance.

## One style guide, enforced

Adopt exactly one published guide per project — the Google developer documentation style guide (the default here) or the Microsoft Writing Style Guide — record the choice where contributors will see it, and do not mix the two. The guide settles the arguments nobody should have twice: capitalization of headings, serial commas, UI element formatting, "click" versus "select". When the house rules in `agents/AGENTS.md` conflict with the guide, the house rules win.

## Plain-language targets

Numbers, not vibes:

- Readability at US grade 8 to 10 (Flesch-Kincaid) for tutorials and guides; reference material may run denser because it is scanned, not read.
- Average sentence length under 25 words, hard ceiling around 35. A sentence carrying three clauses is three sentences.
- Paragraphs of five sentences or roughly 100 words at most, one idea each. In procedural writing, prefer a numbered step to a paragraph.
- Front-load every sentence and paragraph: reader-relevant outcome first, qualification after ("Restart the service to apply the change", not "In order for the change to be applied, it will be necessary to...").
- Cut the padding tokens that inflate grade level without adding meaning: "in order to" becomes "to", "is able to" becomes "can", "it should be noted that" becomes nothing.

## Voice, tense, person

- Active voice by default: "the service returns 404", not "a 404 is returned". Passive is acceptable only when the actor is unknown or irrelevant ("the token is signed" — by design, no actor matters).
- Present tense: "the command creates a file", never "the command will create". Future tense breeds ambiguity about whether behavior is current or planned.
- Second person ("you") for instructions, imperative mood for steps ("Run the migration"), first person plural never ("we can now...").

## Terminology consistency

- One term per concept, project-wide. Choose "delete" or "remove", "repository" or "repo" — then hold the line; synonym variation reads as a distinction the reader must decode.
- Define every acronym at first use per page, maintain a project glossary, and link it rather than redefining terms inline.
- Product names keep their official casing everywhere: SurrealDB, OpenTelemetry, GitHub.
- Honor the workspace humanizer rules: direct, concise, senior-engineer tone; no emojis, icons, or conversational filler anywhere in documentation.

## Style linting in CI (Vale)

Prose gates run in CI beside the code gates, or they do not exist:

- **Vale** with the packaged style matching your chosen guide, plus a project style for house rules:

  ```ini
  # .vale.ini
  StylesPath = styles
  MinAlertLevel = suggestion
  Packages = Google
  [*.md]
  BasedOnStyles = Vale, Google, Solomon
  ```

- Encode the banned-filler list from `agents/AGENTS.md` ("Communication and tone") as an error-severity `existence` rule in the project style. Reference the list by pointer — do not quote the banned terms in prose, examples, or comments, because the CI gate matches substrings case-insensitively, so quoting a term (or using a derived or inflected form of it) fails the build. This file follows its own rule.

  ```yaml
  # styles/Solomon/Cliches.yml
  extends: existence
  message: "Banned filler term '%s'. See agents/AGENTS.md, Communication and tone."
  level: error
  ignorecase: true
  tokens:
    # populate from the ban list in agents/AGENTS.md; placeholder shown
    - utilize
  ```

- **markdownlint** (or `markdownlint-cli2`) for structural rules: single H1, no skipped heading levels, fenced code blocks with a language.
- **lychee** (or `markdown-link-check`) failing the build on broken links; run it per-PR for internal links and on a schedule for external ones, since external rot needs no diff.
- Readability thresholds are checkable too: Vale's metrics feature or a small `textstat` script can fail a page whose grade level or average sentence length exceeds the targets above.

Severity discipline: `error` blocks the merge (banned terms, broken links, missing language on fences); `warning` and `suggestion` inform but do not block, or authors will learn to ignore the tool entirely.

## Common pitfalls

- Enforcing style only through review comments; humans are inconsistent and expensive at this, linters are neither.
- Mixing two style guides, which produces contradictory feedback and teaches authors that the rules are negotiable.
- Passive voice hiding the actor in instructions ("the flag should be set") so the reader cannot tell who acts.
- Future tense for current behavior, leaving readers unsure whether a feature exists yet.
- Synonym churn — alternating terms for one concept — which readers parse as a real distinction.
- Quoting a banned term inside documentation or lint configuration examples, which trips the substring gate the rule exists to serve.
- Grade-level targets applied to reference tables, then "fixed" by padding entries into prose; reference is exempt from narrative readability targets.
- MinAlertLevel set so everything is a suggestion, making the linter decorative.

## Definition of done

- [ ] Exactly one published style guide is adopted and recorded; house rules from `agents/AGENTS.md` take precedence where they conflict.
- [ ] Guides and tutorials measure at grade 8 to 10, average sentence length under 25 words, paragraphs at five sentences or fewer.
- [ ] Instructions use active voice, present tense, second person, and imperative steps; passives survive only where no actor exists.
- [ ] One term per concept; acronyms defined at first use; the glossary is updated for any new term introduced.
- [ ] Vale runs in CI with the chosen package plus the project style; the banned-filler list is encoded as an error-severity rule by pointer, never quoted.
- [ ] markdownlint and a link checker gate the build; error-severity findings block merge.
- [ ] No emojis, icons, or filler terms appear anywhere in the change, including code comments and examples.
