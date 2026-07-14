---
name: resilience-and-load-shedding
description: Governs platform-level overload protection, covering rate limiting and throttling, circuit breaking and outlier ejection, retry budgets across hops, priority-aware load shedding, and autoscaling on leading signals. Use when configuring gateway or mesh traffic controls or validating shedding under a load test.
---

# Resilience and Load Shedding

Under overload, protect the most important traffic by enforcing rate limiting, circuit breaking, retry budgets, and load shedding at the API gateway and service mesh, and validate every control with load tests and fault injection before real traffic does. The operating stance is that a saturated service must fail fast and selectively (reject the cheapest, lowest-priority requests in milliseconds) rather than slow down for everyone until timeouts cascade. Tie every shedding decision to the SLO and the error budget: when the budget burns fast, shed load to defend it.

This skill owns the platform-level traffic controls (gateway/mesh config, autoscaling, brownout) and how to prove they work. It does not re-cover the in-code implementation of timeouts/retries/idempotency (owned by `software_engineer` in `robust_defensive_code`) or the architectural pattern catalog and non-functional-requirement budgets (owned by `software_architect`). The sibling `high_availability` skill owns topology and SPOF elimination; `load_and_resilience_testing` owns the general test taxonomy and gamedays; `reliability_targets_sli_slo_sla_error_budgets` owns burn-rate alerting math referenced below.

## Rate limiting and throttling at the edge and mesh

Rate limiting is a token bucket: a steady refill `rate` plus a `burst` bucket that absorbs short spikes. Place a coarse limit at the gateway (per-IP, per-API-key, per-tenant) and fine limits at the mesh for inter-service quotas. Always return `429 Too Many Requests` with `Retry-After`, never a silent drop or a hang.

NGINX (1.27) ingress, per-client token bucket:

```nginx
limit_req_zone $binary_remote_addr zone=perip:10m rate=10r/s;
limit_req_status 429;
server {
  location /api/ {
    limit_req zone=perip burst=20 nodelay;   # 10 rps steady, absorb a burst of 20, no queueing delay
    add_header Retry-After 1 always;
  }
}
```

`nodelay` serves the burst immediately then enforces the rate; without it NGINX queues and adds latency, which defeats the point of failing fast. For distributed/global quotas use Envoy's rate-limit service (`envoy.filters.http.ratelimit` talking to a `ratelimit` gRPC service backed by Redis) so the limit is shared across gateway replicas instead of per-replica. In Istio (1.26+) wire this with an `EnvoyFilter` referencing the rate-limit cluster, keyed on a descriptor such as `header_match` on the API key or `x-tenant-id`. Gateway API (1.3) has no native rate limiting; it is delivered by the mesh/controller extension, so do not expect a portable spec field.

Key decisions: limit on the most specific stable identity you have (API key or tenant, then IP) because IP-only limits punish shared NATs; set the limit from measured capacity, not a guess; and exempt health checks and internal control-plane traffic from the same bucket.

## Circuit breaking and outlier ejection at the mesh

Circuit breaking caps concurrency so a struggling dependency cannot consume all caller resources; outlier detection ejects individual bad endpoints. Configure both on the Istio `DestinationRule`:

```yaml
apiVersion: networking.istio.io/v1
kind: DestinationRule
metadata: { name: payments }
spec:
  host: payments.prod.svc.cluster.local
  trafficPolicy:
    connectionPool:
      tcp: { maxConnections: 200 }
      http:
        http2MaxRequests: 1000
        maxRequestsPerConnection: 100
        maxRetries: 3                 # concurrent retry cap across the pool, not per-request count
    outlierDetection:
      consecutive5xxErrors: 5
      interval: 10s
      baseEjectionTime: 30s           # grows on repeat ejection
      maxEjectionPercent: 50          # never eject more than half; keep a quorum serving
      minHealthPercent: 40            # below this, stop ejecting (the dependency is broadly down)
```

`maxEjectionPercent: 50` and `minHealthPercent` are the safety rails: without them a correlated failure ejects every endpoint and you create the outage you were trying to avoid. `maxPendingRequests` (Envoy raw, or the connection pool queue) is the backpressure boundary; requests past it get `503` immediately rather than queuing unboundedly. The state machine itself (closed/open/half-open) is the `software_architect` pattern; here you are tuning its thresholds against real latency data, not theory.

## Timeout and retry budgets across hops

Retries multiply down a call chain. With `r` retries at every hop of an `N`-hop chain, worst-case amplification is `(1 + r)^N`: two retries across three hops is `3^3 = 27x` the original load aimed at the deepest, already-failing service. This is how a minor blip becomes a retry storm. Two rules prevent it.

First, a strict timeout hierarchy: `attempts * perTryTimeout` must stay below the parent route timeout, which must stay below the caller's timeout. Retry only idempotent calls and only on transport/connect failures, not on application `5xx` (those are usually deterministic and a retry just doubles the damage).

