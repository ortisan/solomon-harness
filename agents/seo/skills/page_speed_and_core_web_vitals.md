# Page Speed and Core Web Vitals

How to measure and hit the Core Web Vitals: the thresholds, the field-versus-lab discipline, the highest-impact fixes per metric, and enforceable performance budgets. The stance: the only score that counts is the field 75th percentile from real users; lab tools exist to diagnose, and a Lighthouse 100 with failing CrUX is a failing page.

## Thresholds and how they are assessed

A URL (or URL group) passes a metric when the 75th percentile of real-user visits over the trailing 28 days is "good", assessed separately for phone and desktop:

| Metric | Good | Needs improvement | Poor |
| --- | --- | --- | --- |
| LCP (Largest Contentful Paint) | <= 2.5 s | 2.5-4.0 s | > 4.0 s |
| INP (Interaction to Next Paint) | <= 200 ms | 200-500 ms | > 500 ms |
| CLS (Cumulative Layout Shift) | <= 0.1 | 0.1-0.25 | > 0.25 |

INP replaced FID on 2024-03-12; nothing should still target or report FID. Supporting diagnostics: TTFB under 800 ms and FCP under 1.8 s. In the lab, TBT (Total Blocking Time) is the closest INP proxy. For ranking, Core Web Vitals are a lightweight tie-breaker within the page-experience signals — the business case is conversion and crawl efficiency (a slow origin also lowers Googlebot's crawl capacity), not a rankings jump.

## Field vs lab data

- Field: CrUX collects anonymized Chrome data into a 28-day rolling window at p75, reported per URL group when traffic suffices, else origin-wide. Read it in PageSpeed Insights (top panel) and the GSC Core Web Vitals report.
- Lab: Lighthouse and WebPageTest run a synthetic, throttled load (Moto G-class CPU, slow 4G). Deterministic and diffable, but blind to real devices, geography, and interactions — Lighthouse cannot measure INP at all.
- Own your RUM: CrUX is Chrome-only and 28 days laggy. Ship the `web-vitals` library (attribution build) and beacon the values with the responsible element, so an INP regression names its handler:

```js
import { onLCP, onINP, onCLS } from 'web-vitals/attribution';
const send = (m) => navigator.sendBeacon('/rum', JSON.stringify({
  name: m.name, value: m.value,
  target: m.attribution.target ?? m.attribution.largestShiftTarget,
}));
onLCP(send); onINP(send); onCLS(send);
```

## LCP: the biggest levers

Split LCP into its four sub-parts — TTFB, resource load delay, resource load duration, element render delay — and fix the largest one first.

- Make the LCP resource discoverable in the initial HTML with `fetchpriority="high"`; never lazy-load it. Reserve `preload` for LCP images referenced only from CSS.
- Cut TTFB with edge caching/CDN, and 103 Early Hints for the critical origins.
- Keep the hero image under about 150-200 KB: AVIF or WebP, correctly sized via `srcset`/`sizes`.

```html
<link rel="preconnect" href="https://cdn.example.com">
<img src="/hero-1200.avif" fetchpriority="high" width="1200" height="630"
     srcset="/hero-800.avif 800w, /hero-1200.avif 1200w" sizes="100vw" alt="Product hero">
```

## CLS: the biggest levers

- Explicit `width`/`height` (or CSS `aspect-ratio`) on every image, video, and iframe, so the browser reserves the box before load.
- Reserve fixed slots (`min-height`) for ads, embeds, and consent banners; never inject content above existing content.
- Web fonts: use fallback font metric overrides (`size-adjust`, `ascent-override`) or `font-display: optional` so the swap does not reflow; preload self-hosted critical fonts.
- Animate only `transform` and `opacity`; animating layout properties (top, height, margin) shifts neighbors.

## INP: the biggest levers

INP is worst-interaction latency: input delay + processing + presentation. The enemy is long main-thread tasks (over 50 ms).

- Break up long loops and hydration work; yield between chunks so input can run:

```js
for (const chunk of chunks(rows, 50)) {
  render(chunk);
  await scheduler.yield();   // release the main thread between chunks
}
```

- Ship less JavaScript: code-split per route, drop unused polyfills, defer every third-party tag, and move analytics off the main thread (workers) where possible.
- Give instant visual feedback (paint first, compute after), keep the DOM small, and apply `content-visibility: auto` to long offscreen sections so rendering work is deferred.
- Debounce input handlers and avoid full-app re-renders on keystroke in framework code.

## Performance budgets

Budgets make regressions a CI failure instead of a quarterly surprise. Enforce with Lighthouse CI (`budgets.json`) plus a bundle-size check on PRs. Sane starting numbers for a content/commerce page on throttled mobile:

```json
[{ "path": "/*",
   "resourceSizes": [
     { "resourceType": "script", "budget": 300 },
     { "resourceType": "image",  "budget": 500 },
     { "resourceType": "total",  "budget": 1200 } ],
   "timings": [
     { "metric": "largest-contentful-paint", "budget": 2500 },
     { "metric": "total-blocking-time",      "budget": 200 } ] }]
```

Budgets are per template, tightened over time, and a deliberate decision (recorded in the PR) when raised. Pair the lab gate with a weekly review of CrUX p75 so the field verdict stays the source of truth.

## Common pitfalls

- Optimizing the Lighthouse score while field p75 stays red — the assessment Google and users see never changes.
- Lazy-loading the LCP image, adding a full round-trip before the largest paint.
- Font swap without metric overrides, producing both CLS and a flash of restyled text.
- Reading only desktop numbers when the failing CrUX segment is phone (the common case).
- A consent banner injected at the top of `<body>` (CLS) whose script also blocks first input (INP).
- Preloading a dozen resources: priority inflation demotes the actual LCP resource.
- Treating TBT as INP: TBT is load-time only; INP failures often come from post-load interactions.

## Definition of done

- [ ] Field p75 (CrUX or own RUM) meets LCP <= 2.5 s, INP <= 200 ms, CLS <= 0.1 on phone and desktop for the affected templates.
- [ ] The LCP element is server-rendered, not lazy-loaded, carries `fetchpriority="high"`, and its image is <= ~200 KB in AVIF/WebP.
- [ ] Every image, embed, and ad slot has reserved dimensions; fonts load with metric-compatible fallbacks; no content is injected above existing content.
- [ ] No new main-thread task over 50 ms in the interaction path; third-party scripts are deferred or off-thread.
- [ ] Lighthouse CI budgets pass on the PR (script <= 300 KB, TBT <= 200 ms, lab LCP <= 2.5 s on throttled mobile), and any budget raise is justified in the PR.
- [ ] RUM beacons report LCP/INP/CLS with attribution, and the dashboard alert thresholds match the "good" limits.
