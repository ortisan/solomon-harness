# SEO Definition of Done

The acceptance gate for an SEO change: semantic structure, metadata, structured data, crawl health, and field Core Web Vitals must all verify before it ships. A lab score alone closes nothing here; the field p75 and a post-change crawl are the verdicts.

## Common pitfalls

- Metadata declared done from a visual spot-check with no automated parser test asserting the single `<h1>`, heading order, and canonical count — the next template edit regresses it silently.
- Title and description lengths never checked against the 50-60 and 150-160 character bands, so SERPs truncate or rewrite them.
- JSON-LD that passes the Rich Results Test while marking up content not visible on the page — the validator is green, the manual-action risk remains.
- Core Web Vitals claimed from a lab Lighthouse run instead of field p75 against LCP <= 2.5 s, INP <= 200 ms, CLS <= 0.1 — lab data is diagnosis, not the verdict.
- The post-change crawl skipped after touching redirects or canonicals, letting chains, loops, or mixed content ship undetected.
- The sitemap left listing redirected or noindexed URLs after the change, polluting index coverage reports.
- Tests that hit live GSC or PageSpeed APIs instead of mocked fixtures — nondeterministic, and a violation of the mock-every-external-API rule.

## Definition of done


- Page has exactly one `<h1>`, no skipped heading levels, and correct landmark elements; verified by an automated parser test.
- Title (50 to 60 chars), meta description (150 to 160 chars), and a single self-referential canonical to a 200 URL are present and unique.
- OpenGraph and Twitter Card tags are complete with an absolute, 1200x630 HTTPS image.
- All JSON-LD passes the Rich Results Test and Schema Markup Validator with zero errors and reflects only on-page content.
- robots.txt does not block CSS/JS, references the sitemap, and the sitemap lists only canonical 200 URLs with accurate `lastmod`.
- No redirect chains, loops, 4xx, 5xx, or mixed content introduced by the change; confirmed by a crawl.
- Field Core Web Vitals meet targets at the 75th percentile: LCP <= 2.5 s, INP <= 200 ms, CLS <= 0.1.
- Tests are written first, pass, and mock every external SEO/analytics API.
- Change is on a `feature/*` or `bugfix/*` branch with a Conventional Commit message and a humanizer-style PR description.
