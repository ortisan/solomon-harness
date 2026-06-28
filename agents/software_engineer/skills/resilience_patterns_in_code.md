# Resilience Patterns in Code

Wrap every outbound call (HTTP, gRPC, DB, queue, third-party SDK) in an explicit resilience stack so a slow or failing dependency degrades one feature instead of exhausting threads and taking down the process. This skill is the how-to-build: real libraries, exact config, and the composition order. For the catalog of patterns and the decision of which dependency needs which pattern, defer to the software_architect `resilience_patterns` skill; for cluster-level timeouts, load-balancer outlier ejection, retry budgets at the mesh, and chaos gamedays, defer to the sre `high_availability` and `load_and_resilience_testing` skills. Here we write the client code.

## Composition order: nest from the outside in

There are two timeouts, not one, and the patterns nest in a fixed order. From outermost to innermost:

```
overall deadline  ->  retry  ->  circuit breaker  ->  rate limiter  ->  bulkhead  ->  per-attempt timeout  ->  call
```

The reasons each boundary sits where it does:

- **Overall deadline (outermost):** bounds the whole operation including all retries and backoff sleeps, so a caller upstream is never blocked past its own budget. Without it, three retries with backoff can silently exceed an 8s SLA.
- **Retry outside the breaker:** each attempt passes through and reports to the breaker. When the breaker opens, the next attempt fails fast and the retry policy must treat the open-circuit error as non-retriable so it stops immediately. Retrying inside the breaker hides failures from it and defeats the trip.
- **Per-attempt timeout (innermost):** each individual call gets its own short timeout. Without it, retries inherit one long timeout and a hung socket consumes the whole deadline on attempt one.

Resilience4j's documented aspect order is exactly this: `Retry( CircuitBreaker( RateLimiter( TimeLimiter( Bulkhead( fn )))))`. Microsoft's `AddStandardResilienceHandler()` ships the same stack. Match it when you wire patterns by hand.

## Retry with exponential backoff and jitter

Rules that hold across every language:

- Retry only **idempotent** operations on **transient** faults: connection errors, read timeouts, and `429/502/503/504`. Never retry `400/401/403/404/409/422` or any business validation error; the result will not change.
- Backoff is exponential with a base of `200ms`, multiplier `2`, capped at `5s`. **Jitter is mandatory** (full or decorrelated) so retries from many clients do not align into a synchronized thundering herd.
- Cap total attempts at **3** (one try plus two retries). More attempts amplify load on a struggling dependency. Honor `Retry-After` on a `429/503` over computed backoff.
- Add a retry budget when you can: cap retries to roughly 10% of requests so a broad outage does not turn into a retry storm. At the mesh layer this is the sre's concern; in-process, track it with a sliding counter.

Python with `tenacity` 9.x and `httpx`, showing the retry wrapped around a breakered, per-attempt-timed call:

```python
import httpx, pybreaker
from tenacity import (retry, stop_after_attempt, stop_after_delay,
                      wait_exponential_jitter, retry_if_exception_type)

class Retryable(Exception):
    """Transient backend fault worth retrying (429/5xx)."""

breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=30)

@breaker  # records every attempt; raises CircuitBreakerError fast when OPEN
def _attempt(client: httpx.Client, url: str, idem_key: str) -> httpx.Response:
    r = client.post(url, timeout=httpx.Timeout(1.0, connect=0.5),   # per-attempt timeout
                    headers={"Idempotency-Key": idem_key})
    if r.status_code in (429, 502, 503, 504):
        raise Retryable(r.status_code)        # other 4xx fall through and are NOT retried
    r.raise_for_status()
    return r

@retry(
    stop=(stop_after_attempt(3) | stop_after_delay(8)),     # 3 tries OR 8s deadline
    wait=wait_exponential_jitter(initial=0.2, max=5, jitter=2),
    retry=retry_if_exception_type((httpx.TransportError, Retryable)),  # not CircuitBreakerError
    reraise=True,
)
def fetch(client, url, idem_key):
    return _attempt(client, url, idem_key)
```

`CircuitBreakerError` is absent from the retry set, so an open breaker propagates immediately instead of being hammered. JVM, .NET, and Node equivalents below configure the identical numbers.

## Circuit breakers

A breaker stops sending calls to a dependency that is already failing, giving it room to recover and failing the caller fast. Prefer a **failure-rate** breaker over a consecutive-count one for any non-trivial traffic: rate over a sliding window does not trip on a brief blip and does not stay closed through a slow bleed.

Threshold defaults that work in production:

- **Failure-rate threshold:** `50%` over a sliding window of `20` calls, with a `minimum-number-of-calls` of `10` so the rate is statistically meaningful before it can trip.
- **Slow-call threshold:** treat calls slower than `2s` as failures once `80%` of the window is slow, so a dependency that is "up but crawling" still opens the breaker.
- **Open state:** stay open `30s`, then move to half-open automatically.
- **Half-open probes:** permit `5` trial calls; if they pass, close; if any fail, re-open for another `30s`.

