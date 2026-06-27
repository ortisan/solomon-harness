# SEO Best Practices

Reference standard for the SEO specialist: ship pages that crawlers can reach, render, understand, and rank, with measurable indexability and Core Web Vitals targets.

## Scope and mandate

This skill covers the SEO role's duties: semantic HTML hierarchy, metadata (OpenGraph, JSON-LD, Twitter Cards), structured data, indexing and crawling control (robots.txt, sitemaps, canonicals), page speed and Core Web Vitals, and technical SEO audits. Every recommendation here is a verifiable change with a named tool to confirm it.

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

## Semantic HTML hierarchy

- Exactly one `<h1>` per page that describes the page's primary topic and matches search intent. Browsers never implemented the HTML5 document-outline algorithm, so heading rank is taken literally. Treat headings as a flat outline.
- Do not skip heading levels. `h1` then `h2` then `h3`. An `h4` directly under an `h1` is a defect.
- Use landmark elements, not `<div>` soup: one `<main>`, plus `<header>`, `<nav>`, `<article>`, `<section>`, `<aside>`, `<footer>`. One `<main>` per page.
- Descriptive link anchor text. No "click here", "read more", or bare URLs as the only anchor. Internal links should carry the target topic in the text.
- Every meaningful image needs an `alt` that describes content or function; decorative images get `alt=""`. Do not keyword-stuff alt text.
- Set `<html lang="...">`. Add `dir` for right-to-left content.
- Keep primary content in server-rendered HTML. Content that appears only after a click, hover, or client-side fetch is content Google may never index.

## Metadata

- Title tag: unique per page, roughly 50 to 60 characters (target under ~580 px) so it does not truncate in the SERP. Put the primary term near the front.
- Meta description: roughly 150 to 160 characters, unique, written for click-through. It is not a ranking factor, but a missing or duplicated one wastes a result slot.
- One self-referential `rel="canonical"` per page, absolute URL, on the protocol and host you want indexed. Canonical must point to a 200, indexable, non-redirecting URL.
- Robots meta and `X-Robots-Tag` header: `index,follow` by default; `noindex` to remove a page from the index. Use directives such as `max-image-preview:large`, `max-snippet:-1`, `max-video-preview:-1` where you want richer previews.
- Viewport: `<meta name="viewport" content="width=device-width, initial-scale=1">`. Mobile-first indexing means the mobile render is the one Google judges.
- OpenGraph: `og:title`, `og:description`, `og:type`, `og:url` (absolute, canonical), `og:site_name`, and `og:image` at 1200x630 (1.91:1), under 8 MB, served over HTTPS with an absolute URL.
- Twitter Cards: `twitter:card` (usually `summary_large_image`), `twitter:title`, `twitter:description`, `twitter:image`. The platform falls back to OG tags, so do not duplicate values you can inherit, but set `twitter:card` explicitly.
- hreflang for multi-language or multi-region sites: `rel="alternate" hreflang="en-us"` plus an `x-default`. Annotations must be reciprocal and use absolute URLs; a non-reciprocal hreflang is ignored.

## Structured data

- Use JSON-LD. It is Google's recommended format and keeps markup out of the rendered DOM. Avoid Microdata and RDFa for new work.
- Use the schema.org vocabulary and only the types that match visible page content. Marking up content that is not on the page is a spam signal and can trigger a manual action.
- Common, eligibility-bearing types: `Organization` and `WebSite` (site identity), `BreadcrumbList` (breadcrumb trail), `Article` / `NewsArticle`, `Product` with `Offer` and `AggregateRating`, `Recipe`, `Event`, `VideoObject`, `LocalBusiness`. Fill all required and as many recommended properties as the page truthfully supports.
- Know the current eligibility rules: `FAQPage` and `HowTo` rich results were heavily restricted in 2023 (FAQ is limited to authoritative health and government sites; HowTo was retired from results), and the `WebSite` sitelinks search box was deprecated in late 2024. Mark up only what can actually win a result.
- Validate every block with the Rich Results Test (search.google.com/test/rich-results) for eligibility and the Schema Markup Validator (validator.schema.org) for syntax. Both must pass with zero errors before merge.
- Keep `@id` references stable so entities link across pages (for example, the same `Organization` `@id` referenced from `Article.publisher`).

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

