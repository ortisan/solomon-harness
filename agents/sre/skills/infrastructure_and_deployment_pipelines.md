## Infrastructure and deployment pipelines


Everything is code, reviewed, versioned, and reproducible. No console clicks in production.

- **IaC**: Terraform/OpenTofu or Pulumi. Remote state with locking, no local state. Run drift detection on a schedule. Plan output is reviewed in PRs; pin provider and module versions. Build immutable golden images with Packer rather than mutating live hosts.
- **GitOps**: ArgoCD or Flux with git as the single source of truth for cluster state. Reconciliation, not imperative apply.
- **CI/CD stages**: lint and unit tests, build, SAST and dependency scan, sign the artifact, generate an SBOM, integration tests, deploy to staging, automated checks, promote. Gate promotion on tests passing and on the error budget being healthy.
- **Deployment strategy**: prefer canary or blue/green over a naked rolling update. Run automated canary analysis (Argo Rollouts or Flagger) that compares the canary's error rate and latency against the baseline and rolls back automatically on regression. Decouple deploy from release using feature flags.
- **Rollback**: must be one command and complete within minutes. Practice it. A deploy you cannot roll back is not done.
- **Database migrations**: backward-compatible, expand/contract (add column, dual-write, backfill, switch reads, drop old) so the schema is compatible with both the old and new app versions during the rollout. Never couple a destructive migration to the same release that stops using the column.
- **Secrets**: Vault, SOPS, or sealed-secrets. Never in git, never in plain environment files committed to the repo. Rotate on a schedule.
- Pitfalls: snowflake servers, unpinned versions, a pipeline with no rollback path, migrations that assume a single atomic cutover, manual hotfixes that drift from IaC.
