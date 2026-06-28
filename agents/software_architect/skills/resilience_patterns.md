# Resilience and Stability Patterns

Treat every integration point as a guaranteed future failure and decide which stability pattern guards it before the failure arrives, not after the first outage. This skill is the architect's pattern catalog: which pattern counters which failure mode, the thresholds that make it real, how the patterns compose, and where each one is enforced. It governs the design decision; the in-code wiring belongs to the software_engineer skill `robust_defensive_code`, and platform- and gateway-level enforcement belongs to the sre skills `high_availability` and `load_and_resilience_testing`. The canonical reference is Michael Nygard, *Release It!* (2nd ed., 2018) — its Stability Patterns and Stability Antipatterns are the vocabulary used below.

## The failure-mode-first decision table

Pick patterns by the failure you are countering, not by fashion. Name the failure mode in the ADR, then the pattern, then the threshold.

| Failure mode (Nygard antipattern) | Pattern that counters it | Primary owner of enforcement |
| --- | --- | --- |
| Blocked threads / slow responses | Timeout + deadline propagation | client code + gateway |
| Transient blip on an idempotent call | Retry with backoff + full jitter | client code |
| Retries amplifying load (retry storm) | Retry budget / token bucket | client code + service mesh |
| Cascading failure across a dependency | Circuit breaker | client code or mesh sidecar |
| One dependency exhausting a shared pool | Bulkhead isolation | client code (pools), platform (quotas) |
| Caller overrunning a service's capacity | Rate limiting / throttling | gateway / sre |
| Demand exceeding capacity right now | Load shedding | gateway / sre |
| Producer outpacing a consumer | Backpressure (bounded queues) | client code + transport |
| Duplicate delivery from at-least-once retries | Idempotency keys | service + data layer |
| Hard dependency unavailable | Fallback / graceful degradation | service code |
| Resource accumulation over time | Steady-state (purge/evict) | service + platform |

A single integration point usually needs three of these at once: a timeout, a circuit breaker, and a bulkhead. Nygard's rule holds — "every integration point will eventually fail, and you have to decide how."

## Timeouts and deadlines (the foundation)

Nothing else works without a bounded wait. An unbounded call holds a thread until the OS gives up (often 60-300s on default TCP settings), and held threads are how a single slow dependency exhausts a pool and takes down a healthy service.

- Set a timeout on every outbound call: HTTP client, DB query, cache, lock acquisition, queue publish. There is no exception. A missing connect/read timeout is an automatic review rejection.
- Derive the value from the downstream **p99.9**, not the p50, plus headroom — typically `p99.9 * 1.3`. A timeout tuned to the median fires constantly under normal tail latency.
- Propagate a **deadline**, not a fixed per-hop timeout, across a call chain. gRPC does this natively (`context.WithTimeout` / `Deadline`); each hop passes the remaining budget so the total is bounded and no hop wastes work on a request the caller already abandoned. Without propagation, a 5-hop chain with 2s per hop can legally take 10s.
- The per-attempt timeout sits **inside** the retry, so each physical attempt is bounded; an overall request deadline sits outside everything, so total latency is bounded regardless of retries.

## Retry: backoff, full jitter, and retry budgets

Retry is only valid for **idempotent** operations against **transient, retryable** failures (connection reset, 503, 429 with `Retry-After`, gRPC `UNAVAILABLE`). Never retry a 400, a 401, or a business validation error — the result will not change and you have doubled the load for nothing.

- Use exponential backoff with **full jitter**. Equal spacing or backoff-without-jitter produces synchronized retry waves (the thundering herd). The AWS Builders' Library / Marc Brooker analysis ("Exponential Backoff and Jitter") settled this:

