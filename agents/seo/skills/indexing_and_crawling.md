---
name: indexing-and-crawling
description: Sets concrete rules for controlling what search engines and AI crawlers fetch, render, and index under RFC 9309 — robots.txt semantics, sitemap and lastmod discipline, canonicalization and redirect hygiene, crawl budget, and the server-versus-client rendering decision. Use when editing robots.txt or sitemap generation, debugging a Search Console index-coverage state, or deciding whether a template needs server-side rendering.
---

# Indexing and Crawling Control

Concrete rules for controlling what search engines and AI crawlers fetch, render, and index: robots.txt semantics, sitemap discipline, canonicalization, crawl budget, and the SSR/CSR decision. The stance: crawling, rendering, and indexing are three separate pipelines with separate controls. Never use a crawl control to solve an indexing problem, and debug each stage in Search Console before touching the next.

## robots.txt semantics (RFC 9309)

The Robots Exclusion Protocol was standardized as RFC 9309 in September 2022; build to it, not to folklore.

- Matching: within the applicable `User-agent` group, the longest matching path wins; on an exact tie between `Allow` and `Disallow`, Google applies the least restrictive rule (`Allow`). `*` matches any character sequence, `$` anchors the end of the URL.
- Groups do not cascade. A `User-agent: Googlebot` group replaces the `*` group for Googlebot; it does not extend it. Repeat shared rules in the specific group.
- Google parses only the first 500 KiB of the file. Keep it small.
- Fetch-failure semantics are dangerous: a 4xx robots.txt means everything is allowed; a 5xx means Google initially treats the entire site as disallowed, and only after roughly 30 days falls back to the last cached copy. A broken edge function returning 500 on `/robots.txt` can silently stop sitewide crawling.
- robots.txt controls crawling, not indexing. A disallowed URL with inbound links can still be indexed URL-only ("Indexed, though blocked by robots.txt"). To deindex, the page must be crawlable and serve `noindex` via meta tag or `X-Robots-Tag`; `noindex` inside robots.txt has been unsupported since September 2019. Never combine `Disallow` with `noindex` on the same URL.
- Never block CSS, JS, or API endpoints the page needs to render; Google judges the rendered page.
- Decide AI-crawler policy explicitly, per bot: `GPTBot`, `OAI-SearchBot`, `ClaudeBot`, `PerplexityBot`, `CCBot`, `Google-Extended`. Blocking `Google-Extended` opts out of Gemini model training but does not affect Search ranking or AI Overviews, which draw from the normal Search index.

```
User-agent: *
Disallow: /search
Allow: /search/help        # longer path outranks /search
Disallow: /*?sessionid=    # kill a known crawl trap

Sitemap: https://www.example.com/sitemap-index.xml
```

## Sitemaps and lastmod discipline

Protocol limits: 50,000 URLs and 50 MB uncompressed per file; shard behind a sitemap index (itself up to 50,000 sitemap references).

- List only canonical, indexable, 200-status URLs. Every redirected, noindexed, or 404 URL in a sitemap wastes a fetch and pollutes coverage reports.
- `lastmod` is the only date field Google uses, and only while it stays verifiably accurate; `changefreq` and `priority` are ignored. Set `lastmod` from the content's real modification time (W3C datetime format), never from the build or deploy timestamp. A sitemap where every URL "changed" at each deploy teaches Google to distrust the field entirely.
- The sitemap ping endpoints were removed in January 2024. Submit via Search Console and the `Sitemap:` line in robots.txt.
- Segment sitemaps by template (`sitemap-products-1.xml`, `sitemap-articles.xml`) so index coverage can be read per segment in Search Console.

## Canonicalization

`rel=canonical` is a hint, not a directive. Google selects a canonical from converging signals: the tag, 301 redirects, internal links, sitemap membership, and hreflang. Make them agree.

- One host, one protocol: pick `https://www.example.com` (or the apex) and 301 every variant — http, non-www, trailing slash, uppercase — in a single hop. 301 for permanent moves, 302 only for genuinely temporary ones, 410 for deliberate permanent removal.
- Every indexable page carries exactly one absolute, self-referential canonical pointing at a 200, indexable URL. A canonical to a redirect or a noindexed URL is discarded and Google picks its own.
- Normalize tracking parameters (`utm_*`, `gclid`) with canonicals plus consistent internal linking. Internal links always point at the final canonical URL, never at a redirect or a parameterized variant.

