# Wiki Design and Presentation Standards

Establishes structural patterns and visual formatting rules for business-facing landing pages, technical summaries, and release logs.

## Wiki Architecture and Page Patterns

All repository wikis must follow a unified page pattern that balances high-level business goals with detailed technical implementation:

- **Home Page (Business-First):** Must describe the project's vision, core objectives, and business value proposition first. Never start with codebase details or complex dependency logs. Use high-level flowcharts to present the value stream.
- **Developer-First Navigation Index:** On the `Home.md` page, the index directory MUST place the **Quick Start Guide** and **Features/Technical Overview** at the very top of the list. Developer onboarding and capability summaries are high-priority pages that developers need immediately, whereas business constraints and deep technical references belong further down.
- **Features Page (Condensed Capabilities):** Avoid pulverized list-of-features sections. Group technical capabilities into cohesive, user-facing feature sets (powers) that solve specific user problems.
- **Quick Start Page (Onboarding):** Present a sequential setup guide covering prerequisites, environment setup, database configuration, and running the first cycle.
- **Release History Page (Changelog):** Maintain a chronological history of major and minor versions linking to a detailed delivered-issues log.

## Visual Design and Layout

To convey credibility and professional authority, documentation must employ clean layouts and structured visual elements:

- **Mermaid Flowcharts:** Use Mermaid flow diagrams to visualize workflows, data flows, and state machines. Ensure node labels are clear and quoted if they contain special characters.
- **Structured Data Tables:** Use Markdown tables to compare features, backend behaviors, or user roles.
- **GitHub Alert Callouts:** Utilize Markdown callouts (e.g., `> [!NOTE]`, `> [!IMPORTANT]`, `> [!TIP]`) to draw attention to critical requirements, optimization tips, or safety notices.
- **Clickable Issue and PR Links:** Any issue number (e.g., `[#53](https://github.com/<owner>/<repo>/issues/53)`) and PR number (e.g., `[#77](https://github.com/<owner>/<repo>/pull/77)`) referenced in documentation indexes, release notes, or delivered logs must be formatted as clickable markdown links to their respective GitHub URLs.
- **No Comma-Separated Lists:** Never list entities (such as technologies or agents) as comma-separated lists. Always present them as ordered or unordered markdown lists.
- **Markdown Table Separator:** When creating or modifying tables, always ensure a valid separator row (e.g., `| --- | --- |`) is present immediately below the column headers to prevent layout failures.
- **No Emojis or Icons:** Keep all documentation completely free of emojis, visual ornaments, or informal icons, maintaining a direct, senior-engineer style.

## Common pitfalls

- **Pulverized Feature Lists:** Creating disjointed lists of individual functions or files without grouping them into functional, user-facing capabilities.
- **Business/Tech Bleed:** Explaining deep code mechanics (e.g. database schema details) directly on the landing page, diluting the business value proposition.
- **Broken Navigation Links:** Using hardcoded URLs or broken links between wiki pages instead of relative links (e.g., `[Features](Features.md)`).
- **Unlinked Issues/PRs:** Writing raw `#53` or `#77` text without wrapping them in clickable GitHub links in delivered logs or release pages.
- **Missing Table Separators:** Leaving out the divider row, which breaks table layout on GitHub.

## Definition of done

- [ ] Every wiki contains a business-focused `Home.md`, a technical `Features.md`, a step-by-step `Quick-Start.md`, a `Release-Notes.md`, and a `Design-System.md`.
- [ ] No emojis, icons, or flowery AI cliches appear on any documentation page.
- [ ] Complex processes are visualized using Mermaid diagrams rather than large walls of prose.
- [ ] All issue and PR references are formatted as clickable GitHub Markdown links.
- [ ] Tables are formatted with a correct divider row, and no comma-separated inline strings are used for lists.