Resilience4j 2.x (`application.yml`, Spring Boot 3), the canonical reference config:

```yaml
resilience4j:
  retry:
    instances:
      payments:
        max-attempts: 3
        wait-duration: 200ms
        exponential-backoff-multiplier: 2
        randomized-wait-factor: 0.5                 # +-50% jitter
        retry-exceptions: [java.io.IOException, java.util.concurrent.TimeoutException]
        ignore-exceptions:                          # never retry an open breaker
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException
  circuitbreaker:
    instances:
      payments:
        sliding-window-type: COUNT_BASED
        sliding-window-size: 20
        minimum-number-of-calls: 10
        failure-rate-threshold: 50
        slow-call-rate-threshold: 80
        slow-call-duration-threshold: 2s
        wait-duration-in-open-state: 30s
        permitted-number-of-calls-in-half-open-state: 5
        automatic-transition-from-open-to-half-open-enabled: true
  timelimiter:
    instances: { payments: { timeout-duration: 1s, cancel-running-future: true } }
  bulkhead:
    instances: { payments: { max-concurrent-calls: 25, max-wait-duration: 0 } }
```

.NET with Polly v8 (`Microsoft.Extensions.Resilience` 9.x). `AddStandardResilienceHandler()` already produces this stack; build it by hand only to override defaults:

```csharp
var pipeline = new ResiliencePipelineBuilder<HttpResponseMessage>()
    .AddTimeout(TimeSpan.FromSeconds(8))                         // outermost deadline
    .AddRetry(new RetryStrategyOptions<HttpResponseMessage> {
        MaxRetryAttempts = 2, Delay = TimeSpan.FromMilliseconds(200),
        BackoffType = DelayBackoffType.Exponential, UseJitter = true,
        ShouldHandle = new PredicateBuilder<HttpResponseMessage>()
            .Handle<HttpRequestException>().Handle<TimeoutRejectedException>()
            .HandleResult(r => (int)r.StatusCode is 429 or 502 or 503 or 504) })
    .AddCircuitBreaker(new CircuitBreakerStrategyOptions<HttpResponseMessage> {
        FailureRatio = 0.5, MinimumThroughput = 20,
        SamplingDuration = TimeSpan.FromSeconds(30),
        BreakDuration = TimeSpan.FromSeconds(30) })
    .AddTimeout(TimeSpan.FromSeconds(1))                         // innermost per-attempt
    .Build();
```

Node with `opossum` 8.x (pair with `p-retry` 6.x for the retry layer, since opossum has none):

```js
const CircuitBreaker = require('opossum');
const breaker = new CircuitBreaker(callBackend, {
  timeout: 1000,                 // per-call timeout, counted as a failure
  errorThresholdPercentage: 50,  // open at 50% failure rate
  volumeThreshold: 20,           // need >=20 calls before it can trip
  resetTimeout: 30000,           // ms OPEN before a half-open probe
  rollingCountTimeout: 10000, rollingCountBuckets: 10,
});
breaker.fallback(() => cachedOrDegradedResponse());   // serve stale over hard-failing
breaker.on('open', () => metrics.increment('breaker.payments.open'));
```

Export breaker state transitions and `half_open` probe results as metrics; see the observability `metrics` and `distributed_tracing` skills for how to surface them on dashboards.

## Timeouts and deadline propagation

- Every outbound call sets an explicit timeout. An unbounded call is the most common cause of cascading thread-pool exhaustion. Set both a connect timeout (`500ms`) and a read timeout (`1s` typical for an interactive path).
- **Propagate the deadline, do not reset it.** When service A calls B with a 2s budget and B calls C, C must get the *remaining* time, not a fresh 2s. Carry a deadline through the call chain and shrink it at each hop.

```python
import time
def remaining_timeout(deadline: float, floor: float = 0.05) -> float:
    left = deadline - time.monotonic()
    if left < floor:
        raise TimeoutError("deadline already exceeded; do not start a doomed call")
    return left
```

gRPC carries this natively as `grpc-timeout`; for HTTP, pass `X-Request-Deadline` and convert it to a per-call timeout on receipt. A per-attempt timeout must always be shorter than the overall deadline, or the retry layer never gets a second chance.

## Bulkheads and client-side rate limiting

A **bulkhead** caps concurrent in-flight calls to one dependency so it cannot consume every worker. Use one bounded pool or semaphore per dependency, never a single shared pool.

```python
import asyncio
payments = asyncio.Semaphore(25)        # at most 25 concurrent calls to this dependency
inventory = asyncio.Semaphore(50)       # separate pool: a slow payments dep cannot starve it

async def call_payments(client, url, key):
    async with payments:                # rejects/queues past the cap instead of unbounded fan-out
        return await fetch(client, url, key)
```

For thread-based stacks use a bounded `ThreadPoolExecutor(max_workers=25)` with a bounded queue per dependency. Resilience4j offers `SemaphoreBulkhead` and `ThreadPoolBulkhead`; Polly has `AddConcurrencyLimiter`.