```python
# Full jitter: sleep in [0, min(cap, base * 2**attempt)]
sleep = random.uniform(0, min(cap, base * (2 ** attempt)))
# Decorrelated jitter (smoother, self-clocking) is also acceptable:
# sleep = min(cap, random.uniform(base, prev_sleep * 3))
```

  Typical: `base = 100ms`, `cap = 2s`, `max_attempts = 3` total (1 try + 2 retries). More than 3 is rarely worth it; the marginal success probability is tiny and the load cost is linear.
- Add a **retry budget** so retries cannot exceed a fixed fraction of traffic. Google SRE's rule of thumb is retries capped at ~10% of requests; the AWS SDK v2 implements this as a retry token bucket (bucket of 500, each retry costs 5 tokens, a success refunds 1). When the bucket empties, retries stop and the call fails fast. This is the single control that prevents a retry storm from turning a partial outage into a total one.
- Retry at exactly **one layer**. Retries at the client, the gateway, and the service multiply: 3 layers x 3 attempts = 27x amplification against an already-struggling dependency. Decide the layer in the design and disable it everywhere else.

## Circuit breaker (closed / open / half-open)

A breaker stops sending calls to a dependency that is already failing, so the caller fails fast instead of piling up blocked threads, and the dependency gets room to recover.

- **Closed**: calls flow; the breaker counts outcomes over a sliding window. **Open**: trips when the failure rate crosses the threshold; all calls short-circuit immediately with a `CallNotPermitted` error for a cool-down. **Half-open**: after the cool-down, a small number of trial calls are allowed; success closes the breaker, failure re-opens it.
- Sensible defaults (Resilience4j 2.x names): `failureRateThreshold = 50%`, `slidingWindowSize = 100`, `minimumNumberOfCalls = 20` (do not trip on 1 of 2), `waitDurationInOpenState = 30s`, `permittedNumberOfCallsInHalfOpenState = 5`. Add a **slow-call** trip (`slowCallDurationThreshold`, `slowCallRateThreshold`) because slow responses are more dangerous than fast failures — they hold resources.

```yaml
# Resilience4j (2.x) config — the design knobs, not the wiring
resilience4j.circuitbreaker:
  instances:
    pricingService:
      slidingWindowType: COUNT_BASED
      slidingWindowSize: 100
      minimumNumberOfCalls: 20
      failureRateThreshold: 50
      slowCallDurationThreshold: 2s
      slowCallRateThreshold: 80
      waitDurationInOpenState: 30s
      permittedNumberOfCallsInHalfOpenState: 5
```

- Scope one breaker **per dependency** (per downstream service, sometimes per endpoint), never one global breaker — a global breaker lets an unrelated failure block healthy traffic.
- Netflix Hystrix is end-of-life; do not specify it for new designs. Use Resilience4j (JVM), Polly v8 `ResiliencePipeline` (.NET), or push the breaker into the service mesh (Envoy outlier detection / Istio `DestinationRule`) so it is enforced uniformly regardless of client language — coordinate that placement with the sre owner.

## Bulkhead isolation

Partition resources so a failure in one dependency cannot consume the capacity others need, the way ship bulkheads stop one flooded compartment from sinking the hull.

- Give each downstream its **own** connection pool / thread pool / concurrency permit. If service A and service B share one 50-connection pool and B hangs, B's blocked calls drain all 50 and A fails too even though A is healthy.
- Two implementations: **semaphore** isolation (a permit count, cheap, same thread, no timeout enforcement) and **thread-pool** isolation (separate executor, costs context switches but contains the blocking and enforces timeouts). Default to semaphore for fast in-process limits; use thread-pool isolation when the dependency is slow or untrusted.
- Size the bulkhead from the downstream's capacity and your latency target via Little's Law: `concurrency = throughput * latency`. A dependency serving 200 req/s at 50ms needs only ~10 concurrent permits; granting 200 just lets you queue 200 doomed calls.
- At the platform tier this becomes pool quotas, separate node pools, and cell-based architecture — the sre `high_availability` skill owns that level.

## Rate limiting, throttling, load shedding, and backpressure

