## Mandatory competencies for this role


These come from the project rules and apply to every SEO change you make.

- TDD is mandatory. Before changing a template, helper, or build step, write a failing test that asserts the SEO output: a unit test that renders the head and asserts exactly one canonical tag, a snapshot of the JSON-LD block validated against its schema, or a parser assertion that there is exactly one `<h1>`. Red, green, refactor. Do not hand-verify in a browser as a substitute for a test.
- Mock all external services. Tests that touch Google Search Console, PageSpeed Insights, the URL Inspection API, a rank tracker, or a third-party crawler API must mock the HTTP layer. No test reaches the live network. Record fixtures for the Lighthouse JSON and CrUX responses you assert against.
- SOLID and modular design with clear contracts. Keep metadata generation, structured-data builders, and sitemap generation as separate, testable units. A `MetaTagBuilder` should not know how the sitemap is written.
- Preserve unrelated docstrings and comments. Touch only what the change requires.
- Branch-based workflow. Work on a `feature/<name>` or `bugfix/<name>` branch off `main`. Never commit SEO config (robots.txt, canonical rules, redirect maps) straight to `main`.
- Conventional Commits, imperative mood, under 72 characters on the first line, no emojis. Example: `fix(seo): point canonical to https origin to stop duplicate indexing`.
- Humanizer tone in every meta description, structured-data text field, PR, and comment. Direct and professional. No emoji, no filler.
- Lifecycle order. Conception (create the issue via `scripts/scrum-master.sh`), Planning (`PLAN.md` with target URLs, edge cases, and verification criteria), Execution (TDD), Verification (run the audit), Code Review (spec compliance first), Release and Documentation (sync the wiki via `scripts/wiki-sync.sh`).
