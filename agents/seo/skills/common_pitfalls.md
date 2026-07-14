---
name: common-pitfalls
description: Lists indexing, rendering, and markup defects a reviewer rejects before they ship, from robots.txt Disallow-as-deindexing and lazy-loaded LCP images to non-reciprocal hreflang and structured data for invisible content, each paired with the mechanism that makes it harmful. Use when reviewing an SEO change for regressions or checking a template against the SEO definition-of-done checklist before merge.
---

# SEO Common Pitfalls

Indexing, rendering, and markup defects a reviewer rejects before they ship, from robots.txt misuse to structured data for invisible content. Each bullet pairs the mistake with the mechanism that makes it harmful.

## Common pitfalls


- Blocking a URL in robots.txt and expecting it to drop from the index. It will not; serve `noindex` on a crawlable URL instead.
- `noindex` plus `Disallow` on the same URL. Google cannot crawl it to see the `noindex`, so it can stay indexed.
- Lazy-loading the LCP image, which directly degrades LCP.
- Canonical that points to a redirected, noindexed, or 404 URL, which Google then ignores.
- Multiple H1s or skipped heading levels that blur the page's topic signal.
- 302 used for a permanent move, which slows consolidation of signals.
- Non-reciprocal hreflang, which is silently dropped.
- Soft 404s (a 200 status on a "not found" page) that bloat the index.
- Client-side-only content that crawlers never render.
- Marking up content in JSON-LD that is not visible on the page, risking a structured-data manual action.

## Definition of done

- [ ] Deindexing is done with a crawlable `noindex`, never with a robots.txt `Disallow`, and never both on the same URL.
- [ ] The LCP image is not lazy-loaded, verified in the shipped template.
- [ ] Every canonical points at a 200, indexable, non-redirected URL, confirmed by a crawl of the affected templates.
- [ ] Each page carries one H1 with no skipped heading levels.
- [ ] Permanent moves use 301, and every hreflang annotation is reciprocal in both directions.
- [ ] "Not found" states return a real 404 or 410, never a 200 soft 404.
- [ ] The money content is present in the initial HTML, checked with a no-JS fetch against the rendered DOM.
- [ ] All JSON-LD describes only content visible on the page.
