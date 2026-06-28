## Load and resilience testing


Find the breaking point in a controlled test before traffic finds it for you.

- **Tools**: k6 or Locust (scriptable, CI-friendly), Gatling, JMeter, Vegeta or wrk for quick HTTP benchmarks.
- **Test types**: load (expected peak), stress (beyond peak to find the limit), spike (sudden surge), soak/endurance (hold load 4–24h to surface memory leaks and resource exhaustion), and breakpoint/capacity (ramp until it fails to locate the knee of the latency curve).
- **Set pass/fail thresholds up front**: target RPS, p95 and p99 latency ceilings, and a max error rate (for example p99 < 500 ms and error rate < 0.1% at 2x expected peak). A load test with no thresholds is a demo, not a test.
- **Realistic conditions**: production-like data volume, representative payload mix, and cold caches where that matters. Warm-cache tests lie about real capacity.
- **Chaos engineering**: inject faults deliberately (instance kill, latency, packet loss, AZ outage, dependency failure) with a defined steady-state hypothesis and a blast-radius limit. Run scheduled gamedays. Tools: a Chaos Monkey-style killer, fault-injection meshes.
- Pitfalls: load-testing a single instance and extrapolating, ignoring downstream dependency limits (DB connections, third-party rate limits), running once and never again, no abort/kill switch on the test itself.
