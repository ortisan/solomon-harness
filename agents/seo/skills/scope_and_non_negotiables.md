---
name: scope-and-non-negotiables
description: Defines the SEO role's scope and non-negotiables — semantic hierarchy, metadata, structured data, indexing and crawling control, and Core Web Vitals, delivered through mandatory TDD, mocked external SEO APIs, modular contracts, and the branch-and-lifecycle workflow. Use when starting any SEO task to confirm it falls in scope, or checking a change against the mandatory TDD and lifecycle rules before it ships.
---

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

## Common pitfalls

- A template or metadata helper changed without a prior failing test asserting the SEO output — the TDD mandate is explicit that a browser spot-check never substitutes for a test.
- Tests calling live Search Console, PageSpeed Insights, or CrUX endpoints instead of recorded fixtures — nondeterministic, and a breach of the mock-the-HTTP-layer rule.
- Metadata generation, structured-data building, and sitemap writing tangled into one unit — the contracts blur and none of the three can be tested or replaced in isolation.
- robots.txt, canonical rules, or redirect maps committed straight to `main` — SEO config that skips the `feature/`/`bugfix/` branch review can deindex a site in one push.
- A commit like "update meta tags" without a Conventional Commit type and scope, breaking the changelog trail and the under-72-character rule.
- Execution started with no issue from `scripts/scrum-master.sh` and no `PLAN.md` naming target URLs and verification criteria, so the audit stage has nothing to verify against.
- Meta descriptions or structured-data text written in filler tone instead of the direct humanizer register the scope requires.

## Definition of done

- [ ] The change stayed within this role's scope — semantic hierarchy, metadata, structured data, indexing and crawling control, Core Web Vitals, or the audit — and anything else was handed off.
- [ ] A failing test asserting the SEO output (canonical count, single `<h1>`, valid JSON-LD) existed before the implementation change and now passes.
- [ ] Every external SEO or analytics API in the suite is mocked, with fixtures recorded for the Lighthouse and CrUX JSON asserted against.
- [ ] Metadata, structured-data, and sitemap logic remain separate, individually testable units with clear contracts.
- [ ] Work ran on a `feature/<name>` or `bugfix/<name>` branch with Conventional Commit messages: imperative mood, first line under 72 characters, no emojis.
- [ ] The lifecycle order held: issue, `PLAN.md` with target URLs and verification criteria, TDD execution, audit verification, spec-first review, release and wiki sync via `scripts/wiki-sync.sh`.
- [ ] All user-facing text — descriptions, structured-data fields, PR — reads in the humanizer tone with no filler.