These four are distinct decisions about what to do when demand exceeds capacity; do not conflate them.

- **Rate limiting / throttling** caps how much a *caller* may send, protecting the service from a noisy or abusive client. Return `429 Too Many Requests` with a `Retry-After` header and a clear quota. Choose the algorithm deliberately:
  - **Token bucket** — tokens refill at rate `r`, bucket holds `b`; allows bursts up to `b`, then steady `r`. The default for API quotas (AWS API Gateway, Stripe) because real traffic is bursty. GCRA is the queue-free token-bucket variant used by Redis-backed limiters.
  - **Leaky bucket** — requests drain at a fixed rate; output is perfectly smooth with **no** bursts. Use it to protect a downstream that cannot absorb spikes (a legacy DB, a payment rail). The cost is added latency for queued requests.

```
Token bucket: allow if tokens >= 1; tokens = min(b, tokens + elapsed*r); tokens -= 1
Leaky bucket: enqueue; serve at fixed rate r; reject when queue full
```

- **Load shedding** protects the service from *itself* when total demand exceeds capacity regardless of who is sending it. Shed the **lowest-priority** traffic first (health checks and retries before paying users), reject early with `503`, and serve the admitted requests well rather than degrading all of them. Adaptive approaches — Netflix `concurrency-limits` (gradient algorithm, TCP-Vegas-style), Envoy's adaptive concurrency filter, and CoDel ("controlled delay", which sheds based on queue *sojourn time* not depth) — set the limit automatically instead of a hand-tuned constant. Under overload, switching the queue to **LIFO** keeps latency bounded for the requests you do serve. Enforcement lives at the gateway/mesh — coordinate with the sre owner.
- **Backpressure** is the producer/consumer version: signal demand upstream instead of buffering without limit. Reactive Streams (`request(n)` demand signaling, Project Reactor 3.x), RSocket, gRPC/HTTP-2 flow control, and Kafka consumer `pause()/resume()` all implement it. The architectural rule: **every queue is bounded**, and you decide explicitly what happens when it is full (block, drop-oldest, or reject). An unbounded queue converts a latency problem into an out-of-memory crash and hides the overload until it is fatal.

## Idempotency, fallback, and graceful degradation

