---
name: mandatory-competencies-carried-into-sre-work
description: Governs how TDD, security, and observability project competencies become concrete SRE artifacts, covering the IaC test pyramid, signed and SBOM'd supply-chain artifacts, structured trace-correlated logging, and secrets-manager hygiene. Use when writing infrastructure code or wiring a signing/SBOM pipeline step.
---

# Operationalizing the Mandatory Competencies in SRE Work

Turn the shared project competencies into concrete SRE practice rather than treating them as a checklist to recite.

The project rules (TDD, security, observability, supply-chain integrity, secret hygiene) are not paperwork an SRE signs off; they are techniques applied to infrastructure code, pipelines, runbook automation, and load harnesses. This skill shows how each becomes a working artifact. It complements `production_readiness_review` (the go/no-go gate) and `infrastructure_and_deployment_pipelines` (where these run in CI); the full instrumentation depth belongs to the `observability` agent.

## TDD for infrastructure: the IaC test pyramid

Infrastructure code is code, so it gets the Red-Green-Refactor cycle and a test pyramid, fast checks at the base, slow ones at the top:

| Layer | What it checks | Tools | Speed |
| --- | --- | --- | --- |
| Unit / static | syntax, lint, policy on the plan JSON | `terraform validate`, `tflint`, `tfsec`, `conftest` on `terraform show -json` | seconds |
| Contract | module inputs/outputs honor the interface | `terraform test` (1.6+) with mock providers, Terratest plan assertions | seconds-minutes |
| Integration | real apply in an ephemeral account, assert the live resource, destroy | Terratest apply/destroy, kitchen-terraform | minutes |

Write the failing assertion first. A worked `terraform test` contract check (`.tftest.hcl`) that a bucket module stays private:

```hcl
run "bucket_blocks_public_access" {
  command = plan
  assert {
    condition     = aws_s3_bucket_public_access_block.this.block_public_acls == true
    error_message = "S3 bucket must block public ACLs"
  }
}
```

The same discipline covers deployment scripts and alerting logic: a runbook automation or an alert rule ships with a test that proves it fires on the condition it claims to catch. Mock every external cloud API so the unit and contract layers run hermetically and offline.

## A signed-artifact supply chain

The pipeline must produce artifacts whose origin is provable, so a tampered or unknown image cannot reach production. Target SLSA Level 3 (non-falsifiable provenance from an isolated builder). Three concrete steps:

1. **SBOM:** generate a bill of materials and scan it.
   ```bash
   syft my-image@sha256:... -o spdx-json > sbom.spdx.json
   grype sbom:sbom.spdx.json --fail-on high
   ```
2. **Sign:** keyless signing with cosign (Fulcio for the short-lived cert, Rekor for the transparency log).
   ```bash
   cosign sign --yes my-registry/app@sha256:...
   ```
3. **Verify at admission:** reject anything unsigned or from an unexpected identity. Kyverno `verifyImages` or the Sigstore policy-controller enforces it in-cluster:
   ```bash
   cosign verify my-registry/app@sha256:... \
     --certificate-identity-regexp 'https://github.com/org/.*' \
     --certificate-oidc-issuer https://token.actions.githubusercontent.com
   ```

This is the concrete form of the STRIDE controls: signing addresses Tampering and Spoofing of artifacts, the Rekor log addresses Repudiation.

## Structured logs and W3C trace-context propagation

SLIs are only measurable if a request can be followed end to end. Emit structured JSON logs that carry the trace identifiers, and propagate the W3C `traceparent` header across every service hop so spans stitch into one trace. The header format is `traceparent: 00-<32-hex trace-id>-<16-hex span-id>-01`; an OpenTelemetry SDK injects and extracts it automatically. A log line that joins its trace:

```json
{"ts":"2026-06-28T14:02:11Z","level":"error","svc":"orders",
 "trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7",
 "op":"checkout","region":"us-east-1","msg":"db timeout after 2s"}
```

Tag metrics with service, region, and operation so the RED signals (rate, errors, duration) slice the way incidents need. The point is operational: when the fast-burn alert fires, you pivot from the alert to the trace to the log line in seconds instead of grepping unstructured text across services.

## Secrets in a manager, never in git

Static secrets in git are exposed forever in history even after deletion. Keep them in Vault or a cloud secrets manager and sync into the workload with the External Secrets Operator, or store them encrypted at rest with SOPS or sealed-secrets. Prefer short-lived dynamic credentials (Vault's database secrets engine issues a credential per session with a TTL) over long-lived static keys, so a leak expires on its own. Add a pre-commit guard (`gitleaks` or `trufflehog`) so a secret cannot be committed in the first place, and rotate on a schedule and immediately on any suspected exposure.

## Common pitfalls

- IaC merged with no test at any pyramid layer: a typo or a policy regression reaches production unchecked. Reviewers reject infrastructure changes without at least static + contract tests.
- Alerting or runbook automation shipped without a test that it triggers: the alert is discovered to be broken during the incident it was meant to catch. Test the firing condition.
- Images deployed without provenance: an unsigned or unknown artifact can be substituted and nothing detects it. Sign, generate an SBOM, and verify at admission.
- Verification configured but not enforced at admission: signing is theater if the cluster still admits unsigned images. Enforce with Kyverno or policy-controller.
- Logs without `trace_id`/`span_id`, or context not propagated across hops: incident triage degrades to cross-service grep and SLIs cannot be measured end to end. Emit structured logs and propagate `traceparent`.
- Long-lived static credentials in env vars or git: one leak is permanent and unrotated. Use a secrets manager with short-lived dynamic credentials and a pre-commit scanner.

## Definition of done

- [ ] Every IaC module has static and contract tests, with integration tests for the risky resources; tests run hermetically with mocked cloud APIs.
- [ ] Alerting rules and runbook automation ship with a test proving they fire on the intended condition.
- [ ] The pipeline generates and scans an SBOM, signs the artifact (cosign), and the cluster verifies signature and identity at admission.
- [ ] Application and infra logs are structured JSON carrying `trace_id` and `span_id`; W3C trace-context is propagated across every service hop.
- [ ] Metrics are tagged with service, region, and operation so RED signals can be sliced during incidents.
- [ ] Secrets live in a manager or encrypted-at-rest store with short-lived dynamic credentials where possible; a pre-commit scanner blocks secret commits and rotation is scheduled.
- [ ] All of the above is committed as reviewed code per Git Flow and Conventional Commits, and verified at the `production_readiness_review` gate.