```yaml
apiVersion: networking.istio.io/v1
kind: VirtualService
spec:
  http:
  - route: [{ destination: { host: payments } }]
    timeout: 2s
    retries:
      attempts: 2
      perTryTimeout: 600ms            # 2 * 600ms = 1.2s < 2s route timeout
      retryOn: connect-failure,refused-stream,unavailable
      retryRemoteLocalities: false
```

Second, and more important at the platform level, cap retries with a budget rather than a fixed count. A retry budget limits retries to a percentage of active requests, so under broad failure the retry rate collapses automatically. Envoy `retry_budget` (preferred over `max_retries`):

```yaml
circuit_breakers:
  thresholds:
  - priority: DEFAULT
    max_pending_requests: 256         # backpressure queue; 503 past this
    retry_budget:
      budget_percent: { value: 20.0 } # retries capped at 20% of active requests
      min_retry_concurrency: 3
```

Linkerd (2.17) exposes the same idea natively in a `ServiceProfile` (`retryBudget: { retryRatio: 0.2, minRetriesPerSecond: 10, ttl: 10s }`). Retry at exactly one layer, normally the edge or the immediate caller, never at every hop, and add jitter to retry timing (the `software_engineer` skill covers exponential backoff with jitter in code). The mesh budget is the backstop that holds even when a service forgets.

## Load shedding, priority, and QoS queuing

Static limits are fragile; prefer adaptive concurrency that derives the limit from observed latency. Envoy's `envoy.filters.http.adaptive_concurrency` (gradient controller) samples minimum round-trip time, computes an allowed concurrency, and returns `503` when exceeded, with no hand-tuned number to drift out of date:

```yaml
adaptive_concurrency:
  gradient_controller_config:
    concurrency_limit_params: { max_concurrency_limit: 1000 }
    min_rtt_calc_params: { interval: 30s, request_count: 50 }
```

Shedding must be priority-aware: classify traffic into tiers and drop the lowest first. Tag requests (`x-request-priority: critical|standard|sheddable`) so checkout and payments survive while recommendations, prefetch, and batch jobs are dropped under pressure. The Kubernetes API server's Priority and Fairness (`FlowSchema` to `PriorityLevelConfiguration` with concurrency shares) is the reference implementation of this pattern; mirror it. Use LIFO, not FIFO, for the admission queue under overload: the oldest queued request is the one the client most likely already abandoned, so serving it wastes work. Envoy's overload manager adds global resource-based shedding (for example `envoy.resource_monitors.fixed_heap` driving `stop_accepting_requests` at 95% heap) as the last line before OOM. The in-process token-bucket/concurrency-limiter version of this (Netflix `concurrency-limits` and its ports) is `software_engineer` territory; here you are placing the limiter at the gateway/sidecar.

## Autoscaling and backpressure

Autoscale on a signal that leads load, not one that lags it. CPU is a poor proxy for an IO-bound service; scale on requests-per-second or queue depth. Kubernetes HPA (`autoscaling/v2`) with asymmetric behavior:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  minReplicas: 4                      # N+1 even at trough; one pod loss must not hurt
  maxReplicas: 40
  metrics:
  - type: Pods
    pods:
      metric: { name: http_requests_per_second }
      target: { type: AverageValue, averageValue: "200" }
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0   # react immediately to spikes
      policies: [{ type: Percent, value: 100, periodSeconds: 30 }]
    scaleDown:
      stabilizationWindowSeconds: 300 # decay slowly to avoid flapping
      policies: [{ type: Percent, value: 10, periodSeconds: 60 }]
```

For queue- or event-driven workloads use KEDA (2.17) `ScaledObject` to scale on Kafka consumer lag, SQS depth, or Prometheus query, including scale-to-zero. Autoscaling is not a substitute for shedding: pod startup plus readiness is tens of seconds, so a sudden spike must be absorbed by rate limits and shedding while replicas come up. Keep capacity headroom (target utilization 60-70%, not 90%) so the autoscaler has room to react. Backpressure is the same principle propagated upstream: bounded queues that reject when full, connection limits, and `503 Retry-After` so callers slow down instead of the system silently buffering until it falls over.

## Graceful degradation and brownout

Prefer a reduced service to no service. Brownout sheds features, not requests: behind a flag driven by a load signal, disable personalization, drop recommendation panels, serve stale cache, or skip non-critical writes. HTTP caching gives free degradation: `Cache-Control: stale-while-revalidate=30, stale-if-error=86400` lets the CDN serve stale content for a day when the origin is failing. Make the brownout signal the error-budget burn rate so degradation is automatic and reversible, and surface a banner or header so the state is observable rather than silent.

## Validating the controls (load test and chaos)

A resilience control you have not load-tested is a hypothesis. Drive traffic past known capacity with k6 (v1.x) `ramping-arrival-rate` (open-model: it offers requests at a fixed rate regardless of how slow the system gets, which is what real traffic does) and assert that shedding is fast and explicit, not a hang:

```js
import http from 'k6/http';
import { check } from 'k6';
import { Rate } from 'k6/metrics';

const shed = new Rate('shed_responses');