- **Idempotency** is the precondition that makes retries and at-least-once delivery safe. Exactly-once delivery does not exist across a network; build idempotent receivers instead. Require an **idempotency key** on every non-idempotent mutation (Stripe's `Idempotency-Key` header model): the server records the key and the result, and a replay returns the stored result instead of re-executing. Pair with the transactional **outbox** pattern when a state change must produce exactly one side effect. PUT/DELETE/GET are idempotent by HTTP semantics; POST is not — protect it.
- **Fallback / graceful degradation** is what the caller does when a dependency is open-circuited or timed out: serve stale cache (`stale-while-revalidate`), a cached/default value, a reduced feature set, or read-only mode — anything better than a hard error. The hard rule: a fallback must not call another fragile dependency, or it becomes a second failure mode. Decide per feature whether degradation is acceptable; for money movement it usually is not, so there fail fast and surface the error.

## Steady-state and fail-fast

- **Steady-state**: any resource that accumulates must have a matching purge — log rotation, cache eviction with a bound (LRU + max size + TTL), connection recycling, completed-job cleanup, idempotency-key expiry. A design with growth and no purge has a built-in outage with a date on it.
- **Fail-fast**: check preconditions you can verify cheaply — breaker open, rate limit exceeded, required parameter missing, no capacity — and reject immediately rather than starting work that will time out. A fast `503` lets the caller's retry and breaker logic react in milliseconds; a slow timeout holds resources on both sides.

## How the patterns compose

Order matters; the wrong nesting silently defeats a pattern. Compose from the outside in: **circuit breaker, then retry, then timeout, then the call**, with the bulkhead innermost around the call and an overall deadline outermost.

```
overall deadline
  └─ circuit breaker        (open => short-circuit before spending any retry budget)
       └─ retry (+ budget)  (re-attempt only transient failures)
            └─ timeout      (bound each physical attempt)
                 └─ bulkhead(call)   (cap concurrency to the resource)
```

The reasoning: a **tripped breaker outside the retry** stops the retries before they consume budget against a dependency that is already down — the most common goal, protecting a struggling downstream. The **timeout inside the retry** bounds each attempt so a slow attempt does not eat the whole deadline. The **bulkhead innermost** limits real concurrency to the resource. Note the alternative: Resilience4j's default decorator order places retry *outside* the breaker so the breaker observes every physical attempt and trips faster; choose that when fast tripping matters more than conserving retry budget, and document which you chose and why in the ADR. Whichever order, the overall deadline is always outermost so total latency is bounded no matter how the inner patterns behave.

## Common pitfalls

- An integration point with no timeout. One slow dependency exhausts the thread/connection pool and the failure cascades; this is the single most common cause of total outages.
- Retries at multiple layers (client + gateway + service). Amplification multiplies; cap retry to one layer and add a retry budget so a partial outage cannot become a retry storm.
- Retrying non-idempotent or non-retryable failures (POST without an idempotency key, a 400, a 401). It duplicates side effects or doubles load for an outcome that will not change.
- Backoff without jitter. Synchronized clients retry in waves and DDoS the recovering dependency; require full or decorrelated jitter.
- A single global circuit breaker. An unrelated dependency's failure blocks healthy traffic; scope one breaker per dependency.
- A circuit breaker that trips on absolute counts with no `minimumNumberOfCalls`, so 1 failure out of 2 opens it during low traffic.
- Unbounded queues / buffers. They convert overload into an out-of-memory crash and mask the problem until it is fatal; every queue is bounded with a defined full-policy.
- Specifying Hystrix for new work. It is end-of-life; use Resilience4j, Polly v8, or mesh-level enforcement.
- A fallback that calls another fragile dependency, adding a failure mode instead of removing one.
- Synchronous deep call chains with no deadline propagation, so total latency is the unbounded sum of per-hop timeouts.
- Treating exactly-once delivery as achievable instead of building idempotent receivers; the result is duplicate charges and double-processing under retry.
- A resource that grows with no purge mechanism (logs, cache, idempotency keys), violating steady-state.

## Definition of done

- [ ] Every integration point in the design has an explicit timeout derived from the downstream p99.9, with deadline propagation across call chains.
- [ ] Retries are restricted to idempotent operations and retryable failures, use exponential backoff with full or decorrelated jitter, are capped (~3 attempts), apply a retry budget, and exist at exactly one layer.
- [ ] Each external dependency has its own circuit breaker (per-dependency scope) with documented failure-rate, slow-call, cool-down, and half-open thresholds; no Hystrix.
- [ ] Bulkheads isolate each dependency's pool/concurrency, sized via Little's Law; one dependency cannot exhaust another's capacity.
- [ ] Rate limiting (token vs leaky bucket chosen and justified), load shedding by priority, and bounded-queue backpressure are specified, with the gateway/mesh enforcement point named and handed to the sre owner.
- [ ] Non-idempotent mutations require idempotency keys with a defined dedup store and TTL; at-least-once paths assume idempotent receivers.
- [ ] Each fragile dependency has a defined fallback / graceful-degradation behavior that does not call another fragile dependency, or a documented decision to fail fast.
- [ ] Every accumulating resource has a purge/eviction mechanism (steady-state) with a bound.
- [ ] The composition order of the patterns is drawn in the ADR with the nesting reasoning, and an overall request deadline wraps everything.
- [ ] The ADR names the failure mode each pattern counters; in-code implementation is delegated to the software_engineer `robust_defensive_code` skill and resilience/load testing to the sre `load_and_resilience_testing` skill.
