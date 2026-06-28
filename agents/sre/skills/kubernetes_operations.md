# Kubernetes Operations

Operate workloads on Kubernetes so that every rollout is reversible, every Pod declares how to be probed and how much it may consume, and the cluster sheds and reschedules failures without paging a human. Treat the Deployment spec as the contract: probes, resources, autoscaling, and disruption budgets are not optional polish, they are what makes the workload self-healing. Configuration and secrets are injected, never baked into the image, which keeps this skill aligned with twelve_factor_app.

## Deployments and rollout strategy

A Deployment owns a ReplicaSet which owns Pods. You change the Pod template, the controller rolls a new ReplicaSet, and the old one is kept for rollback.

- Default strategy is `RollingUpdate` with `maxUnavailable: 25%` and `maxSurge: 25%`. For a service that must never drop below its current replica count, set `maxUnavailable: 0` and `maxSurge: 1` so new Pods come up before old ones leave. `Recreate` (kill all, then start all) is only for singletons that cannot run two versions at once (a non-clustered DB migration job, a workload holding an exclusive lock).
- Pin images by digest (`image@sha256:...`) or an immutable tag, never `:latest`. A mutable tag plus `imagePullPolicy: Always` means two replicas of the "same" Deployment can run different code.
- `kubectl rollout status deploy/<name> --timeout=120s` in the pipeline; on non-zero exit, `kubectl rollout undo deploy/<name>`. Keep `revisionHistoryLimit: 10` so undo has targets.
- `minReadySeconds: 10-30` stops a Pod that passes readiness for one scrape but crashes seconds later from cascading the whole rollout.
- Always set `terminationGracePeriodSeconds` (default 30s) to comfortably exceed your longest in-flight request, and handle SIGTERM by draining. A `preStop` `sleep 5-15` hook covers the race where the Pod is still receiving traffic because Endpoints/iptables have not yet converged after it left the Service.
- Progress deadline: `progressDeadlineSeconds: 600` marks a stuck rollout `Failed` instead of hanging forever; wire that condition into the pipeline gate.

For canary or blue-green beyond native rolling updates, use Argo Rollouts or a service mesh (Istio/Linkerd) for weighted traffic, not hand-rolled replica math. Record the rollout decision and the rollback runbook entry with `save_decision`; on a failed rollout, `log_issue` and `log_handoff` to the on-call owner.

## Health probes: liveness, readiness, startup

Three probes, three distinct jobs. Conflating them is the most common cause of self-inflicted outages.

- **Readiness** gates traffic. Failing readiness removes the Pod from Service Endpoints but does not restart it. Use it for "warming up", "downstream dependency unavailable", or "draining". This is the probe that protects users.
- **Liveness** gates restarts. Failing it past `failureThreshold` kills and restarts the container. Reserve it for deadlock/wedged states only. A liveness probe that checks a downstream dependency turns a dependency blip into a cluster-wide restart storm: every replica fails liveness at once, all restart, none serve.
- **Startup** disables the other two until the app has booted. Use it for slow starters (JVM warmup, large model load) so you can keep a tight liveness interval without the startup window tripping it. `failureThreshold * periodSeconds` must exceed worst-case boot time.

```yaml
startupProbe:    { httpGet: { path: /healthz,  port: 8080 }, failureThreshold: 30, periodSeconds: 5 }   # up to 150s to boot
readinessProbe:  { httpGet: { path: /readyz,   port: 8080 }, periodSeconds: 5, timeoutSeconds: 2, failureThreshold: 3 }
livenessProbe:   { httpGet: { path: /livez,    port: 8080 }, periodSeconds: 10, timeoutSeconds: 2, failureThreshold: 3 }
```

- Keep `/livez` cheap and dependency-free (process responsive); put dependency checks in `/readyz`. Separate endpoints, separate semantics.
- Liveness `timeoutSeconds` defaults to 1s; raise it, because a 1s timeout under GC pause or CPU throttling causes spurious restarts.
- Prefer `httpGet`/`grpc` probes over `exec`; exec probes fork a process each period and are expensive at scale.

## Resource requests and limits

Requests drive scheduling and QoS; limits drive throttling and termination. Set them deliberately.

