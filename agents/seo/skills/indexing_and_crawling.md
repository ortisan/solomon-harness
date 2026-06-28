## Indexing and crawling


- robots.txt controls crawling, not indexing. A URL disallowed in robots.txt can still appear in the index if it is linked. To remove a page from the index, serve `noindex` and make sure the page is crawlable so Google can see that directive. Never combine `Disallow` with `noindex` on the same URL.
- Do not block CSS or JS in robots.txt. Google needs them to render and judge the page. `noindex` inside robots.txt is unsupported and ignored.
- Reference the sitemap from robots.txt with a `Sitemap:` line using an absolute URL.
- XML sitemap limits: 50,000 URLs and 50 MB uncompressed per file; split larger sets behind a sitemap index. List only canonical, indexable, 200-status URLs. Include accurate `lastmod`. Remove noindexed, redirected, and 404 URLs from the sitemap.
- Redirects: use 301 for permanent moves, 302 only for genuinely temporary ones. Eliminate redirect chains and loops; each hop costs crawl budget and link equity. Use 410 to signal permanent removal when appropriate.
- Canonicalization: pick one host (www vs non-www) and one protocol (HTTPS), and 301 the rest. Normalize trailing slashes, casing, and tracking parameters.
- Avoid crawl traps: faceted navigation, calendar pages, session IDs, and infinite parameter combinations. Constrain them with canonicals, `noindex`, or parameter handling.
- Pagination: Google no longer uses `rel=next`/`rel=prev`. Give each page a distinct, crawlable, self-canonical URL with real content.
- JavaScript SEO: prefer server-side rendering or static generation for indexable content. Client-only rendering delays or blocks indexing. Confirm rendered output with the URL Inspection tool's rendered HTML, not just the view source.
- HTTPS everywhere, no mixed content. Internal links should point at the final canonical URL, not at a redirect.
