# High Availability

Design so that any single component can fail without taking the service down, and prove it by failing components on purpose.

High availability is in-region survival of component loss: a pod, a node, an availability zone, a database replica. It is distinct from disaster recovery, which handles losing the whole region (see `disaster_recovery`), and from runtime overload defense, which is in `resilience_and_load_shedding`. The discipline is part arithmetic (availability composes in predictable ways) and part engineering (redundancy only helps when failures are independent).

## Availability math: the nines

Availability is the fraction of time the service meets its SLO. The "nines":

| Availability | Downtime / month | Downtime / year |
| --- | --- | --- |
| 99% | 7.2 h | 3.65 d |
| 99.9% | 43.8 min | 8.76 h |
| 99.95% | 21.9 min | 4.38 h |
| 99.99% | 4.38 min | 52.6 min |
| 99.999% | 26 s | 5.26 min |

This table uses an average month (30.44 days). The error-budget skill computes against a fixed 30-day rolling window, so its 99.9% figure is 43.2 min, not 43.8; keep the basis explicit so the two never look contradictory (see `reliability_targets_sli_slo_sla_error_budgets`).

## Composed dependencies

Availability of components **in series** multiplies, so a chain is always less available than its weakest link. Worked example, a request that must touch four dependencies:

```
compute(99.95%) x db(99.95%) x cache(99.9%) x auth(99.99%)
= 0.9995 * 0.9995 * 0.999 * 0.9999
= 0.99790  ->  99.79%  ->  ~1.5 h/month down
```

Four healthy-looking dependencies compose to below 99.8%. The ceiling on your availability is the product of everything on the critical path, which is why you remove dependencies from that path (cache-aside, async, graceful degradation) rather than only hardening each one.

Redundant components **in parallel** multiply their failure probabilities, which is how redundancy buys nines. Two independent replicas at 99% each:

```
P(both down) = 0.01 * 0.01 = 0.0001  ->  availability 99.99%
```

The decisive word is **independent**. If both replicas share a NAT gateway, an AZ, or a single database primary, the failures correlate and the math collapses back toward a single component. Most "we were multi-AZ but still went down" outages are a hidden shared dependency.

## Redundancy and capacity

Run **N+1** (enough spare to survive one unit failing) or **N+2** for higher tiers. If peak needs M units, run M+1 or M+2 and never plan to run at 100% utilization, or the loss of one unit overloads the rest. Keep headroom (target 60-70% utilization) so the autoscaler and failover have room to react.

## Failover and quorum

For stateful systems, use quorum-based replication (Raft or Paxos) with an **odd** member count (3 or 5) so a majority can always be formed; even counts give no tie-breaker. A write commits only when a majority acknowledges. Verify that failover actually promotes a replica and that the application reconnects; an untested failover usually does not work. Test split-brain handling with fencing (STONITH) so two nodes cannot both believe they are primary.

## Load balancing and health checks

Use L4 balancing for raw throughput and L7 for routing, TLS termination, and header-based decisions. Choose least-connections or consistent hashing where session affinity or cache locality matters, round-robin otherwise. Enable outlier detection so the balancer ejects unhealthy backends automatically.

Separate the health-check kinds:

- **Liveness:** "restart me." Keep it shallow so a slow dependency does not trigger a restart loop.
- **Readiness:** "route traffic to me." Make it deep enough to remove the instance from rotation when a critical dependency is down, so it drains instead of serving errors.
- **Startup:** gives slow-booting services time before liveness applies.

Circuit breakers stop a struggling dependency from consuming all caller resources; their threshold tuning (outlier ejection percentages, retry budgets, timeouts) lives in `resilience_and_load_shedding`.

## Multi-AZ vs multi-region

Span at least two availability zones by default; it is cheap and removes the AZ as a single point of failure. Reach for multi-region only when the SLO and the DR tier justify the cost and the data-consistency complexity, because active-active across regions forces conflict resolution and global routing. Multi-region is as much a DR topology as an HA one (see `disaster_recovery`).

## Common pitfalls

- "Multi-AZ" that shares a single NAT gateway, load-balancer subnet, or database primary: the shared component is the real SPOF and one failure takes everything. Reviewers reject redundancy with a hidden shared dependency.
- Running at 100% utilization with no N+1: the first failure cascades because survivors cannot absorb the load. Size for M+1 with headroom.
- Liveness probes that are deep (call the database): a slow dependency restart-loops healthy pods and amplifies the outage. Keep liveness shallow, readiness deep.
- Readiness probes that pass while the service is useless: the balancer keeps routing to a broken instance. The readiness check must reflect ability to serve.
- Even-numbered quorum members: no majority on a split, so no failover. Use 3 or 5.
- Assuming failover works because it is configured: untested promotion silently fails during the real outage. Test it in game days.
- Synchronized retries without jitter that turn a blip into a thundering herd: covered and bounded in `resilience_and_load_shedding`; do not solve it ad hoc here.

## Definition of done

- [ ] Every critical-path component runs N+1 or higher across at least two availability zones, with no hidden shared dependency.
- [ ] The composed availability of the critical dependency chain is calculated and meets the service SLO.
- [ ] Capacity is sized with headroom (60-70% target utilization), not at saturation.
- [ ] Liveness, readiness, and startup probes are distinct and correctly scoped (shallow liveness, deep readiness).
- [ ] Load balancing uses outlier detection to eject unhealthy backends.
- [ ] Stateful systems use odd-numbered quorum replication with tested, fenced failover.
- [ ] Failover and split-brain handling are exercised in scheduled game days.
- [ ] Multi-region is used only where the SLO and DR tier justify it, and is coordinated with `disaster_recovery`.
- [ ] HA configuration is committed as code, reviewed, and version-controlled per Git Flow and Conventional Commits.