## Crawl budget realities

Crawl budget is crawl capacity (how hard Google will hit the server) times crawl demand (how much it wants the URLs). Per Google's guidance it is a real constraint above roughly one million URLs, or above ~10,000 URLs with daily-changing content. Below that, a "crawl budget problem" is almost always a quality or discoverability problem.

- Capacity tracks server health: fast 200s raise it; 5xx responses and timeouts cut it.
- Support conditional requests (`ETag` / `If-Modified-Since` answered with 304) so recrawls of unchanged pages cost near nothing.
- Kill infinite URL spaces: faceted navigation, calendar pages, session IDs, internal search results. Constrain pure crawl traps with robots.txt, everything else with canonicals and by not linking to them.
- Log-file analysis is the ground truth for where budget goes; the GSC Crawl Stats report is the free approximation.

## JavaScript rendering and the SSR/CSR decision

Googlebot renders with an evergreen Chromium, but rendering is a second, queued phase — typically minutes behind the crawl, unbounded under load. Decision rule:

- Indexable, revenue-bearing content: server-side rendering or static generation. Content, links, canonicals, and JSON-LD must be present in the initial HTML response.
- Client-side rendering is acceptable only for logged-in or deliberately non-indexable surfaces.
- Dynamic rendering (bot-only prerendering) is deprecated as a long-term approach; treat it as a migration stopgap.
- The 2025-2026 reality: most AI and answer-engine crawlers (GPTBot, ClaudeBot, PerplexityBot) do not execute JavaScript. CSR-only content is invisible to them, so SSR is now a citation strategy, not just a Google one.
- Verify with URL Inspection's rendered HTML, and diff a plain `curl` fetch against the rendered DOM for the money content.

## Index coverage debugging in Search Console

Read the Page indexing report states as symptoms, in this order:

1. "Blocked by robots.txt" / "Excluded by noindex": intent check — is the exclusion deliberate?
2. "Discovered - currently not indexed": the crawl never happened; weak internal linking, sitemap-only orphans, or genuine budget limits.
3. "Crawled - currently not indexed": Google fetched it and declined; thin or duplicative content. Fix the content, not the plumbing.
4. "Duplicate, Google chose different canonical than user": conflicting signals; align canonical, internal links, sitemap, and hreflang.
5. "Soft 404": 200 responses on empty or error pages; return a real 404 or 410.

After a fix, confirm with a URL Inspection live test, then start "Validate fix" on the coverage issue and track it to completion.

## Common pitfalls

- Using `Disallow` to deindex: a blocked page cannot show its `noindex` and can stay indexed URL-only.
- `lastmod` stamped with the deploy time on every URL, which makes Google ignore the field.
- A 5xx on `/robots.txt` halting sitewide crawling for days before anyone notices.
- Canonical pointing at a redirect or noindexed URL; Google discards it.
- Internal links to redirecting or parameterized URLs, burning budget one hop at a time.
- Shipping the article body or product grid only via client-side fetch: delayed in Google, invisible to AI crawlers.

## Definition of done

- [ ] robots.txt is valid under RFC 9309 semantics, under 500 KiB, blocks no CSS/JS, carries a `Sitemap:` line, and states an explicit per-bot AI-crawler policy.
- [ ] Sitemaps list only canonical, indexable, 200-status URLs within the 50k/50MB limits, and `lastmod` reflects real content changes (spot-checked against page history).
- [ ] One host and protocol; all variants 301 in a single hop; the crawl shows zero new redirect chains or loops.
- [ ] Every indexable template emits exactly one absolute self-canonical to a 200 URL, asserted by a unit test.
- [ ] Indexable content, links, and JSON-LD are present in the initial HTML, verified by a curl-vs-rendered-DOM diff or URL Inspection.
- [ ] GSC Page indexing shows no new "not indexed", "Duplicate", or "Soft 404" regressions after the change, and "Validate fix" is running for anything repaired.
