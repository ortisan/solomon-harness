# Twelve-Factor App at Runtime

Run the workload so the same immutable image moves through every environment, all variable state lives in injected config and attached backing services, and each process can be killed, restarted, or scaled out at any instant without data loss or dropped requests. This skill is the operational reading of the twelve factors (https://12factor.net): how each one lands in a container image, a Deployment spec, and the surrounding platform. The architectural rationale (why statelessness and design contracts) belongs to `software_architect`; this skill governs the runtime contract you enforce in the manifest and the pipeline.

## Config and secrets from the environment (factor III)

Config that varies between deploys (endpoints, credentials, feature flags, tunables) is injected at runtime. It is never baked into the image. One image must boot identically in dev, staging, and prod, differentiated only by what the environment hands it. The test: could you open-source the image right now without leaking a single credential?

- Non-secret config goes in a `ConfigMap`; secrets go in a `Secret` (or, preferably, a cloud secret manager surfaced by External Secrets Operator, ESO 0.10+, or the Secrets Store CSI driver). Sync from Vault/AWS Secrets Manager/GCP Secret Manager so the cluster `Secret` is a projection, not the system of record. Storage, encryption, and rotation policy are owned by `security` (`secrets_handling.md`); this skill owns the injection mechanism.
- Prefer mounting secrets as files over `env`. Environment variables leak into crash dumps, `/proc/<pid>/environ`, child processes, and many logging libraries; a mounted file with `defaultMode: 0400` does not.

```yaml
containers:
  - name: api
    image: registry.internal/api@sha256:7b1f...   # pin by digest, never :latest
    envFrom:
      - configMapRef: { name: api-config }
    env:
      - name: DATABASE_URL
        valueFrom: { secretKeyRef: { name: api-db, key: url } }
    volumeMounts:
      - name: tls
        mountPath: /etc/tls
        readOnly: true
volumes:
  - name: tls
    secret:
      secretName: api-tls
      defaultMode: 0400
```

- Env-injected config does not hot-reload. Changing a `ConfigMap` does not restart pods. Either roll the Deployment explicitly or run Stakater Reloader (annotate with `reloader.stakater.com/auto: "true"`) so a config change triggers a rollout. Mounted-file config can be re-read, but only if the app watches the file.
- Set `enableServiceLinks: false` on the pod spec. Kubernetes otherwise injects a `*_SERVICE_HOST` env var for every Service in the namespace, polluting the environment and occasionally colliding with your own config keys.

## Backing services as swappable attached resources (factor IV)

Databases, queues, caches, object stores, and third-party APIs are attached resources addressed only through a connection string in config. Swapping a local Postgres for RDS, or failing over to a replica, is a config change and a pod restart, with zero code change.

- Never hard-code a hostname or embed a connection in the image. Resolve backing services through their URL in config; inside the cluster, address them by Service DNS (`db.data.svc.cluster.local`) or an `ExternalName` Service that aliases the managed endpoint, so the app target stays stable while the backend moves.
- Open connection pools lazily and make them reconnect. A backing-service failover must heal without a pod restart; a pool that caches a dead socket forever turns a 5-second failover into an outage.
- Bound every outbound call with a timeout and a circuit breaker. Resilience patterns are detailed in `high_availability.md`; the twelve-factor requirement is simply that the resource is detachable and re-attachable at runtime.

## Build, release, run: immutable releases (factor V)

Three strictly separated stages. Build turns source into an image. Release joins that exact image to a config. Run executes the release. A release is immutable and uniquely identified; you never edit code or config in a running container, and any change produces a new release.

- Build once, promote the same digest. The artifact that passed staging is the artifact that reaches prod, byte for byte. Rebuilding per environment breaks dev/prod parity (factor X) and invalidates every test you ran. The pipeline stages, signing, and SBOM generation are owned by `infrastructure_and_deployment_pipelines.md`.
- A release = image digest + resolved config, captured in the rendered manifest under Git (GitOps). This gives you a versioned, append-only release ledger and makes rollback a revert to the previous release, not a rebuild.
- Codebase and dependencies (factors I and II) are the build-stage half of this: one repo, many deploys via Kustomize overlays or Helm values, not a branch per environment. Pin the base image by digest and pin lockfiles (`uv.lock`, `package-lock.json`); install nothing at container start. Prefer distroless or minimal bases so the image is the explicit, isolated dependency boundary.
- Dev/prod parity (factor X) is enforced in CI: same image, same backing-service types (real Postgres in CI via Testcontainers, not SQLite standing in for Postgres), config the only delta. Time, personnel, and tooling gaps between dev and prod are the defects this factor exists to close.

## Stateless and disposable processes (factors VI and IX)

Processes are share-nothing and disposable: they hold no durable local state, start fast, and shut down cleanly on demand. This is the factor SREs get paged for, so it gets the most detail.

Stateless (VI): any state that must survive a restart lives in a backing service. No session affinity, no in-memory caches treated as durable, no writing user data to the container filesystem. `emptyDir` is scratch space that dies with the pod, never a store of record. If you need sticky sessions, that is a design defect to flag back to `software_architect`.

Disposable (IX): fast startup and graceful shutdown. Kubernetes terminates a pod by sending `SIGTERM`, waiting up to `terminationGracePeriodSeconds` (default 30), then `SIGKILL`. The trap is that endpoint removal and `SIGTERM` are dispatched concurrently, so for a few seconds kube-proxy/the load balancer can still route to a pod that has begun shutting down. The fix is a `preStop` sleep that delays shutdown until endpoint deletion has propagated, paired with an application `SIGTERM` handler that drains in-flight work.

```yaml
spec:
  terminationGracePeriodSeconds: 45   # must exceed preStop sleep + worst-case drain
  containers:
    - name: api
      lifecycle:
        preStop:
          exec: { command: ["/bin/sh", "-c", "sleep 10"] }   # let endpoints converge
```

```python
import signal, threading

_shutdown = threading.Event()

def _on_sigterm(*_):
    # Stop accepting new work, then let the server drain in-flight requests.
    _shutdown.set()
    server.stop(grace=30)   # gRPC: refuse new RPCs, finish active ones within 30s

signal.signal(signal.SIGTERM, _on_sigterm)
```

- The process must trap `SIGTERM`. A container whose PID 1 ignores it (common when the app runs under a shell that does not forward signals) gets `SIGKILL` after the grace period, dropping every in-flight request. Use an exec-form `ENTRYPOINT` or a minimal init like `tini` so signals reach the app as PID 1.
- Make `terminationGracePeriodSeconds` longer than `preStop sleep + max drain time`. A 10s sleep with a 30s grace leaves only 20s to drain; size it to the slowest legitimate request.
- Workers and consumers must be crash-only: idempotent and safe to kill mid-task. Use at-least-once queues with visibility timeouts so an unacknowledged job is redelivered after a `SIGKILL`. Never assume a worker finishes what it started.
- Startup must be fast and gated by a `startupProbe` so slow boots do not trip the liveness probe into a restart loop. Probe semantics (liveness vs readiness vs startup, and draining on readiness failure) are owned by `high_availability.md`.
- For sidecars (proxy, log shipper), use native sidecar containers (`initContainers` with `restartPolicy: Always`, GA in Kubernetes 1.33). They start before and terminate after the main container, so your app can still reach the mesh proxy while draining instead of losing it mid-shutdown.

## Concurrency and horizontal scale (factors VIII and VII)

Scale by running more processes, not by growing one. Each workload type is a first-class process: web requests, async workers, and schedulers are separate Deployments scaled independently. The app exports its service purely by binding a port (factor VII): a self-contained server listening on `containerPort`, with no externally injected web server (no Apache/PHP-FPM coupling), so the same process model runs locally and in the cluster.

- Scale out with replicas and an `HorizontalPodAutoscaler` (`autoscaling/v2`). Scale on the signal that tracks load: requests-per-second or queue depth usually beats CPU. CPU-based HPA only works if you set CPU `requests`.
- For queue-driven workers, use KEDA (2.14+) to scale on queue length, including scale-to-zero when idle. A backlog, not CPU, is the honest load signal for a consumer.
- Set resource `requests` on every container so the scheduler can place pods and the HPA has a baseline. Set memory `limit == request` to get predictable OOM behavior; be cautious with CPU limits, which cause CFS throttling and tail-latency spikes on latency-sensitive services. In-place pod resize (GA in Kubernetes 1.33) lets you adjust requests without a restart.
- Protect availability during voluntary disruptions (node drains, rollouts) with a `PodDisruptionBudget` (`minAvailable`) so scale-out redundancy is not erased by a cluster operation.

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  scaleTargetRef: { apiVersion: apps/v1, kind: Deployment, name: api }
  minReplicas: 3            # redundancy floor, not 1
  maxReplicas: 30
  metrics:
    - type: Pods
      pods:
        metric: { name: http_requests_per_second }
        target: { type: AverageValue, averageValue: "200" }
```

## Logs as event streams (factor XI)

The process writes its log stream, unbuffered, to `stdout`/`stderr` and is otherwise oblivious to storage and routing. It never writes log files, never rotates logs, and never ships them itself. The platform captures both streams and a node agent (Fluent Bit 3.x, Vector, or the vendor agent) forwards them to the aggregator (Loki, Elasticsearch/OpenSearch, Cloud Logging).

- Disable application-side buffering so logs are not lost on `SIGKILL`. In Python set `PYTHONUNBUFFERED=1` (or `flush=True`); a buffered crash swallows the most important lines.
- Emit structured JSON, one event per line, with a trace/correlation id. The log schema, levels, and tracing-context fields are owned by `observability` (`logging.md`, `opentelemetry_instrumentation.md`); this skill only mandates that the destination is the standard streams.
- Writing to a file inside the container couples logging to ephemeral disk, fills the node, and loses everything on pod deletion. If a third-party component insists on a log file, tail it to `stdout` with a sidecar rather than persisting it.

## Admin and one-off processes (factor XII)

Migrations, backfills, REPL sessions, and one-off scripts run in the release environment, against the same image and config as long-running processes, as ephemeral processes that exit. They are not SSH sessions on a mutable host and not a separately built tool image that can drift from prod.

- Run one-off tasks as a `Job` (or `kubectl run --rm -it --image=<same-digest>`) so they inherit the release's image and config. Schema migrations run as a `Job` or an `initContainer` using the release image, gated before the new version serves traffic, and must be backward-compatible (expand/contract) per `infrastructure_and_deployment_pipelines.md` so old and new pods coexist during the rollout.
- Never `kubectl exec` into a running app pod to mutate state as routine practice. It bypasses the release ledger, leaves no audit trail, and is the antithesis of an immutable, reproducible deploy.

## Common pitfalls

- `:latest` or a mutable tag in the manifest. Two nodes pull different bytes and a rollback is undefined. Pin by `@sha256:` digest.
- Secrets baked into the image or passed only as env vars, leaking via `/proc`, crash dumps, and child processes. Mount as files with `0400`; project from a secret manager via ESO/CSI.
- Rebuilding the image per environment instead of promoting one digest, which discards every test result and breaks dev/prod parity.
- No `SIGTERM` handler, or an app not running as PID 1, so the process is `SIGKILL`ed after the grace period and drops in-flight requests.
- `preStop` sleep missing, so pods receive traffic for seconds after termination starts because endpoint removal had not yet propagated.
- `terminationGracePeriodSeconds` shorter than `preStop sleep + drain time`, guaranteeing forced kills mid-request.
- State on local disk or in process memory treated as durable (sticky sessions, in-memory cache as store of record), so any restart or scale-down loses data.
- App writing to log files and rotating them itself, filling the node and losing logs on pod deletion; or buffered stdout that is lost on crash.
- HPA configured on CPU with no CPU `request` set, so it never scales; or `minReplicas: 1`, which removes redundancy.
- CPU `limit` set tight on a latency-sensitive service, causing CFS throttling and tail-latency spikes that look like a code regression.
- One-off admin work done by `kubectl exec` into a live pod or from a drifted tool image, bypassing the release and the audit trail.

## Definition of done

- [ ] The same image digest, pinned by `@sha256:`, is promoted unchanged from CI through prod; nothing is rebuilt or `apt-get install`ed at container start.
- [ ] All deploy-varying config is injected from `ConfigMap`/`Secret` (or a secret manager via ESO/CSI); no credential is present in the image, and secrets are mounted as `0400` files where feasible.
- [ ] Backing services are addressed only through config-supplied URLs/Service DNS; failover and resource swaps need only a config change and restart, and pools reconnect without a restart.
- [ ] Each release is an immutable image+config recorded in Git; rollback is a revert to the prior release, not a rebuild.
- [ ] Processes are stateless: no durable local-disk or in-memory state, no sticky sessions; all persistent state is in a backing service.
- [ ] Pods handle `SIGTERM` (app as PID 1), have a `preStop` delay covering endpoint propagation, and a `terminationGracePeriodSeconds` exceeding `preStop + drain`; workers are idempotent and crash-safe.
- [ ] Each workload type is its own horizontally scalable Deployment with resource `requests` set, an HPA/KEDA on a load-correlated metric, `minReplicas >= 2`, and a `PodDisruptionBudget`.
- [ ] The app logs unbuffered JSON to `stdout`/`stderr` and ships nothing itself; the platform agent forwards to the aggregator.
- [ ] Migrations and one-off tasks run as `Job`s on the release image and config, are expand/contract compatible, and no routine state change is done via `kubectl exec` into a live pod.
- [ ] Dev/prod parity is enforced in CI with the same image and real backing-service types; config is the only environment delta.