- **CPU**: always set a request (the scheduler needs it; it is also the CFS share weight). Be cautious with CPU limits: a limit throttles via CFS quota and can add tail latency even when the node is idle. Common 2026 practice for latency-sensitive services is request set to the steady-state p90, no CPU limit, and rely on requests plus node headroom. Set CPU limits for batch/noisy-neighbor isolation.
- **Memory**: always set request and limit, and for most workloads set them equal. Memory is incompressible; exceeding the limit gets the container OOMKilled. Equal request/limit gives the `Guaranteed` QoS class, which is evicted last under node memory pressure.
- **QoS classes**: `Guaranteed` (requests == limits for all resources) > `Burstable` (requests < limits) > `BestEffort` (nothing set, evicted first). Run anything user-facing as Guaranteed or tightly-bounded Burstable.
- Right-size from real data: use the Vertical Pod Autoscaler in `recommender`/`Off` mode or metrics-server history to pick requests; do not guess. Over-requesting strands cluster capacity and inflates cost; under-requesting causes OOMKills and evictions.
- Set a namespace `LimitRange` for defaults and a `ResourceQuota` to cap a team's total footprint. Persist the chosen numbers and the data behind them with `save_decision` so the next sizing review is not a fresh guess.

## HorizontalPodAutoscaler and PodDisruptionBudget

- **HPA** scales replica count on a metric. `autoscaling/v2` lets you target CPU, memory, or custom/external metrics. Formula the controller uses: `desiredReplicas = ceil(currentReplicas * currentMetric / targetMetric)`. Target CPU utilization at 60-70% of the request to leave headroom for the scale-up lag.
  - HPA utilization is measured against the **request**, so HPA requires a CPU request to function. No request, no scaling.
  - Set `minReplicas >= 2` for any HA service, and a `maxReplicas` that your cluster autoscaler and downstream (DB connections, quotas) can actually absorb.
  - Tune `behavior.scaleDown.stabilizationWindowSeconds` (default 300s) to avoid flapping; scale up fast, scale down slow.
  - Do not combine HPA and VPA on the same CPU/memory metric; they fight. HPA on CPU + VPA on memory is the supported split.
- **PodDisruptionBudget** caps *voluntary* disruptions (node drains, cluster autoscaler scale-down, upgrades). `minAvailable: N` or `maxUnavailable: N`/`%`. Without a PDB, a node drain can evict every replica at once.
  - `minAvailable` must be strictly less than the replica count, or drains deadlock forever (`kubectl drain` blocks because evicting one would violate the budget). For 3 replicas use `maxUnavailable: 1`, not `minAvailable: 3`.
  - A PDB does not protect against involuntary disruption (node hardware failure, OOM); that is what multiple replicas and anti-affinity are for. Spread replicas with `topologySpreadConstraints` across zones/nodes so one failure domain cannot take the quorum.

## ConfigMaps and Secrets

Config and secrets are injected at runtime, per twelve_factor_app. Read that skill for the config-in-environment principle; this is the Kubernetes mechanism.

- Inject config as env vars (`envFrom: configMapRef`) for small flat values, or mount as a volume for files and large sets. Mounted ConfigMaps/Secrets update in-place (with a propagation delay, tens of seconds); env vars do **not** update a running Pod.
- A ConfigMap/Secret change does not restart Pods. Either roll via a checksum annotation on the Pod template (`checksum/config: <sha256 of data>`) so a content change forces a new ReplicaSet, or use an operator like Reloader. Decide one and apply it everywhere.
- Secrets are base64, not encrypted, by default. Enable **encryption at rest** (`EncryptionConfiguration` with a KMS provider) on etcd, and lock down RBAC: `get`/`list` on Secrets is read access to the credential. For real secret management use the External Secrets Operator pulling from Vault/AWS Secrets Manager/GCP Secret Manager, or Sealed Secrets for GitOps. Never commit a plaintext Secret manifest; it belongs in the secret store, referenced by the manifest.
- `immutable: true` on stable ConfigMaps/Secrets reduces kube-apiserver watch load and prevents accidental edits.

## Troubleshooting the common failure modes

Start every triage with `kubectl get pod <p> -o wide`, `kubectl describe pod <p>` (Events at the bottom), and `kubectl logs <p> --previous` for the crashed container.

