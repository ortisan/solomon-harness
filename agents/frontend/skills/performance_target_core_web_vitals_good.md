## Performance (target: Core Web Vitals "good")


- Field targets at the 75th percentile: LCP under 2.5s, INP under 200ms (INP replaced FID as the responsiveness metric), CLS under 0.1.
- Code-split by route and lazy-load heavy, below-the-fold, or rarely used components (`React.lazy`/`Suspense`, Angular `@defer`, dynamic `import()`).
- Set and enforce a bundle budget (Angular `budgets` in `angular.json`; a bundle analyzer in CI for React). Treat a regressive jump in initial JS as a build failure, not a warning.
- Prevent layout shift: reserve space for images/media with explicit `width`/`height` or `aspect-ratio`, and avoid injecting content above existing content.
- Optimize images: modern formats (AVIF/WebP), responsive `srcset`, `loading="lazy"` for off-screen, and `fetchpriority="high"` for the LCP image.
- Virtualize long lists (TanStack Virtual, Angular CDK `cdk-virtual-scroll`) instead of rendering thousands of nodes.
- Keep the main thread free: debounce/throttle scroll, resize, and input handlers; move heavy computation off the render path; cancel stale requests with `AbortController`.
- Measure before optimizing. Use the React Profiler, Angular DevTools, and Lighthouse/WebPageTest. Verify each optimization against numbers, not intuition.
