---
name: opa-rego
description: Treats authorization as code built on Open Policy Agent evaluating Rego policies against input and data documents, keeping the decision and the enforcement separate and denying by default. Use when writing or reviewing an OPA/Rego authorization policy or deciding where a policy decision point sits in a service.
---

# OPA and Rego

Treat authorization as code. Open Policy Agent (OPA) evaluates Rego policies against an `input` and a `data` document and returns a decision; your service enforces it. Keep the decision and the enforcement separate, deny by default, and enforce at every endpoint, not just the UI.

## Version baseline and orientation

- OPA 1.0.0 shipped in December 2024. The current line is `1.x`. Rego v1 is the default and only dialect the parser accepts unless you opt out. Check with `opa version`.
- Rego v1 makes `if` mandatory before every rule body and `contains` mandatory for every multi-value (partial set) rule. `import rego.v1` is now a no-op kept for source compatibility; you do not need it on 1.x.
- Legacy v0 policies do not parse on 1.x. Run them with `opa run --v0-compatible` / `opa eval --v0-compatible`, or migrate once with `opa fmt --rego-v1 -w ./policy` and verify with `opa check --strict ./policy`.
- The Go module path changed. New code imports `github.com/open-policy-agent/opa/v1/rego` and `.../v1/sdk` (Rego v1 defaults). The old `.../opa/rego` path still exists for v0.x transitions but is not recommended for new work.
- OPA binaries are rebuilt on patched Go releases for CVE fixes. Pin a specific tag (`openpolicyagent/opa:1.x.y-static` or `-rootless`), never `latest`, in production images. The `-static` image has no shell, which shrinks the attack surface of a sidecar.
- Companion tools version independently: Conftest (`0.x`, pre-1.0, embeds an OPA engine and supports Rego v1), Gatekeeper (`3.x`, pins a specific OPA/Rego version per release), OPAL (`0.x`), Regal linter (`0.x`).

## Policy-as-code and decoupled decisions

The core contract: OPA answers a question, the application acts on the answer. Do not push enforcement branching into Rego and do not push policy logic into the service.

- Return a structured decision, not a bare boolean, when the caller needs reasons. A rich result lets the service log, surface, and act without re-deriving anything.
- The default decision path is `data.system.main`. Prefer an explicit named path per concern, for example `data.http.authz`, queried as `POST /v1/data/http/authz`.
- Undefined is not false. If a rule never fires, OPA returns `{}` (no `result` key), and a naive client reads that as "no decision". This is the most common OPA security bug. Always write `default allow := false` and have the client treat a missing/undefined result as deny.

Authorization policy, deny-by-default, RBAC plus an ABAC condition (Rego v1):

```rego
package http.authz

import data.roles      # slow-changing baseline, delivered via bundle/data
import data.tenants

default allow := false

# Allow only when an explicit grant matches and tenancy lines up.
allow if {
    some role in input.subject.roles
    some perm in data.roles[role].permissions
    perm.action == input.action
    perm.resource == input.resource
    input.subject.tenant == input.resource_tenant   # ABAC: same-tenant check
}

# Rich decision object for callers that need the reason.
decision := {
    "allow": allow,
    "reason": reason,
}

reason := "granted" if allow
reason := "denied_by_default" if not allow
```