- **CrashLoopBackOff**: the container starts and exits repeatedly; kubelet backs off exponentially (10s, 20s, 40s, capped at 5m). Not an error itself, a symptom. Causes: app exits non-zero (read `logs --previous`), failing liveness probe killing a healthy-but-slow app (move the check to startup/readiness, raise thresholds), missing config/secret, bad command/entrypoint. Exit code 0 in a CrashLoop means the process is finishing and the workload should be a Job, not a Deployment.
- **OOMKilled**: container exceeded its memory limit; `describe` shows `Reason: OOMKilled`, exit code 137. Either the limit is too low (raise request and limit together, after measuring) or the app leaks (heap dump, profile). Note 137 = 128 + SIGKILL(9); a node under memory pressure can also OOM-kill via the kernel even within limits if requests are oversubscribed.
- **ImagePullBackOff / ErrImagePull**: kubelet cannot fetch the image. Causes: wrong image/tag/digest, missing or expired registry `imagePullSecrets`, private registry auth, rate limits (Docker Hub), or no network/egress path to the registry. `describe` Events name the exact reason. Fix the reference or the pull secret; do not paper over it by switching to `:latest`.
- **Pending pods**: scheduler cannot place the Pod. `describe` Events give the predicate that failed: `Insufficient cpu/memory` (no node has the requested capacity, fix requests or scale the node pool), unsatisfiable `nodeSelector`/affinity/taints (missing toleration), no zone matching a `topologySpreadConstraint`, or a `PersistentVolumeClaim` that is unbound (no provisioner/storageclass). If the cluster autoscaler is present, a Pending Pod with a valid request is what triggers a scale-up; if it never scales, check the autoscaler logs for `max node group size reached` or unschedulable-due-to-taint.
- **Terminating stuck**: a Pod stuck `Terminating` past its grace period is usually a finalizer or a process ignoring SIGTERM; investigate before force-deleting, because `--force --grace-period=0` on a StatefulSet member risks split-brain.

Record the root cause and the fix in project memory: `log_issue` when you find a recurring failure mode, `save_decision` for the remediation (limit bumped, probe retuned), and `log_handoff` when passing an unresolved incident to the next on-call. Cross-reference incident_response_and_runbooks for the response loop and high_availability for the redundancy this troubleshooting assumes.

## Common pitfalls

- Liveness probe that checks a database or downstream API: a dependency blip restarts every replica simultaneously. Dependency checks belong in readiness.
- A slow-booting app with a tight liveness probe and no startup probe: the container is killed mid-boot and never comes up. Add a startupProbe.
- Memory limit set far above request, or no limit at all, on a leaky app: the node oversubscribes and the kernel OOM-kills neighbors. Set memory request == limit for predictable workloads.
- CPU limit on a latency-sensitive service causing CFS throttling at low overall utilization, showing as tail-latency spikes. Drop the CPU limit or raise it well above p99.
- HPA configured with no CPU request: utilization is undefined and the HPA reports `<unknown>`, never scaling.
- `PDB minAvailable` equal to replica count: node drains and cluster upgrades deadlock permanently.
- Mutable image tag (`:latest`) plus `imagePullPolicy: Always`: replicas of one Deployment silently run different builds; rollback is meaningless.
- Editing a ConfigMap/Secret and expecting running Pods to pick it up: env-var injection never refreshes, and even mounted volumes do not restart the process. Roll the Deployment.
- Secret committed as a base64 manifest in Git, mistaken for encryption. It is encoding. Use a secret store and etcd encryption at rest.
- `kubectl delete pod --force --grace-period=0` as a reflex on a StatefulSet, risking duplicate writes and split-brain.
- `Recreate` strategy left on a user-facing Deployment, causing a full outage on every deploy.

## Definition of done

- [ ] Deployment pins an immutable image (digest or fixed tag), sets `revisionHistoryLimit`, `minReadySeconds`, `progressDeadlineSeconds`, and a `RollingUpdate` surge/unavailable policy matched to the HA requirement.
- [ ] `kubectl rollout status` gates the pipeline and `rollout undo` is the documented, tested rollback path.
- [ ] Readiness gates traffic, liveness is dependency-free and reserved for wedged states, and slow starters have a startupProbe whose budget exceeds worst-case boot.
- [ ] Every container sets CPU and memory requests; memory limit is set (and == request for predictable workloads); CPU-limit choice is justified against throttling.
- [ ] HPA targets 60-70% of the CPU request, `minReplicas >= 2`, a sane `maxReplicas`, and a scale-down stabilization window; HPA and VPA do not contend on the same metric.
- [ ] A PDB protects every multi-replica service with `minAvailable` strictly below replica count, and replicas are spread across failure domains with topology constraints.
- [ ] Config and secrets are injected (per twelve_factor_app), a content change forces a roll (checksum annotation or Reloader), etcd encryption at rest is on, and real secrets come from a secret store, never a committed manifest.
- [ ] Runbook entries exist for CrashLoopBackOff, OOMKilled, ImagePullBackOff, and Pending pods, each naming the `describe`/`logs --previous` triage step and the fix.
- [ ] Sizing, rollout, and remediation decisions are persisted with `save_decision`; recurring failures are captured with `log_issue` and unresolved incidents handed off with `log_handoff`.
