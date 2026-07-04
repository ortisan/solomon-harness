# SEO Best Practices

Ship pages that crawlers, both search engines and AI answer engines, can reach, render, understand, and rank, with measurable indexability and Core Web Vitals targets. Every recommendation in this agent's skills is a verifiable change with a named tool to confirm it.

## Scope and non-negotiables

This skill set governs the SEO role's duties: semantic HTML hierarchy, metadata (titles, descriptions, Open Graph, Twitter cards, canonical, hreflang), structured data (JSON-LD), indexing and crawling control (robots.txt, sitemaps, redirects, canonicalization), page speed and Core Web Vitals, and the technical SEO audit.

Mandatory competencies from the project rules, made concrete for this role:

- TDD is mandatory. Before changing a template, helper, or build step, write the failing test that asserts the SEO output: exactly one canonical tag, exactly one `<h1>`, a JSON-LD block that validates against its schema. Red, green, refactor. A browser spot-check never substitutes for a test.
- Mock all external services. Tests that touch Google Search Console, PageSpeed Insights, the URL Inspection API, CrUX, or a third-party crawler API mock the HTTP layer. Record fixtures for the Lighthouse and CrUX JSON you assert against.
- SOLID and modular design with clear contracts. Metadata generation, structured-data builders, and sitemap generation are separate, testable units. A `MetaTagBuilder` does not know how the sitemap is written.
- Preserve docstrings and comments unrelated to the current change.
- Branch-based workflow: `feature/<name>` or `bugfix/<name>` off `main`. Never commit SEO config (robots.txt, canonical rules, redirect maps) straight to `main`.
- Conventional Commits, imperative mood, first line under 72 characters, no emojis. Example: `fix(seo): point canonical to https origin to stop duplicate indexing`.
- Humanizer tone in every meta description, structured-data text field, PR, and comment. Direct and professional; no filler.
- Lifecycle order: issue via `scripts/scrum-master.sh`, `PLAN.md` with target URLs and verification criteria, TDD execution, audit verification, code review against the spec, release and wiki sync via `scripts/wiki-sync.sh`.
