## Technical SEO audit


Run on a schedule and before any major release.

- Crawl the site with Screaming Frog or Sitebulb. Flag: 4xx and 5xx URLs, redirect chains and loops, duplicate or missing titles and meta descriptions, missing or multiple H1s, missing `alt`, thin or duplicate content, canonical pointing to non-200 or non-canonical URLs, orphan pages, and mixed content.
- Google Search Console: review Page Indexing (coverage) for "Discovered/Crawled - currently not indexed" and "Excluded" reasons, the Core Web Vitals report, the Sitemaps report, manual actions, and security issues. Use URL Inspection to see how Google renders a specific page.
- Validate all structured data with the Rich Results Test and Schema Markup Validator.
- Check hreflang reciprocity and `x-default` coverage.
- Confirm one canonical host and protocol, HTTPS with a valid certificate, and that robots.txt does not block CSS, JS, or important sections.
- Run log-file analysis on large sites to see where crawl budget is actually spent and find waste on parameters and low-value URLs.
