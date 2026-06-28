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