export const options = {
  scenarios: {
    overload: {
      executor: 'ramping-arrival-rate',
      startRate: 100, timeUnit: '1s',
      preAllocatedVUs: 500, maxVUs: 2000,
      stages: [
        { target: 100,  duration: '1m' },
        { target: 3000, duration: '2m' },   // ~3x past measured capacity
        { target: 3000, duration: '2m' },
      ],
    },
  },
  thresholds: {
    'http_req_duration{expected_response:true}': ['p(99)<500'], // accepted traffic keeps its SLO
    'shed_responses': ['rate<0.6'],                              // most requests still served
    'http_req_failed': ['rate<0.01'],                           // 429/503 are shed, not "failed"
  },
};

export default function () {
  const res = http.get('https://api.example.com/orders');
  shed.add(res.status === 429 || res.status === 503);
  check(res, { 'served or shed cleanly': (r) => r.status < 500 || r.status === 503 });
}
```

A passing run shows shed responses returning in single-digit milliseconds with `429/503` while accepted requests hold p99; a failing system returns connection resets and timeouts and its tail latency explodes. Prove circuit breaking and timeouts with mesh fault injection rather than only killing pods:

```yaml
http:
- fault:
    delay: { percentage: { value: 100 }, fixedDelay: 5s }   # forces the caller's timeout
    abort: { percentage: { value: 20 }, httpStatus: 503 }   # drives outlier ejection
  route: [{ destination: { host: payments } }]
```

Run these as scheduled gamedays with a steady-state hypothesis, a blast-radius limit, and an abort switch (the full chaos taxonomy lives in `load_and_resilience_testing`). Wire results back to the SLO: confirm that under the injected fault the fast-burn alert (for example 14.4x burn over 1h) fires and triggers shedding/brownout before the error budget is exhausted.

## Common pitfalls

- Rate limiting that queues instead of rejecting (no `nodelay`, unbounded `maxPendingRequests`): latency climbs for everyone instead of failing the excess fast. Reject with `429/503` and `Retry-After`.
- Retries configured at every hop with a fixed count and no budget: `(1+r)^N` amplification turns a blip into a storm. Cap with a retry budget and retry at one layer only.
- `perTryTimeout * attempts` exceeding the parent timeout, so the parent kills the call mid-retry and the budget is wasted. Enforce the timeout hierarchy.
- Outlier detection with no `maxEjectionPercent`/`minHealthPercent`: a correlated failure ejects every endpoint and manufactures the outage. Cap ejection at 50% and stop ejecting below the health floor.
- Retrying application `5xx`/non-idempotent writes: doubles damage and risks duplicate side effects. Retry only transport failures on idempotent calls.
- Autoscaling on CPU for an IO-bound service, or with no headroom: the metric lags the load and pods arrive after the spike has already broken the SLO. Scale on RPS/queue depth and keep 30-40% headroom.
- FIFO admission queues under overload: serves requests clients already abandoned. Use LIFO and shed the oldest.
- Treating autoscaling as the overload defense: startup latency means shedding must hold the line until replicas are ready.
- Load shedding that is uniform, not priority-aware: critical checkout traffic is dropped alongside prefetch. Classify and shed the lowest tier first.
- A control merged without a load test or fault-injection run proving it sheds fast: it is unverified. Gate it in CI with k6 thresholds.

## Definition of done

- [ ] Edge and mesh rate limits exist, keyed on the most specific stable identity, return `429`/`503` with `Retry-After`, and exempt health/control-plane traffic; distributed limits use a shared rate-limit service, not per-replica counters.
- [ ] Circuit breaking and outlier detection are configured per dependency with `maxEjectionPercent <= 50` and a `minHealthPercent` floor; the backpressure queue rejects rather than buffering unboundedly.
- [ ] Retries are capped by a retry budget (Envoy `retry_budget` or Linkerd `retryBudget`), applied at one layer, only on idempotent transport failures, with `attempts * perTryTimeout` strictly under the parent timeout.
- [ ] Load shedding is priority-aware (traffic classified into tiers, lowest shed first), uses adaptive concurrency or an explicit limit, and LIFO admission under overload; a global resource-based shed (heap/connection) exists as the last line.
- [ ] Autoscaling targets a leading signal (RPS or queue depth via HPA `autoscaling/v2` or KEDA), with `minReplicas` giving N+1, fast scale-up and slow scale-down behavior, and measured headroom.
- [ ] A documented graceful-degradation/brownout path exists, driven by an observable load or error-budget signal, including stale-cache serving (`stale-if-error`).
- [ ] A k6 `ramping-arrival-rate` test drives traffic past capacity in CI with thresholds asserting shed responses are fast `429/503` and accepted-traffic p99 holds; mesh fault injection validates circuit breaking and timeouts.
- [ ] Shedding and brownout are tied to the error budget: a fast-burn alert triggers protection before the budget is exhausted, verified during a gameday.
- [ ] All gateway/mesh configs and load/chaos scripts are committed as code, reviewed, and version-controlled per Git Flow and Conventional Commits.
