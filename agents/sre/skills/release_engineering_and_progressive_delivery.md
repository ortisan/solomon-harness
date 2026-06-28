# Release Engineering and Progressive Delivery

Ship every change to a small, observed slice first, let automated analysis against SLOs decide whether to promote or abort, and keep a rollback that is one command and completes in minutes. The job is to make a bad release boring: bound its blast radius, detect it from error-budget burn, and undo it before users notice. This skill is the rollout mechanics; reliability targets and the error-budget policy come from sibling skill `reliability_targets_sli_slo_sla_error_budgets`, the surrounding CI/CD and IaC from `infrastructure_and_deployment_pipelines`, and the application-level rollout sequencing (expand/contract, dual-run, strangler) from software_architect's `incremental_migration_and_delivery`.

## Choosing a strategy

Pick by blast radius, statefulness, and cost, not by habit.

- **Rolling update**: replace pods batch by batch. The Kubernetes default. Cheap (no extra capacity), but old and new run concurrently with no traffic gating, so a bad version takes proportional traffic before you notice. Use for low-risk, backward-compatible changes. Always set `maxUnavailable: 0` and a small `maxSurge` (1 or 25%) plus a real `readinessProbe`, or you shed capacity mid-roll.
- **Blue-green**: stand up the full new version (green) alongside the live one (blue), smoke-test green out of band, then flip 100% of traffic at once. Instant rollback (flip back). Costs 2x capacity during the window and gives no progressive signal, so a fault that only appears under real load hits everyone at the switch. Use when you cannot run mixed versions safely (heavy schema coupling, stateful singletons) and need an atomic cutover.
- **Canary**: route a small fraction (start 5%) to the new version, analyze, then step up (5 -> 25 -> 50 -> 100) with pauses. The default for any change touching the request path. Needs traffic-splitting (service mesh or ingress) and good per-version metrics. Best blast-radius control and the only strategy that gives an early automated verdict.

Canary is the target for user-facing services; blue-green is the fallback when mixed versions are unsafe; rolling is for internal or trivially safe changes.

## Canary with Argo Rollouts or Flagger

Both replace the bare Deployment with a controller that owns traffic weight and pause/promote/abort.

- **Argo Rollouts** (1.8+): a `Rollout` CRD with explicit `steps` (setWeight/pause) and inline `analysis`. Traffic shaping via the SMI, Istio, NGINX, ALB, or the Gateway API plugin. `kubectl argo rollouts` promotes/aborts; pairs with Argo CD GitOps.
- **Flagger**: a `Canary` CRD that drives an existing Deployment, automating stepwise weight and analysis from `metrics` + webhooks; works with Istio, Linkerd, App Mesh, NGINX, Gateway API.

Use Argo Rollouts when you want fine-grained, hand-tuned step control and a single CD tool; Flagger when you want convention-driven canaries over plain Deployments. Do not run both on the same workload.

```yaml
# Argo Rollouts: weight steps gated by analysis; abort halts and scales the canary to zero.
apiVersion: argoproj.io/v1alpha1
kind: Rollout
spec:
  strategy:
    canary:
      canaryService: app-canary
      stableService: app-stable
      trafficRouting:
        gatewayAPI: { httpRoute: app-route, namespace: app }
      steps:
        - setWeight: 5
        - pause: { duration: 5m }     # bake time: long enough for the SLI to move
        - analysis: { templates: [ { templateName: slo-gate } ] }
        - setWeight: 25
        - pause: { duration: 10m }
        - setWeight: 50
        - analysis: { templates: [ { templateName: slo-gate } ] }
        - setWeight: 100
```

```yaml
# AnalysisTemplate: success-rate gate from Prometheus. failureLimit aborts the rollout.
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata: { name: slo-gate }
spec:
  metrics:
    - name: success-rate
      interval: 1m
      count: 5
      successCondition: result >= 0.99      # >= 99% non-5xx on the canary
      failureLimit: 1                        # one breach -> abort + rollback
      provider:
        prometheus:
          address: http://prometheus.monitoring:9090
          query: |
            sum(rate(http_requests_total{service="app-canary",code!~"5.."}[2m]))
            / sum(rate(http_requests_total{service="app-canary"}[2m]))
```

Rules that keep canary analysis honest:

- Compare canary against the **stable baseline running concurrently**, not against last week's numbers. Deploy a baseline replica of the old version so both see the same live traffic mix; absolute thresholds drift with diurnal load.
- Bake time per step must exceed the metric scrape/aggregation window (a 1m Prometheus rate needs >= 2-3m pause) or you promote on noise.
- Gate on the same SLIs your SLOs use: success rate, latency p95/p99, and saturation. Add app-specific guards (error logs, business KPI) as extra metrics, never as the only signal.
- Set a hard maximum rollout duration; a canary that never reaches a verdict is a stuck release, not a safe one.

## Automated analysis and rollback on error-budget burn

The promote/abort decision is an SLO question. Use **multi-window, multi-burn-rate** alerting (Google SRE workbook) so the gate reacts fast to severe regressions and ignores noise.

