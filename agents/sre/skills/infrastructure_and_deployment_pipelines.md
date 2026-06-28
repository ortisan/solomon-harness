# Infrastructure and Deployment Pipelines

Everything is code, reviewed, versioned, reproducible, and promoted through gates; no console clicks reach production.

This skill owns infrastructure-as-code, GitOps, and the build-and-promote pipeline with its gates. The progressive-delivery mechanics that decide whether a rollout promotes (canary analysis, blue/green, automated rollback against SLOs) live in `release_engineering_and_progressive_delivery`; the supply-chain signing and IaC test pyramid are detailed in `mandatory_competencies_carried_into_sre_work`. This file connects them into one auditable path from commit to production.

## Infrastructure as code

Use Terraform/OpenTofu or Pulumi. Keep state remote with locking (S3 + DynamoDB, Terraform Cloud, or equivalent); never local state, which races and leaks secrets. Pin provider and module versions and commit the lockfile (`.terraform.lock.hcl`) so a plan is reproducible months later. Run scheduled drift detection (`terraform plan -detailed-exitcode`) and treat drift as an incident, because a manual console change you did not capture will be overwritten or will silently break the next apply. Build immutable golden images with Packer rather than mutating live hosts.

## GitOps

Make git the single source of truth for cluster state with Argo CD or Flux. The controller continuously reconciles the cluster to the declared state, so an out-of-band `kubectl edit` is reverted automatically. This makes rollback a `git revert` of the manifest change: the controller converges back to the previous state, and the audit trail is the git history.

## Pipeline stages and gates

Build the artifact **once** and promote the identical content digest through every environment (build once, deploy many); rebuilding per environment means staging and production are not the same bits. Each arrow below is a gate that stops promotion on failure:

```
commit
  -> [lint + unit tests]
  -> [build immutable image; reference by sha256 digest, never :latest]
  -> [SAST + dependency scan + secret scan]
  -> [policy gate: conftest / tfsec / checkov]
  -> [sign image (cosign) + generate SBOM (syft)]
  -> [integration tests on an ephemeral environment]
  -> [deploy to staging via GitOps]
  -> [smoke + automated checks]
  -> [promote: bump the pinned digest in the env repo]
  -> [progressive delivery -> see release_engineering_and_progressive_delivery]
```

Promotion is also gated on the error budget being healthy (see `reliability_targets_sli_slo_sla_error_budgets`): if the budget is exhausted, the pipeline blocks feature deploys until it recovers.

## Immutable artifacts

Reference images and modules by content digest (`app@sha256:...`), not mutable tags like `:latest`, so what you tested is exactly what you run. Tag additionally with the git SHA for traceability. The image, the SBOM, and the signature travel together through the registry.

## Policy as code

Encode guardrails as code so a reviewer is not the only thing standing between a bad config and production. Run OPA/Conftest (or Gatekeeper/Kyverno at admission) plus `tfsec`/`checkov` for cloud resources. Worked Conftest/Rego rule rejecting unpinned images:

```rego
package main

import rego.v1

deny contains msg if {
  input.kind == "Deployment"
  some c in input.spec.template.spec.containers
  endswith(c.image, ":latest")
  msg := sprintf("container %q uses :latest; pin a digest", [c.name])
}
```

Run it in CI: `conftest test k8s/*.yaml`. A failing policy fails the stage exactly like a failing unit test.

## Database migrations

Migrations must be backward-compatible across the rollout window. Use **expand/contract**: add the new column, dual-write, backfill, switch reads, and only in a later release drop the old column. The schema must work with both the old and new app versions at once, because during a rollout both run simultaneously. Never couple a destructive migration to the same release that stops using the column; that removes the rollback path.

## Secrets

Keep secrets in a manager (Vault, AWS/GCP Secrets Manager) and sync them with the External Secrets Operator, or store them encrypted in git with SOPS or sealed-secrets. Never plaintext in git history or in committed env files. Rotate on a schedule and prefer short-lived dynamic credentials over long-lived static ones (detailed in `mandatory_competencies_carried_into_sre_work`).

## Rollback

Rollback must be one command and complete within minutes, and you must have practiced it. With GitOps the practiced path is reverting the env-repo digest bump; the controller reconciles back. A deploy you cannot roll back is not done.

## Common pitfalls

- Local or unlocked Terraform state: concurrent applies corrupt state and secrets leak to disk. Reviewers reject any IaC without remote, locked state.
- Unpinned provider/module/image versions: a plan is not reproducible and `:latest` means staging and prod diverge. Pin everything and commit the lockfile.
- Rebuilding the artifact per environment: you ship bits you never tested. Build once, promote the same digest.
- A pipeline with no rollback path, or one never practiced: the first real failure is the first rollback attempt. Make rollback one command and rehearse it.
- Destructive migration shipped with the release that stops using the column: there is no safe rollback and a mid-rollout app sees a missing column. Use expand/contract across releases.
- Manual hotfixes applied in the console: they drift from IaC and vanish on the next apply. All change goes through the pipeline.
- Secrets in git or committed env files: a clone exposes them forever in history. Use a secret manager or encrypted-at-rest storage.
- Guardrails enforced only by human review: reviewers miss things and tire. Encode them as policy-as-code gates.

## Definition of done

- [ ] All infrastructure is IaC with remote, locked state, pinned versions, and a committed lockfile; drift detection runs on a schedule.
- [ ] Cluster state is reconciled from git via Argo CD or Flux, with git as the single source of truth.
- [ ] The pipeline builds an immutable artifact once, references it by digest, and promotes the same digest through every environment.
- [ ] Gates exist for lint/unit, SAST/dependency/secret scan, policy-as-code, signing + SBOM, integration tests, and smoke checks; a failing gate blocks promotion.
- [ ] Promotion is also gated on a healthy error budget.
- [ ] Database migrations are backward-compatible (expand/contract) and never couple a destructive step to the release that stops using the column.
- [ ] Secrets live in a manager or encrypted-at-rest store, never plaintext in git, and rotate on a schedule.
- [ ] Rollback is one command, completes in minutes, and has been practiced.
- [ ] Progressive-delivery promotion is delegated to `release_engineering_and_progressive_delivery`, not reimplemented here.
- [ ] All pipeline and IaC code is reviewed and version-controlled per Git Flow and Conventional Commits.
