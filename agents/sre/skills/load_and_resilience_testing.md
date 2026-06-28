# Load and Resilience Testing

Find the breaking point and the slow resource leak in a controlled test before live traffic finds them for you.

This skill owns the test taxonomy, the load tools, chaos experiments, and how to turn results into automated pass/fail gates. It does not cover the runtime overload controls (rate limiting, circuit breaking, adaptive concurrency, load shedding) or the overload-specific `ramping-arrival-rate` proof; those live in `resilience_and_load_shedding`. Topology and redundancy are in `high_availability`; the burn-rate math that test results are wired back to is in `reliability_targets_sli_slo_sla_error_budgets`.

## Test types

Each type answers a different question; run all of them, not just the easy one.

- **Load test:** hold expected peak (for example measured p99 daily peak RPS) and confirm SLOs hold. The baseline regression gate.
- **Stress test:** push beyond peak to find the failure mode and confirm it is graceful (shedding, 429/503) rather than a cascade of timeouts.
- **Spike test:** jump from baseline to a multiple of peak in seconds to test autoscaling lag and admission control. Pods take tens of seconds to become ready, so the spike must be absorbed by shedding meanwhile.
- **Soak / endurance test:** hold expected load for 4-24 hours to surface memory leaks, file-descriptor and connection-pool leaks, log-disk fill, and unbounded caches. Watch the RSS slope, GC frequency, and open-FD count, not just latency.
- **Breakpoint / capacity test:** ramp until the system fails to locate the knee of the latency curve, which is your real capacity number and the input to autoscaling and capacity planning.

## Open vs closed model

A closed model (fixed virtual users that wait for each response) lets a slow system protect itself by slowing the client, which hides the failure. An open model (arrival rate independent of response time) is what real traffic does and is what stress and capacity tests need. Prefer arrival-rate executors for capacity and overload work.

## Tools

| Tool | Model | Best for |
| --- | --- | --- |
| k6 (v1.x) | scriptable JS, open and closed | CI gates with thresholds, scripted scenarios |
| Locust | Python | complex stateful user flows |
| Gatling | Scala/Java DSL | high-throughput tests, rich HTML reports |
| JMeter | XML/GUI | legacy estates, broad protocol coverage |
| Vegeta / wrk | CLI | quick HTTP throughput benchmarks |

## SLO-based pass/fail gates

A load test with no thresholds is a demo. Declare pass/fail up front from the SLO: target RPS, p95 and p99 latency ceilings, and a maximum error rate. Wire it so a breach fails the CI stage. Worked k6 steady-peak load test:

```js
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady_peak: {
      executor: 'constant-arrival-rate',
      rate: 500, timeUnit: '1s',     // 500 rps = measured peak
      duration: '15m',
      preAllocatedVUs: 200, maxVUs: 800,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<300', 'p(99)<500'],  // latency SLO ceilings (ms)
    http_req_failed: ['rate<0.001'],                 // < 0.1% errors
    checks: ['rate>0.999'],
  },
};

export default function () {
  const res = http.get('https://staging.api.example.com/orders');
  check(res, { 'status 200': (r) => r.status === 200 });
}
```

A breached threshold makes k6 exit non-zero, so the pipeline blocks promotion. Run this against staging before every release and on a nightly schedule to catch regressions.

## Realistic conditions

Use production-like data volume, a representative payload mix, and cold caches where cache state matters. Warm-cache tests overstate capacity. Never load-test a single instance and extrapolate linearly; the limits that bite are shared and downstream (database connection pools, third-party rate limits, NAT ports). Test in an isolated environment that mirrors production, or test in production behind explicit guardrails and a kill switch.

## Chaos engineering

Chaos engineering is controlled experimentation on a production-like system to build confidence it withstands turbulent conditions. The method:

1. Define a **steady-state hypothesis** as a measurable normal, for example "checkout success rate >= 99.5% with p99 < 400 ms".
2. Inject a real-world fault: instance kill, added latency, packet loss, AZ outage, a failed dependency, disk-full, clock skew.
3. Limit the **blast radius** (one cell, a small traffic percentage) and arm an **abort switch**.
4. Verify the steady state still holds; if it does not, you found a weakness to fix before customers do.

Tools: Chaos Mesh (Kubernetes CRDs: `PodChaos`, `NetworkChaos`, `IOChaos`, `StressChaos`), Litmus, Gremlin (SaaS), and AWS Fault Injection Service. Run experiments as scheduled game days, treating each like an incident with an owner and a timeline. Wire results back to the SLO: confirm that under the injected fault the fast-burn alert fires and the runtime controls in `resilience_and_load_shedding` engage before the error budget is exhausted.

## Common pitfalls

- Load-testing a single instance and extrapolating: shared and downstream limits (DB pool, third-party quotas) break the linear assumption. Reviewers reject single-node numbers presented as system capacity.
- No thresholds on the run: it proves nothing and cannot gate CI. Every test must encode SLO-derived pass/fail.
- Closed-model executors for stress/capacity work: a slow system throttles the client and hides the failure. Use an arrival-rate (open) model.
- Warm-cache or tiny-dataset tests: they overstate capacity and miss the real knee. Use production-like volume and cold caches where it matters.
- Skipping the soak test: leaks and FD exhaustion only appear over hours and cause 3am pages. A passing 10-minute run does not prove endurance.
- Chaos experiments with no steady-state hypothesis, blast-radius limit, or abort switch: that is an outage you caused, not an experiment. Reviewers reject unbounded fault injection.
- Running a test once and never again: capacity and dependencies drift; the gate must run on a schedule and before releases.

## Definition of done

- [ ] Load, stress, spike, soak, and breakpoint tests exist for the critical journeys, each with a documented purpose.
- [ ] Every test encodes SLO-derived thresholds (RPS, p95/p99 latency, error rate) and fails the CI stage on breach.
- [ ] Capacity and stress tests use an open (arrival-rate) model; results feed autoscaling and capacity planning.
- [ ] Tests run against production-like data volume and payload mix, with an isolated environment or in-prod guardrails and a kill switch.
- [ ] A soak test of at least 4 hours runs on a schedule, with memory, FD, and connection-pool trends reviewed.
- [ ] Chaos experiments define a steady-state hypothesis, a blast-radius limit, and an abort switch, and run as scheduled game days.
- [ ] Chaos and load results are tied back to SLO burn-rate alerts and the runtime controls in `resilience_and_load_shedding`.
- [ ] All test scripts and chaos manifests are committed as code, reviewed, and version-controlled per Git Flow and Conventional Commits.