Verifying a JWT inside the policy (the role's `iss`/`aud`/`exp`/signature requirement, expressed as code):

```rego
package http.authz

default allow := false

claims := payload if {
    [valid, _, payload] := io.jwt.decode_verify(input.token, {
        "cert": data.jwks,                 # JWKS delivered via bundle/data, rotated centrally
        "iss": "https://issuer.example.com/",
        "aud": "api://rates",
        "alg": "RS256",
    })
    valid
}

allow if {
    "rates:read" in claims.scope
}
```

`io.jwt.decode_verify` validates the signature and, when present in the token, `exp` and `nbf` against current time, plus `iss`/`aud` when you pass them as constraints. Pin `alg` to stop algorithm-confusion (`none`, or RS/HS swap) attacks. Never accept an unsigned token path.

## Deployment models: sidecar, library, host-level, Envoy

Pick based on latency budget and language.

- Sidecar / co-located daemon. Run `opa run -s` next to the app; the app calls `http://localhost:8181/v1/data/...` over loopback. Default for polyglot fleets. Keep the API on loopback or mTLS only.
- Library / embedded. Use the Go SDK to evaluate in-process with zero network hop. Pre-compile the query with `PrepareForEval` once at startup and reuse the prepared query per request; compiling per request is the dominant avoidable cost.

```go
import "github.com/open-policy-agent/opa/v1/rego"

pq, err := rego.New(
    rego.Query("data.http.authz.allow"),
    rego.Load([]string{"./policy"}, nil),
).PrepareForEval(ctx)            // do this once

rs, err := pq.Eval(ctx, rego.EvalInput(input))   // do this per request
allow := rs.Allowed()
```

- Sidecar with management. For non-Go services that still want bundles/decision-logs in-process, embed `sdk.OPA` (it carries the bundle, decision-log, and status plugins).
- OPA-Envoy external authorization. The `openpolicyagent/opa-envoy-plugin` image answers Envoy's gRPC `ext_authz` so you enforce at the mesh edge without touching app code. Input arrives under `input.attributes.request.http` (method, path, headers). Return `{"allowed": bool, "headers": {...}}` to inject headers downstream.

Sidecar query and the undefined trap, side by side:

```bash
curl -s localhost:8181/v1/data/http/authz \
  -H 'Content-Type: application/json' \
  -d '{"input":{"action":"read","resource":"rates",
       "subject":{"roles":["analyst"],"tenant":"acme"},"resource_tenant":"acme"}}'
# => {"result":{"allow":true,"reason":"granted"}}
# A wrong path (typo in /authz) returns {} — no error, no result. The client must fail closed.
```

## Input and data: what goes where

- `input` is request-scoped and supplied by the caller on every query: the subject, action, resource, request attributes. Keep it small.
- `data` is the baseline document: roles, permission tables, JWKS, tenant maps, allow-lists. It changes slowly relative to requests. Deliver it through bundles or push it with the Data API; do not stuff it into `input` on every call.
- Pushing large, slow-changing reference data in `input` per request is a latency and bandwidth mistake. Bundle it as `data` instead.

## Bundles: distribution, signing, delta, decision logs

OPA pulls a gzip tarball of policy plus data from an HTTP service on a poll interval and activates it atomically. This is how policy reaches a fleet without redeploying OPA.

`config.yaml` for a signed, polled bundle with decision logging and status:

```yaml
services:
  registry:
    url: https://bundles.example.com
    credentials:
      bearer:
        token: ${OPA_BUNDLE_TOKEN}

bundles:
  authz:
    service: registry
    resource: bundles/authz/bundle.tar.gz
    polling:
      min_delay_seconds: 30
      max_delay_seconds: 60          # OPA jitters within this window
    signing:
      keyid: prod_key                # require a valid signature before activation
      scope: write

keys:
  prod_key:
    algorithm: RS256
    key: ${OPA_BUNDLE_PUBKEY}         # public key; private key signs at build time

decision_logs:
  service: registry
  reporting:
    min_delay_seconds: 5
    max_delay_seconds: 10

status:
  service: registry                  # exposes bundle activation/health upstream
```

Bundle `.manifest` scopes what a bundle is allowed to own. `roots` is a write boundary: two bundles cannot both claim the same root, which prevents one source from silently overwriting another's policy.

```json
{
  "revision": "git:abc1234",
  "roots": ["http/authz", "roles"],
  "metadata": {"team": "identity"}
}
```

Operational notes and pitfalls:

- Sign bundles in production. Build with `opa build -b ./src --signing-key private.pem --signing-alg RS256`, ship the public key in `keys`, and require `keyid`. An unsigned bundle path is a policy-injection vector. Verify the manifest too with `--exclude-files-verify` discipline.
- Delta bundles patch `data` only (JSON-patch style), not policy, and cannot be signed. Use them for fast-moving data with HTTP long polling when 30-60s is too slow; do not use them as your only channel if you require signed delivery.
- Decision logs can leak secrets. Redact with a `mask` rule in `system.log` before logs leave the process:

```rego
package system.log

mask contains "/input/password"
mask contains "/input/token"
mask contains "/input/authorization"
```

- Gate readiness on bundle activation. Probe `GET /health?bundles=true` (and `?plugins=true`); a fresh OPA with no bundle loaded otherwise answers requests with deny-by-undefined and looks healthy.

## Testing policies with `opa test`

Tests are Rego files; rules prefixed `test_` that evaluate to true pass. This satisfies the project's mandatory-tests rule for policy code.

```rego
package http.authz_test

import data.http.authz

test_analyst_can_read if {
    authz.allow with input as {
        "action": "read", "resource": "rates",
        "subject": {"roles": ["analyst"], "tenant": "acme"},
        "resource_tenant": "acme",
    }
    with data.roles as {"analyst": {"permissions": [{"action": "read", "resource": "rates"}]}}
}

test_cross_tenant_denied if {
    not authz.allow with input as {
        "action": "read", "resource": "rates",
        "subject": {"roles": ["analyst"], "tenant": "acme"},
        "resource_tenant": "globex",
    }
    with data.roles as {"analyst": {"permissions": [{"action": "read", "resource": "rates"}]}}
}

test_deny_by_default if {
    not authz.allow with input as {"action": "delete", "resource": "rates",
        "subject": {"roles": ["guest"]}}
}
```

Run and gate in CI:

```bash
opa test ./policy -v                                  # verbose
opa test ./policy --coverage --threshold 80           # fail build if line coverage < 80%
opa test ./policy --bench                              # micro-benchmark each test
opa check --strict ./policy                            # catch unused vars/imports, unsafe refs
```

- `with input as ... with data... as ...` is mock injection; mock external data and (with function mocking) `http.send`, so tests stay isolated, matching the QA mocking rule.
- `--threshold` fails the run below the percentage. Wire it into CI as a hard gate.
- Always include an explicit deny-by-default test and a negative test per allow rule. A policy with only positive tests hides the undefined-equals-allow bug.
- Debug with `print(...)` inside rules (output shows in `opa eval`/`opa test`); it superseded `trace()`. Strip noisy prints before shipping.
- Lint with Regal: `regal lint --enable-all ./policy`. It enforces the Rego Style Guide, flags `rego.v1` migration gaps, and finds dead code. Run it alongside `opa check` in CI.

## OPAL for real-time data sync

OPA's native channels (bundle polling, Data API push) are pull-based or manual. OPAL (Open Policy Administration Layer, by Permit.io) adds an event-driven control plane so policy and data reach agents within seconds of a change.

- OPAL Server watches a Git repo (GitHub/GitLab/Bitbucket, webhook or polling) for policy and watches configured data sources for data. On a change it publishes to a topic over a WebSocket pub/sub.
- OPAL Client runs at the edge next to OPA, subscribes to topics, fetches the actual policy/data, and writes it into OPA. The control plane carries instructions on where to fetch; the data plane fetches directly, which keeps secrets and large payloads off the bus.

Minimal wiring (env on each side):

```yaml
# OPAL server
OPAL_POLICY_REPO_URL: https://github.com/acme/authz-policy.git
OPAL_POLICY_REPO_POLLING_INTERVAL: "30"
OPAL_DATA_CONFIG_SOURCES: >
  {"config":{"entries":[
    {"url":"https://api.internal/users","topics":["users"],"dst_path":"/users"}]}}

# OPAL client (co-located with OPA)
OPAL_SERVER_URL: http://opal-server:7002
OPAL_POLICY_STORE_URL: http://localhost:8181     # the OPA to feed
OPAL_INLINE_OPA_ENABLED: "true"                  # let the client run OPA for you
```

Trigger an incremental data update without a redeploy by posting a `DataUpdate` to the server; only clients subscribed to the topic fetch and patch:

```bash
curl -X POST http://opal-server:7002/data/config \
  -H 'Content-Type: application/json' \
  -d '{"entries":[{"url":"https://api.internal/users/42","topics":["users"],
       "dst_path":"/users/42"}]}'
```

For multi-replica servers, back the pub/sub broadcaster with Postgres, Redis, or Kafka (`OPAL_BROADCAST_URI`); a single in-memory server does not fan out across replicas. On client restart OPAL re-syncs from source, so a restarted OPA is not left stale.

## Conftest: policy-test your config and IaC in CI

Conftest runs Rego against structured config (YAML/JSON/HCL/Dockerfile/INI) and is the right tool for shifting policy left in the pipeline. It looks for `deny`, `violation`, and `warn` rules; `deny`/`violation` fail the run.

```rego
package main

deny contains msg if {
    input.kind == "Deployment"
    not input.spec.template.spec.securityContext.runAsNonRoot
    msg := sprintf("Deployment %s must set runAsNonRoot", [input.metadata.name])
}

deny contains msg if {
    input.kind == "Deployment"
    some c in input.spec.template.spec.containers
    endswith(c.image, ":latest")
    msg := sprintf("container %s pins :latest", [c.name])
}
```

```bash
conftest test k8s/deployment.yaml -p policy/
conftest test --all-namespaces -p policy/ k8s/      # evaluate every package, not just main
conftest verify -p policy/                          # run policy/*_test.rego unit tests
```

- Unit-test Conftest policies the same way: `*_test.rego` with `test_` rules, executed by `conftest verify`. Hold the policies to the same coverage bar as application code.
- Distribute shared policy as OCI artifacts: `conftest push` to a registry, `conftest pull` in consuming pipelines. Version the policy bundle like any dependency.
- Conftest is pre-deploy (CI gate on manifests, Terraform plans, Dockerfiles). It does not enforce at runtime; pair it with Gatekeeper or an OPA sidecar for runtime defense in depth.

## Gatekeeper: OPA admission control for Kubernetes

Gatekeeper is the Kubernetes-native OPA: a validating (and mutating) admission webhook plus an audit controller. You define a `ConstraintTemplate` (the Rego and a parameter schema, which generates a CRD) and one or more `Constraint` CRs (the parameters and match scope).

ConstraintTemplate using Rego v1 (recent Gatekeeper releases; v1 syntax is opt-in via `version: "v1"`, default is still v0):

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8srequiredlabels
spec:
  crd:
    spec:
      names:
        kind: K8sRequiredLabels
      validation:
        openAPIV3Schema:           # v1 requires a structural schema
          type: object
          properties:
            labels:
              type: array
              items: {type: string}
  targets:
    - target: admission.k8s.gatekeeper.sh
      code:
        - engine: Rego
          source:
            version: "v1"          # opt in to Rego v1; no `import rego.v1` needed
            rego: |
              package k8srequiredlabels

              violation contains {"msg": msg} if {
                  some required in input.parameters.labels
                  not input.review.object.metadata.labels[required]
                  msg := sprintf("missing required label: %v", [required])
              }
```

Constraint, rolled out safely:

```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequiredLabels
metadata:
  name: must-have-owner
spec:
  enforcementAction: dryrun        # dryrun -> warn -> deny as you gain confidence
  match:
    kinds:
      - apiGroups: ["apps"]
        kinds: ["Deployment"]
  parameters:
    labels: ["owner"]
```

- Roll out with `enforcementAction: dryrun` (audit-only, violations reported on `status`), then `warn`, then `deny`. Flipping straight to `deny` cluster-wide can wedge legitimate deployments.
- Test templates offline with the `gator` CLI: `gator test` and `gator verify` run your ConstraintTemplates against fixture manifests in CI, before anything reaches the cluster. This is the unit-test layer for admission policy.
- Validating Admission Policy (CEL) integration: Gatekeeper can generate Kubernetes-native VAP from constraints. CEL validation is stable as of 3.18; VAP management is beta as of 3.20. It moves enforcement into the API server (in-process, fail-closed, lower latency) and reduces dependence on the webhook being reachable.
- Referential constraints (rules that look at other objects, for example "no duplicate Ingress host") need replicated data via the `Config` resource `syncOnly`. They are evaluated against a cache, so they are eventually consistent: a true time-of-check/time-of-use gap exists. The audit controller is the backstop for what slips through admission.
- Match scoping is load-bearing. An empty/over-broad `match` block silently applies a constraint to objects you did not intend, or never matches at all. Verify with `gator test`.

## Securing OPA itself

A default `opa run -s` exposes an unauthenticated REST API that can read decisions and, critically, accept policy and data writes. Lock it down.

```bash
opa run -s \
  --authentication=token \
  --authorization=basic \
  --tls-cert-file opa.crt --tls-private-key-file opa.key \
  --addr 0.0.0.0:8181 \
  config.yaml policy/
```

`--authorization=basic` makes OPA consult a `system.authz` policy for every API request; write it deny-by-default and grant only the paths a caller needs:

```rego
package system.authz

default allow := false

# Health is open.
allow if input.path == ["health"]

# Sidecar app may only query the authz decision.
allow if {
    input.path == ["v1", "data", "http", "authz"]
    input.identity == data.tokens.app_token
}
```

- Bind the API to loopback for a true sidecar, or require mTLS. Never expose `8181` on `0.0.0.0` without auth.
- Disable the Data and Policy write APIs unless something legitimately pushes through them; bundles are the safer delivery path.

## Performance and determinism pitfalls

- Compile once. With the SDK, `PrepareForEval` at startup; over HTTP, the bundle is compiled on activation, not per request. Per-request compilation is the usual cause of slow OPA.
- Rule indexing matters. Equality on `input` fields lets OPA index and skip non-matching rules. Catch-all comparisons and arithmetic in rule heads defeat indexing and turn O(1) lookups into O(n) scans over `data`.
- Use partial evaluation (`opa eval --partial`) to specialize a general policy against known inputs and flatten non-linear policies; benchmark with `opa bench` before and after.
- Keep policy deterministic for auditability. `time.now_ns()`, `rand`, and `http.send` inside a decision make it non-reproducible and break decision-log replay. When you need the current time, pass it in `input` so the same input always yields the same decision.
- Right-size `input`. Sending megabytes of context per request dwarfs evaluation time; move stable data into `data` via bundles.

## Common pitfalls

- Undefined treated as allow. No `default allow := false`, or the client reads a missing `result` as permissive. Fail closed everywhere.
- Querying the wrong decision path returns `{}` with HTTP 200, not an error. A typo silently disables enforcement. Test the exact path in CI.
- Unsigned bundles, or signing configured but not required. Either lets an attacker who reaches the bundle endpoint inject policy. Require `keyid`.
- Decision logs shipping PII or tokens because no `mask` rule exists.
- OPA management API exposed without `--authentication`/`--authorization`, allowing remote policy overwrite.
- Rego v1 migration missed: a policy using `in`/`if`/`contains` as plain identifiers fails to parse on 1.x. Run `opa fmt --rego-v1` and `opa check --strict`.
- Gatekeeper constraint pushed straight to `deny` with a broad or empty `match`, blocking valid workloads; or a referential constraint trusted as strongly consistent.
- Delta bundles assumed to carry policy or to be signable; they are data-only and unsigned.

## Definition of done

- [ ] Every policy is deny-by-default (`default allow := false`); the client fails closed on undefined/missing results.
- [ ] Policies are Rego v1 (`if`/`contains` mandatory), pass `opa check --strict` and `regal lint`, and `opa fmt` is clean.
- [ ] `opa test --coverage --threshold` gates CI; each allow rule has a positive and a negative test, plus an explicit deny-by-default test; external data and `http.send` are mocked.
- [ ] JWT verification pins `alg` and checks `iss`/`aud`/`exp`/signature; JWKS is delivered as `data`, not hardcoded.
- [ ] Deployment model chosen deliberately (sidecar on loopback/mTLS, embedded with `PrepareForEval`, or OPA-Envoy); the OPA management API requires auth.
- [ ] Bundles are signed, scoped by `.manifest` roots, and polled; readiness probes `?bundles=true`; decision logs are masked.
- [ ] Real-time sync (OPAL) backed by a durable broadcaster when the server is replicated; clients re-sync on restart.
- [ ] Conftest gates manifests/IaC in CI with its own `*_test.rego`; shared policy distributed as a versioned OCI bundle.
- [ ] Gatekeeper templates tested with `gator`, rolled out dryrun -> warn -> deny, with scoped `match`; VAP/CEL used where API-server enforcement is preferable.
- [ ] Decisions are reproducible (no nondeterministic builtins in the decision path); the policy version/revision is recorded.
- [ ] Auth design decision persisted to project memory; security-sensitive policy changes handed off for review.
