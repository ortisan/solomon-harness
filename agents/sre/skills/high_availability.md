## High availability


Design so that any single component can fail without taking down the service.

- **Eliminate SPOFs.** Run N+1 (survive one failure) or N+2 capacity. Spread across at least two availability zones; reach for multi-region only when the SLO and DR tier justify the cost and complexity.
- **Health checks**: separate liveness (restart me) from readiness (route traffic to me). Keep liveness shallow so a slow dependency does not trigger a restart loop; make readiness deep enough to drain on dependency failure. Add startup probes for slow-booting services.
- **Load balancing**: L4 for raw throughput, L7 for routing and TLS termination. Use least-connections or consistent hashing where session affinity or cache locality matters; round-robin otherwise. Configure outlier detection to eject unhealthy backends.
- **Resilience patterns**: timeouts on every outbound call (never unbounded), retries with exponential backoff plus jitter, retry budgets to prevent retry storms, circuit breakers, bulkheads to isolate pools, and load shedding that drops the lowest-priority traffic first. Prefer graceful degradation (serve stale cache, reduced features) over hard failure.
- **Autoscaling**: HPA on the signal that actually correlates with load (RPS or queue depth often beat CPU). Set sane min replicas for redundancy and max for cost control. Keep headroom; an autoscaler cannot save you from a cold-start stampede. Test scale-down behavior, not just scale-up.
- **Stateful systems**: use quorum-based replication (Raft/Paxos) and verify the failover actually promotes a replica. Test split-brain handling.
- Pitfalls: synchronized retries without jitter, health checks that pass while the service is useless, autoscaling on a lagging metric, "multi-AZ" that shares a single NAT gateway or database primary.
