# Metadata: Titles, Descriptions, Social Cards, Canonical and hreflang

Rules for the head of every indexable page. The stance: metadata is a rendering contract with three consumers — the SERP, social scrapers, and answer engines — and it is measured in pixels and eligibility rules, not character counts and hope. Every rule here is testable in a template unit test.

## Title and description: budget in pixels, not characters

Google truncates by rendered width, so the budget is pixels: characters are only a proxy that fails on wide glyphs ("W" renders about four times wider than "i").

- Title: roughly 580 px on desktop before ellipsis. That is about 55 characters of mixed-case English, fewer if the title is caps-heavy. Put the primary entity or query term first, brand suffix last (` | Brand`), and give every template a unique pattern.
- Meta description: roughly 920 px on desktop (about 155-160 characters) and about 680 px on mobile (about 120 characters). Write the first 120 characters to stand alone, because mobile is the render that counts under mobile-first indexing.
- Enforce the budget in CI: measure the string with a canvas or font-metrics library using a SERP-like font stack, and fail the test above budget, rather than counting characters.
- Rewrite reality: Google rewrites roughly 60% of titles and 70% of descriptions. Rewrites are triggered by over-length, keyword stuffing, and boilerplate duplication across a template. You reduce rewrites by removing the triggers, not by fighting the SERP.
- A description is not a ranking factor, but it is the default pitch in the SERP and a frequent source for answer-engine citations, so a missing or duplicated one wastes the slot twice.

## Open Graph and Twitter cards

Social scrapers and most chat-app unfurlers do not execute JavaScript: these tags must be server-rendered in the initial HTML.

- Open Graph minimum: `og:title`, `og:description`, `og:type`, `og:site_name`, `og:url` (absolute, and identical to the canonical), and `og:image` at 1200x630 (1.91:1), at least 200x200, under 8 MB, absolute HTTPS URL. Ship `og:image:width` and `og:image:height` so scrapers can lay out the card before downloading the image.
- Twitter/X: set `twitter:card` (usually `summary_large_image`) explicitly; the platform falls back to OG for title, description, and image, so only duplicate values that differ.
- Validate with the Facebook Sharing Debugger and LinkedIn Post Inspector; X retired its card validator preview, so test with a real post. Debuggers also force a re-scrape after a fix.
- An `og:url` that disagrees with the canonical splits share counts and confuses scrapers; generate both from the same helper.

## Canonical correctness matrix

One absolute `rel="canonical"` per page. The correct target depends on the page state:

| Page state | Canonical target |
| --- | --- |
| Unique indexable page | Self |
| Tracking/parameter variant (`?utm_...`) | The clean URL |
| A/B test variant URL | The control URL |
| Paginated page (`/category?page=3`) | Self — never page 1 |
| Faceted page not worth indexing | The base category, or `noindex` — pick one signal, not both |
| Syndicated copy on another host | The original article |
| PDF or non-HTML asset | `Link: <...>; rel="canonical"` HTTP header |

The target must always be a 200, indexable, non-redirecting URL, or Google ignores the hint.

## hreflang correctness matrix

- Codes: ISO 639-1 language, optionally plus ISO 3166-1 alpha-2 region — `en`, `en-gb`, `pt-br`. A bare region (`gb`) is invalid and silently dropped. Add one `x-default` for the language selector or global fallback.
- Reciprocity is mandatory: if page A lists B as an alternate, B must list A, or the pair is ignored.
- Every hreflang target must be a 200, indexable, self-canonical URL. hreflang and canonical must agree: canonicalizing `en-GB` to `en-US` while cross-referencing both breaks the whole cluster.
- Pick exactly one delivery channel — HTML `<link>` elements, HTTP headers, or the XML sitemap — and generate it from one source of truth. Sitemap delivery scales best past a handful of locales.

```html
<link rel="canonical" href="https://www.example.com/en-gb/pricing">
<link rel="alternate" hreflang="en-gb" href="https://www.example.com/en-gb/pricing">
<link rel="alternate" hreflang="en-us" href="https://www.example.com/en-us/pricing">
<link rel="alternate" hreflang="x-default" href="https://www.example.com/pricing">
```

## Pagination metadata

`rel=next`/`rel=prev` has been ignored by Google since 2019; do not ship it for SEO. Instead: each paginated page is self-canonical with a distinct title ("Category - Page 3"), stays indexable when it is the only crawl path to deep items, and links its neighbors with plain `<a href>`. Never canonicalize page N to page 1 — it hides everything past the first page — and avoid `noindex` on structural pagination, since long-noindexed pages eventually stop passing their links.

## Robots meta and snippet controls in the AI-answer era

Default is `index,follow` (no tag needed). Use `noindex` for removal, and the snippet directives to control both classic snippets and what AI Overviews may quote: `max-snippet`, `max-image-preview:large`, `max-video-preview`, `nosnippet`, and inline `data-nosnippet`. These are the supported opt-outs for AI Overviews content reuse; blocking `Google-Extended` affects Gemini training, not Overviews. `meta keywords` is dead, and `noarchive` is moot since Google removed cached links in 2024. Always ship `<meta name="viewport" content="width=device-width, initial-scale=1">`.

## Common pitfalls

- Counting characters instead of pixels, then shipping a 58-character caps-heavy title that truncates anyway.
- One boilerplate description across a template, which triggers mass rewrites and wastes the SERP pitch.
- `og:url` or OG tags injected client-side, so scrapers see an empty card.
- Non-reciprocal hreflang, or hreflang pointing at redirecting or noindexed URLs — silently dropped.
- Canonicalizing paginated pages to page 1, orphaning deep content.
- Two canonical tags emitted by competing plugins or layout components; Google ignores both.

## Definition of done

- [ ] Title and description are unique per page, within the pixel budgets (about 580 px title, 920 px desktop / 680 px mobile description), asserted by a width-measuring unit test.
- [ ] Exactly one absolute self- or matrix-correct canonical per page, target verified as a 200 indexable URL.
- [ ] OG set complete with a 1200x630 HTTPS image and `og:url` equal to the canonical; `twitter:card` set; all server-rendered and confirmed in a scraper debugger.
- [ ] hreflang clusters are reciprocal, use valid ISO codes plus `x-default`, target self-canonical 200 URLs, and are emitted from a single source of truth.
- [ ] Paginated pages are self-canonical, uniquely titled, and indexable; no `rel=next/prev` shipped as an SEO measure.
- [ ] Snippet-control directives (`max-snippet`, `max-image-preview`, `nosnippet`/`data-nosnippet`) match the business's AI-reuse policy, and viewport meta is present.