**Client-side rate limiting** keeps you under a partner's quota and smooths bursts. Use a token-bucket: steady rate plus a small burst.

```python
from aiolimiter import AsyncLimiter
limiter = AsyncLimiter(max_rate=100, time_period=1)   # 100 permits/sec, token-bucket
async with limiter:
    await call_partner()
```

`pyrate-limiter` 3.x for sync/multi-tier limits, Resilience4j `RateLimiter`, Polly's `TokenBucketRateLimiter` (from `System.Threading.RateLimiting`), and Node's `bottleneck` are the same pattern in each ecosystem. A `429` from the server means your client-side limit is set too high; tighten it rather than relying on retries.

## Idempotency keys: what makes retries safe

Retrying a non-idempotent write (charge a card, send an email, create an order) risks duplicate side effects. An idempotency key is the contract that makes the retry a no-op on the server.

- The **client** generates a UUIDv4 per logical operation and sends it as an `Idempotency-Key` header. It reuses the *same* key across all retries of that operation; a new attempt of the same intent is not a new key.
- The **server** persists `key -> (status, stored_response)` scoped to endpoint plus account, with a TTL (Stripe's is 24h). A duplicate key whose first request completed replays the stored response; one still in flight returns `409` or blocks. Make the persist-and-respond atomic so two concurrent retries cannot both execute.
- `GET`, `PUT`, and `DELETE` are idempotent by definition and retry freely. Only `POST`-style creates need the key.

This is where the engineer's `robust_defensive_code` boundary-validation discipline applies: validate the key format and scope before trusting it.

## Failure-injection testing

Prove the patterns fire before production does. Unit and integration tests are mandatory per the project TDD rules.

- **Unit:** inject a fault with a fake transport (`httpx.MockTransport`) that returns `503` N times then `200`. Assert exactly `N+1` attempts ran, that backoff was applied, and that the breaker opened after the configured count. Mock all external calls; do not hit the network in unit tests.
- **Integration:** put **Toxiproxy** (Shopify) between the app and the real dependency and add `latency`, `timeout`, and `reset_peer` toxics to prove the per-attempt timeout and breaker trip under genuine socket conditions.
- **Orchestrated chaos** (`chaostoolkit`, Chaos Mesh, AZ-kill gamedays) is the sre agent's `load_and_resilience_testing` territory; coordinate, do not duplicate it here.

## Common pitfalls

- Retrying without jitter, so synchronized clients form a thundering herd that re-DDoSes the recovering dependency.
- Retrying non-idempotent writes with no idempotency key, producing duplicate charges or orders.
- Retrying `4xx` (other than `429`), business-validation errors, or an open-circuit error; the outcome cannot change and you just add load.
- A single timeout for the whole operation instead of a per-attempt timeout plus an overall deadline, so one hung call burns the entire budget.
- Unbounded outbound calls (no timeout at all), the root cause of thread-pool and connection-pool exhaustion.
- One shared thread pool for all dependencies, so one slow backend starves every other call. Bulkhead per dependency.
- A consecutive-count breaker on high-traffic paths that never trips on a partial (40%) failure rate; use a failure-rate window.
- Breaker placed inside the retry with no exclusion, so the retry hammers an open circuit and the breaker can never short-circuit the caller.
- Resetting the deadline to full at each hop instead of propagating the remaining budget, so a deep call chain blows the top-level SLA.
- Catching the open-circuit exception and silently returning success-shaped empty data, hiding the outage from callers and metrics.

## Definition of done

- [ ] Every outbound call has an explicit connect and read timeout; no unbounded calls remain.
- [ ] Patterns nest in the order overall-deadline -> retry -> circuit breaker -> rate limiter -> bulkhead -> per-attempt timeout, with a per-attempt timeout strictly shorter than the deadline.
- [ ] Retry is capped at 3 attempts, uses exponential backoff with jitter, retries only idempotent operations on transient faults, honors `Retry-After`, and never retries an open-circuit error.
- [ ] Circuit breaker uses a failure-rate threshold (50% over a >=20-call window with a 10-call minimum), a slow-call threshold, a 30s open state, and bounded half-open probes; state transitions are emitted as metrics.
- [ ] Bulkheads are per dependency (bounded semaphore or thread pool), and client-side rate limiting uses a token bucket sized below the partner quota.
- [ ] Non-idempotent writes carry a client-generated `Idempotency-Key` reused across retries, with atomic server-side dedup and a defined TTL.
- [ ] Deadlines propagate across hops as remaining time, not a reset budget.
- [ ] Failure-injection tests (fake transport for units, Toxiproxy for integration) prove retries fire, the breaker opens and recovers, timeouts trip, and bulkheads reject past the cap; all external calls are mocked in unit tests.
- [ ] Cross-references honored: architecture and when-to-use deferred to software_architect `resilience_patterns`, infra-level resilience and chaos to the sre skills, dashboards to observability `metrics`.
