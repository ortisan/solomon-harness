---
name: performance-target-core-web-vitals-good
description: Sets performance budgets for holding Core Web Vitals at "good" at the 75th percentile of real field traffic, enforced as CI failures, with optimization driven by field data over lab data. Use when adding a page, image, or script that could affect load performance, or reviewing a budget failure.
---

# Performance (Target: Core Web Vitals "Good")

This skill sets the performance budgets and the discipline for meeting them: every user-facing page holds Core Web Vitals "good" at the 75th percentile of real field traffic, budgets are enforced as CI failures rather than warnings, and optimization follows measurement — field data decides what is slow, lab data prevents regressions.

## Budgets

Field thresholds at p75, mobile included (Google's "good" bar):

- LCP (Largest Contentful Paint) <= 2.5 s — loading.
- INP (Interaction to Next Paint) <= 200 ms — responsiveness; INP replaced FID in March 2024, and it scores the worst interaction, not the first.
- CLS (Cumulative Layout Shift) <= 0.1 — visual stability.

Static resource budgets, enforced in CI:

- Initial route JS <= 200 KB gzipped (React 19 `react` + `react-dom` cost about 45 KB of that; a router and query client another 20-30 KB, so application code gets what remains).
- Any lazy route chunk <= 100 KB gzipped; total CSS <= 60 KB gzipped; LCP-candidate images <= 200 KB.
- Enforce with `size-limit` or bundle-analyzer diffs in CI for React, and `budgets` in `angular.json` for Angular (set `"type": "initial", "maximumWarning": "350kb", "maximumError": "500kb"` rather than keeping the loose defaults). A budget that only warns is a budget nobody reads.

## LCP under 2.5 s

- Identify the LCP element per page (usually the hero image or heading) and treat it specially: server-render it, never lazy-load it, and mark the image `fetchpriority="high"` with a `preload` if it is discovered late.
- TTFB feeds LCP: keep it under 800 ms via streaming SSR (App Router streams by default), CDN caching, and `preconnect` to required origins.
- Ship less JS to get to first paint sooner: the Server/Client boundary rules in `react_standards` are the main LCP lever in this stack.

## CLS under 0.1

- Every image and embed declares `width`/`height` or `aspect-ratio` so the browser reserves space; skeletons match the dimensions of the content they stand in for.
- Never inject banners, ads, or late-loading UI above existing content; reserve the slot.
- Fonts: prevent fallback-to-webfont reflow with `size-adjust`/`ascent-override` metric overrides on the fallback font.
- Animate only `transform` and `opacity`; animating `top`, `left`, `height`, or `margin` triggers layout and often shifts neighbors.

## INP under 200 ms

- Keep main-thread tasks under 50 ms: chunk long work with `scheduler.yield()` (falling back to `setTimeout`), or move it to a Web Worker.
- Mark non-urgent updates as transitions (`useTransition`/`useDeferredValue` in React; signals keep Angular updates fine-grained) so typing and clicking stay responsive.
- Virtualize long lists (TanStack Virtual, Angular CDK `cdk-virtual-scroll-viewport`) instead of rendering thousands of nodes; debounce input-driven work; cancel stale requests with `AbortController`.
- Use the `web-vitals` library's attribution build to find which interaction and which script are responsible before touching code.

## Code splitting and loading discipline

- Route-level splitting is the default: App Router does it per route; Angular uses `loadComponent`/`loadChildren`.
- Below-the-fold and rarely used heavy components load on demand: `React.lazy` + Suspense, Angular `@defer (on viewport)`, or dynamic `import()` on first interaction for chart libraries, editors, and exporters.
- Watch for barrel files (`index.ts` re-exporting everything): they defeat tree-shaking and pull entire directories into the initial chunk. Import from the concrete module.

## Images and fonts

- Serve AVIF/WebP with `srcset`/`sizes`; `loading="lazy"` and `decoding="async"` for off-screen images only. In `ui/`, `next/image` handles format negotiation, sizing, and lazy-loading; use it instead of raw `<img>`.
- Self-host fonts as WOFF2 (max two families, ~4 weights, or one variable font); `font-display: swap` plus the metric-override fallback above; `preload` only the font used above the fold.

## Measuring: CrUX plus Lighthouse CI

- Field truth: CrUX (28-day rolling p75, surfaced in PageSpeed Insights and the CrUX API) for public pages, and your own RUM — `web-vitals` reporting into the existing OpenTelemetry pipeline — for authenticated views CrUX cannot see.
- Lab enforcement: Lighthouse CI in the pipeline with assertions (for example `largest-contentful-paint: max 2500`, `cumulative-layout-shift: max 0.1`, performance category >= 0.9) on throttled mobile settings, so regressions fail the PR instead of reaching the field.
- Lab and field will disagree: Lighthouse cannot measure INP (it has no real user interaction). Optimize against field numbers; use lab numbers as the regression tripwire.

## Common pitfalls

- Optimizing the Lighthouse score while field INP stays red: lab load is not user interaction.
- Lazy-loading the LCP image, adding a full round-trip to the most important paint.
- Bundle budget configured as a warning, drifting 10 KB per PR until nobody remembers green.
- Skeletons and spinners sized differently from the content they replace, paying CLS twice.
- A barrel-file import pulling a 300 KB library into the initial chunk for one function.
- Measuring only on a developer-grade machine and fast network; p75 mobile is the contract.
- Animating layout properties for "polish", shifting everything below the element.

## Definition of done

- [ ] p75 field metrics for affected pages hold LCP <= 2.5 s, INP <= 200 ms, CLS <= 0.1 (CrUX or RUM), or lab equivalents pass under throttled mobile settings for pre-launch work.
- [ ] Bundle budgets enforced as CI failures: initial JS <= 200 KB gz, lazy chunks <= 100 KB gz (or the Angular `budgets` error thresholds); the PR shows no unexplained size regression.
- [ ] LCP element server-rendered, not lazy-loaded, `fetchpriority="high"` where late-discovered.
- [ ] All media reserves space (`width`/`height` or `aspect-ratio`); no content injected above existing content; skeletons dimensionally match.
- [ ] Heavy or below-the-fold components split (`React.lazy`, `@defer`, dynamic import); no barrel-file regressions in the initial chunk.
- [ ] Images in modern formats with `srcset`; fonts self-hosted WOFF2 with `font-display: swap` and metric-adjusted fallbacks.
- [ ] Long tasks chunked or offloaded; non-urgent updates in transitions; long lists virtualized.
- [ ] Lighthouse CI assertions and `web-vitals` RUM reporting in place for the affected routes; regressions fail the pipeline.
