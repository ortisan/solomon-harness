# Wiki Design and Presentation Standards

This skill establishes the structural patterns, naming conventions, and visual formatting rules for the project wiki: the sync model that makes `docs/wiki/` the source of truth, page naming and navigation, the standard page set, release-notes conventions, and the layout rules that keep pages credible and scannable.

## Sync model: the repo is the source of truth

The wiki is authored in `docs/wiki/*.md` inside the repository and published by `scripts/wiki-sync.sh`, which clones `<repo>.wiki.git`, copies the Markdown files in flat, commits, and pushes. Consequences that shape how you work:

- Never edit pages in the GitHub wiki UI; the next sync overwrites them. All wiki changes are pull requests against `docs/wiki/`, reviewed like any docs change.
- The sync is flat: subdirectories under `docs/wiki/` are not copied. Every page is a top-level `.md` file.
- GitHub only creates the wiki content repository after the first page is saved through the web UI. The script detects an uninitialized wiki via `solomon_harness.wiki_bootstrap detect` and exits with code 4 and an actionable message instead of a raw git error; with no git remote configured it degrades to mock mode and copies the files to `tmp/wiki-mock-verification` for inspection.
- Sync runs in the Release and Documentation stage; a release is not done until the wiki reflects it.

## Page naming and navigation

- Page files use Title-Case-With-Hyphens (`Quick-Start.md`, `Release-Notes.md`, `Release-0.11.0.md`); the filename becomes the wiki page URL and title.
- Internal links use the page name without the `.md` extension — `[Features](Features)` — which is how the GitHub wiki resolves links; extension-suffixed links render in repo browsing but break as wiki navigation.
- `_Sidebar.md` is the navigation rail: a single list with Home first, then the developer-first pages (Quick Start, Commands Reference, Features), business and deep technical references after, and Release History and the Design System last. Every page in `docs/wiki/` appears in the sidebar or is reachable from Home; a page reachable from nowhere is dead weight.

## Standard page set and page patterns

Every repository wiki carries a consistent set, each with a defined job:

- **`Home.md` (business-first):** the project's vision, core objectives, and business value proposition first — never codebase details or dependency logs. Use a high-level Mermaid flowchart to present the value stream, then a documentation index that places the Quick Start Guide and the Features/Technical Overview at the top: developers need onboarding and capability summaries immediately, while business constraints and deep references belong further down.
- **`Quick-Start.md` (onboarding):** a sequential setup guide covering prerequisites, environment setup, database configuration, and running the first cycle.
- **`Features.md` (condensed capabilities):** group technical capabilities into cohesive, user-facing feature sets that solve specific problems; never a pulverized list of individual functions or files.
- **`Release-Notes.md` and `Delivered.md`:** the release history, per the conventions below.
- **`Design-System.md`:** the wiki's own presentation standards, so contributors keep pages consistent.

## Release notes conventions

Three artifacts share the release story, newest first in all of them:

- **`Release-Notes.md`** is the consolidated history: one `### vX.Y.Z (date)` section per release with one to three bolded capability bullets written for users, followed by the standing release-policy section. It links to the Delivered log for the full detail.
- **`Delivered.md`** is the per-issue log: a single table with columns Date, Issue, Title, Version, and PR, where every issue and PR number is a clickable GitHub link.
- **`Release-<version>.md`** pages carry the business problem (milestone and goals) and the technical changes for one version, linked from `Release-Notes.md`.

Versions follow the milestone-gated SemVer policy (`docs/release-policy.md`, ADR-0004): the wiki records what shipped and never announces a tag before the release PR merges.

## Visual design and layout

- **Mermaid flowcharts** visualize workflows, data flows, and state machines; quote node labels containing special characters. Prefer a diagram to a wall of prose for any multi-step process.
- **Markdown tables** compare features, backend behaviors, or roles, and always carry a valid separator row (`| --- | --- |`) immediately below the header, or GitHub breaks the layout.
- **GitHub alert callouts** (`> [!NOTE]`, `> [!IMPORTANT]`, `> [!TIP]`) flag critical requirements, optimization notes, and safety warnings; use them sparingly so they retain force.
- **Clickable issue and PR links:** every referenced issue (`[#53](https://github.com/<owner>/<repo>/issues/53)`) and PR (`[#77](https://github.com/<owner>/<repo>/pull/77)`) is a Markdown link, never raw `#53` text.
- **No comma-separated entity lists:** technologies, agents, and similar enumerations are ordered or unordered Markdown lists, never inline comma strings.
- **No emojis or icons** anywhere; the tone is direct, senior-engineer prose per the workspace humanizer rules.

## Common pitfalls

- Editing the wiki through the GitHub UI, silently reverted by the next `wiki-sync.sh` run.
- Placing pages in subdirectories of `docs/wiki/`, which the flat sync never publishes.
- Internal links with the `.md` extension, which look fine in the repo and break in the wiki.
- Adding a page without a `_Sidebar.md` entry or a Home index link, leaving it unreachable.
- Business/tech bleed: schema details and dependency mechanics on the landing page, diluting the value proposition.
- Pulverized feature lists — disjointed functions instead of grouped, user-facing capabilities.
- Raw `#53` issue text, missing table separator rows, or comma-separated entity strings.
- Documenting a version in the wiki before the release PR merges, so the wiki claims a tag that does not exist.

## Definition of done

- [ ] All changes were made in `docs/wiki/` (flat, Title-Case-With-Hyphens filenames) and published via `scripts/wiki-sync.sh`; no direct wiki-UI edits.
- [ ] The wiki contains the standard set: business-first `Home.md`, `Quick-Start.md`, `Features.md`, `Release-Notes.md`, `Delivered.md`, and `Design-System.md`.
- [ ] Internal links are extension-free page-name links, and every page is reachable from `_Sidebar.md` or Home.
- [ ] A release adds its `Release-Notes.md` section, its `Delivered.md` rows, and a linked `Release-<version>.md` page, all with clickable issue and PR links, only after the release merges.
- [ ] Complex processes are Mermaid diagrams, tables carry separator rows, and no comma-separated entity lists remain.
- [ ] No emojis, icons, or banned filler terms appear on any page.