## Page speed and Core Web Vitals

Core Web Vitals are assessed at the 75th percentile of real users (field data in CrUX). Targets:

- LCP (Largest Contentful Paint): good <= 2.5 s, needs improvement 2.5 to 4.0 s, poor > 4.0 s.
- INP (Interaction to Next Paint): good <= 200 ms, needs improvement 200 to 500 ms, poor > 500 ms. INP replaced FID in March 2024; do not optimize for FID anymore.
- CLS (Cumulative Layout Shift): good <= 0.1, needs improvement 0.1 to 0.25, poor > 0.25.
- Supporting targets: TTFB < 800 ms, FCP < 1.8 s. TBT is the lab proxy for INP.

Concrete techniques:

- LCP: identify the LCP element (usually the hero image or H1 block). Serve it from the document HTML, `preload` it, set `fetchpriority="high"`, and never lazy-load it. Cut TTFB with caching, a CDN, and HTTP/2 or HTTP/3.
- Images: serve AVIF or WebP, use `srcset`/`sizes` for responsive delivery, set explicit `width` and `height` (or `aspect-ratio`) on every image and embed to prevent layout shift, and add `loading="lazy"` to below-the-fold images only.
- CLS: reserve space for images, ads, embeds, and late-loading UI. Use `font-display: swap` and `preload` self-hosted fonts to avoid invisible-text and reflow. Avoid inserting content above existing content after load.
- INP/TBT: split and defer JavaScript, remove unused code (tree shaking, code splitting), break up long tasks, and minimize third-party scripts. `async`/`defer` non-critical scripts.
- Render path: inline critical CSS, defer the rest, minify, and compress with Brotli or Gzip. `preconnect` to required third-party origins.
- Measure field data with CrUX and PageSpeed Insights; use Lighthouse and WebPageTest for lab diagnosis. Lab scores guide fixes, but the pass/fail verdict is the field 75th percentile.

## Technical SEO audit

Run on a schedule and before any major release.

- Crawl the site with Screaming Frog or Sitebulb. Flag: 4xx and 5xx URLs, redirect chains and loops, duplicate or missing titles and meta descriptions, missing or multiple H1s, missing `alt`, thin or duplicate content, canonical pointing to non-200 or non-canonical URLs, orphan pages, and mixed content.
- Google Search Console: review Page Indexing (coverage) for "Discovered/Crawled - currently not indexed" and "Excluded" reasons, the Core Web Vitals report, the Sitemaps report, manual actions, and security issues. Use URL Inspection to see how Google renders a specific page.
- Validate all structured data with the Rich Results Test and Schema Markup Validator.
- Check hreflang reciprocity and `x-default` coverage.
- Confirm one canonical host and protocol, HTTPS with a valid certificate, and that robots.txt does not block CSS, JS, or important sections.
- Run log-file analysis on large sites to see where crawl budget is actually spent and find waste on parameters and low-value URLs.

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

- Page has exactly one `<h1>`, no skipped heading levels, and correct landmark elements; verified by an automated parser test.
- Title (50 to 60 chars), meta description (150 to 160 chars), and a single self-referential canonical to a 200 URL are present and unique.
- OpenGraph and Twitter Card tags are complete with an absolute, 1200x630 HTTPS image.
- All JSON-LD passes the Rich Results Test and Schema Markup Validator with zero errors and reflects only on-page content.
- robots.txt does not block CSS/JS, references the sitemap, and the sitemap lists only canonical 200 URLs with accurate `lastmod`.
- No redirect chains, loops, 4xx, 5xx, or mixed content introduced by the change; confirmed by a crawl.
- Field Core Web Vitals meet targets at the 75th percentile: LCP <= 2.5 s, INP <= 200 ms, CLS <= 0.1.
- Tests are written first, pass, and mock every external SEO/analytics API.
- Change is on a `feature/*` or `bugfix/*` branch with a Conventional Commit message and a humanizer-style PR description.
