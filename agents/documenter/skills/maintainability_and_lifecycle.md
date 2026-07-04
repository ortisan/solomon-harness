# Maintainability and Lifecycle

This skill governs how documentation stays true after it ships: ownership, review cadence, staleness detection, docs tested mechanically in CI, deprecation notices, and deliberate deletion. The stance: documentation decays by default — code changes and prose does not — so correctness over time is an engineered property with owners, dates, and failing builds, not a hope.

## Ownership

- Every page names an owner in its front matter. Prefer a team or role over an individual; people leave, roles persist. An unowned page is unmaintained by definition — assign it or delete it.
- Route documentation review mechanically: a `CODEOWNERS` entry for the docs paths ensures the owning team sees every change to its pages, the same way code review routes.
- Ownership means accountability for accuracy, not exclusive write access. Anyone fixes a doc bug; the owner answers for the page being right.

## Review cadence and staleness markers

- Every page carries `last_reviewed` (ISO date) in front matter. A review means re-running the commands, re-checking versions and links against the current release, and bumping the date — not skimming.
- Re-validate each page at least every 90 days. At 180 days past `last_reviewed`, the page is stale: it gets a visible staleness banner and is removed from the "current" navigation until reviewed.
- Automate the sweep: a small script (CI job or scheduled task) lists pages ordered by `last_reviewed` and files an issue for each page crossing the threshold, assigned to the owner. Staleness that depends on someone remembering to check is not a control.
- High-churn pages (quickstarts, install guides) deserve a tighter cadence than slow-moving explanation pages; set the threshold per directory if the tooling allows, but never beyond 180 days.

## Docs tested in CI

Prose cannot be unit-tested, but most of what makes docs wrong can be:

- **Code examples execute.** Python examples run under doctest (`pytest --doctest-modules`, or doctest blocks in the docs themselves); standalone snippets are extracted from fenced blocks and executed against a sandbox in CI. An example that stops compiling fails the build the day it breaks, not the day a user pastes it.
- **Links are checked.** `lychee` runs per-PR for internal links and on a schedule (weekly) for external links, because external rot arrives without a diff to trigger on.
- **Structure and style are linted.** markdownlint and Vale gate every docs PR, as defined in the readability skill.
- **Generated content regenerates.** API reference, CLI help dumps, and diagrams-as-code are rebuilt in CI and diffed; a drifted committed artifact fails the build.

## Deprecation notices

- The moment a feature's removal is announced, its pages get a deprecation notice at the top: `status: deprecated` in front matter, a visible banner stating the replacement (linked) and the removal date.
- Keep deprecated pages published until the removal date — users on old versions still need them — then replace each with a redirect or stub pointing at the replacement so inbound links keep working.
- Record the deprecation in the changelog under Deprecated at announcement time and under Removed when it lands, with the migration steps linked from both.

## Deletion and repair

- Delete what you cannot keep current; a short, correct corpus beats a large, stale one. Git history preserves the content, and a stub or redirect preserves the URL.
- Treat a doc bug like a code bug: file an issue, fix at the source (never patch a downstream copy of a single-sourced fact), verify the example or link, close with the fix referenced.

## Lifecycle integration in this repo

- Documentation is part of the Release and Documentation stage: a release is not done until its docs and changelog are updated and the wiki is synced with `scripts/wiki-sync.sh`.
- Persist documentation decisions and structural changes to project memory (`save_decision`, `log_handoff`) so the next agent inherits the rationale instead of re-deriving it.

## Common pitfalls

- Pages owned by a person who left a year ago; ownership must be re-assigned on departure, which is why teams own pages.
- `last_reviewed` bumped without re-running anything — a fresh date on wrong content is worse than an honest stale banner.
- Staleness policy that exists only as prose, with no automated sweep; nobody re-reads policy pages either.
- Examples "tested" once at writing time and never executed again; only CI execution catches the break that the next release causes.
- Link checking only on PRs, so external links rot silently between edits.
- Deleting deprecated pages at announcement instead of at removal, stranding users on supported old versions.
- Removing a page without a redirect or stub, breaking every inbound link and bookmark at once.
- Fixing a wrong value in one copy while the single-source original still emits the error everywhere else.

## Definition of done

- [ ] Every touched page has an owner (team or role) in front matter, and `CODEOWNERS` routes its reviews.
- [ ] `last_reviewed` is current and reflects an actual re-validation: commands re-run, versions and links checked.
- [ ] The automated staleness sweep covers the page set; pages past 180 days carry a banner and are out of primary navigation.
- [ ] Code examples execute in CI (doctest or extracted snippets); the link checker passes per-PR and runs on a schedule for external links.
- [ ] Generated artifacts (reference, CLI dumps, diagrams) are rebuilt and diffed in CI; no drifted committed output.
- [ ] Deprecated pages carry the banner, replacement link, and removal date; removed pages leave redirects; the changelog records both events.
- [ ] Release docs and changelog are updated and the wiki is synced via `scripts/wiki-sync.sh` before the release is called done.
- [ ] Documentation decisions and structure changes are recorded in project memory.
