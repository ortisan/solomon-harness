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