- Burn rate = (observed error rate) / (1 - SLO target). At a 99.9% SLO the budget is 0.1%; a 1% error rate burns at 10x.
- Fast gate: burn rate >= 14.4x over a 1h long window with a 5m short window confirming (consumes ~2% of a 30-day budget in 1h) -> abort immediately.
- Slow gate: burn rate >= 6x over 6h with a 30m confirm -> abort before promotion.
- Wire these as the `successCondition`/`failureLimit` on the analysis step so a burst of errors in the canary aborts within minutes, while a small steady elevation still blocks promotion without thrashing.
- On abort the controller stops stepping, drops canary weight to zero, and scales the canary down; stable keeps serving. That is the automated rollback. Record it: `save_decision` for the abort and its trigger, `log_issue` to open the regression for follow-up, and `log_handoff` so the next on-call inherits why traffic is pinned to stable.

## One-command rollback and immutability

- Every deployable is an immutable, signed artifact addressed by digest, never a moving tag like `latest`. Rollback = repoint to the previous known-good digest, which must already exist.
- Provide exactly one rollback command and rehearse it: `kubectl argo rollouts undo <rollout>` (or `argocd app rollback`, or in plain GitOps a revert commit the controller reconciles). Target: complete in minutes, no rebuild.
- A release is not done until its rollback has been demonstrated. A deploy you cannot reverse is an outage with a delay.
- Database migrations gate rollback. Keep them backward-compatible (expand/contract) so the old version still runs against the new schema during and after the rollout; never couple a destructive `DROP` to the release that stops using the column. The schema sequencing lives in software_architect's `incremental_migration_and_delivery` and the pipeline checks in `infrastructure_and_deployment_pipelines`; honor both.

## Decouple deploy from release with feature flags

Deploy = the binary is in production. Release = users can reach the behavior. Separating them lets you ship dark, ramp independently of the rollout, and kill a feature without redeploying.

- Standardize on the **OpenFeature** (CNCF) API with a provider (flagd, LaunchDarkly, Unleash, Flipt) rather than scattering `if` flags, so flag reads are uniform and swappable.
- Wrap new behavior in a flag defaulting to off; deploy via canary to prove the binary is healthy, then ramp the flag as a second, independent axis. A flag flip is the fastest kill switch in the toolkit, far faster than re-rolling pods.
- A killable flag must have a safe default and no irreversible side effects behind it (no destructive migration triggered only when the flag is on).
- Flags are operational debt. Tag each with an owner and an expiry; remove flags within a sprint or two of full rollout. Persist the ramp plan and removal owner with `save_decision`/`save_memory` so a stale permanent flag does not become unowned config.

## Operational record and handoff

- Open a `save_session` at the start of a progressive rollout and record current weight, gate verdicts, and flag state as you ramp.
- On promote, abort, or rollback, write `save_decision` (what and why) and, if it leaves residual risk, `log_issue`; use `log_handoff` so the on-call after you knows whether traffic is on stable or canary and which flags are mid-ramp. Pull `get_latest_activity` before touching a release someone else started.

## Common pitfalls

- Rolling update with `maxUnavailable > 0` and no readiness probe: capacity drops and traffic hits not-yet-ready pods mid-roll.
- Canary analysis compared against a static or historical threshold instead of a concurrent baseline; diurnal load makes it both flap and miss real regressions.
- Bake time shorter than the metric window, so promotion happens before any datapoint reflects the canary. Promoting on noise.
- Gating only on HTTP 5xx while latency, saturation, or a business KPI quietly regress.
- Single-window burn-rate alerting: either too twitchy (aborts on a blip) or too slow (whole budget gone before it fires). Use multi-window multi-burn-rate.
- Rollback that requires a rebuild, or repoints to a `latest` tag that already moved, so the previous artifact is gone. Address by digest.
- A destructive migration shipped in the same release that stops using the column, making rollback impossible without data loss.
- Blue-green flip with no smoke test on green and no plan for in-flight requests/sessions at cutover.
- Feature flags with no owner or expiry accumulating into permanent, untested branching; or a kill switch that cannot actually be flipped because behavior had irreversible side effects.
- Running Argo Rollouts and Flagger (or two CD controllers) over the same workload, so two reconcilers fight over traffic weight.

## Definition of done

- [ ] Strategy is chosen deliberately: canary for request-path changes, blue-green when mixed versions are unsafe, rolling only for low-risk changes with `maxUnavailable: 0` and a readiness probe.
- [ ] Canary runs through a controller (Argo Rollouts or Flagger, not both) with explicit weight steps, bake times longer than the metric window, and traffic shaping via mesh, ingress, or Gateway API.
- [ ] Automated analysis gates each step against the SLO SLIs (success rate, latency p95/p99, saturation) compared to a concurrent stable baseline, with a hard maximum rollout duration.
- [ ] Abort/rollback is driven by multi-window multi-burn-rate error-budget gates (fast ~14.4x/1h, slow ~6x/6h) and fires automatically.
- [ ] Rollback is one rehearsed command, addresses artifacts by signed digest, and completes in minutes; it has been demonstrated, not assumed.
- [ ] Migrations are backward-compatible (expand/contract) so rollback is safe; no destructive change is coupled to the release that retires it.
- [ ] New behavior is behind an OpenFeature-backed flag defaulting off, ramped independently of the deploy, with a safe kill default, an owner, and an expiry.
- [ ] Rollout state, gate verdicts, abort reasons, and handoffs are persisted via `save_session`, `save_decision`, `log_issue`, and `log_handoff`.
- [ ] Tests/dry-runs cover a forced analysis failure aborting the rollout, a rollback completing within target, and a flag kill switch disabling behavior without redeploy, with external metric providers mocked.
