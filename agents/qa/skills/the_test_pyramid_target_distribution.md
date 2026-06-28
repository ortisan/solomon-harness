## The test pyramid (target distribution)


Hold the shape, not the exact percentages, but use these as a budget when a suite drifts:

- Unit: ~70%. Single function/class, no I/O, sub-millisecond. The bulk of edge-case coverage lives here.
- Integration: ~20%. Real wiring between in-process components (domain plus an adapter), external boundaries faked or containerized.
- E2E: ~10%. Full path through the deployed system. Slowest and most brittle, so keep them few and focused on critical user journeys.

Anti-pattern to reject: the "ice-cream cone" (mostly E2E, few unit). It is slow, flaky, and gives weak failure localization.
