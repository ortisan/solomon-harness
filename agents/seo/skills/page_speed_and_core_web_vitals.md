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
