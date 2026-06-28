## Metadata


- Title tag: unique per page, roughly 50 to 60 characters (target under ~580 px) so it does not truncate in the SERP. Put the primary term near the front.
- Meta description: roughly 150 to 160 characters, unique, written for click-through. It is not a ranking factor, but a missing or duplicated one wastes a result slot.
- One self-referential `rel="canonical"` per page, absolute URL, on the protocol and host you want indexed. Canonical must point to a 200, indexable, non-redirecting URL.
- Robots meta and `X-Robots-Tag` header: `index,follow` by default; `noindex` to remove a page from the index. Use directives such as `max-image-preview:large`, `max-snippet:-1`, `max-video-preview:-1` where you want richer previews.
- Viewport: `<meta name="viewport" content="width=device-width, initial-scale=1">`. Mobile-first indexing means the mobile render is the one Google judges.
- OpenGraph: `og:title`, `og:description`, `og:type`, `og:url` (absolute, canonical), `og:site_name`, and `og:image` at 1200x630 (1.91:1), under 8 MB, served over HTTPS with an absolute URL.
- Twitter Cards: `twitter:card` (usually `summary_large_image`), `twitter:title`, `twitter:description`, `twitter:image`. The platform falls back to OG tags, so do not duplicate values you can inherit, but set `twitter:card` explicitly.
- hreflang for multi-language or multi-region sites: `rel="alternate" hreflang="en-us"` plus an `x-default`. Annotations must be reciprocal and use absolute URLs; a non-reciprocal hreflang is ignored.
