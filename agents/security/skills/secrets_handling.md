---
name: secrets-handling
description: Standardizes where credentials live (OIDC federation, secret managers, environment variables), how gitleaks and trufflehog detect leaks before and after they land in git, rotation SLAs by credential class, and the revoke-first leak playbook. Use when configuring a new credential's storage, wiring secret scanning into pre-commit or CI, or responding to a leaked or suspected-leaked secret.
---

# Secrets Handling

The standard for where credentials live, how leaks are detected before and after they land in git, how fast keys rotate, and exactly what to do the moment one leaks. The stance: a secret that has touched a commit, a log line, or a chat window is compromised — containment starts with revocation, never with cleanup.

## Where secrets live

Order of preference:

1. No long-lived secret at all: OIDC federation (GitHub Actions `id-token: write` exchanging a workflow identity for short-lived cloud credentials) removes the stored key entirely. Prefer this wherever a cloud provider is involved.
2. A secret manager — HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager, or SOPS+age for small repos — which adds access audit logs, rotation hooks, and versioning.
3. Environment variables, acceptable at this project's scale but with known leak paths: `/proc/<pid>/environ`, crash reports, `env` dumps in CI logs, and inheritance by every subprocess. Never pass a secret on a command line (`ps` shows it to every local user).

This harness reads `SURREAL_URL` / `SURREAL_USER` / `SURREAL_PASS` from the environment with per-tenant config in `.agent/config.json` — keep it that way; a credential literal in Python source or a workflow file is a review-blocking finding. In GitHub Actions, secrets come from `secrets.*` or environment-scoped secrets, are masked in logs automatically, and must not be echoed, base64-wrapped (masking misses encodings), or written to artifacts.

`.env` hygiene: `.env` and any key files are gitignored; a committed `.env.example` carries variable names with placeholder values only; nothing in `docker-compose.yml` or test fixtures holds a real credential — tests mock the secret source per the house rule.

## Detection: pre-commit and CI

Two complementary scanners:

- `gitleaks` — fast regex-plus-entropy scanning, the right tool for the pre-commit hook (`gitleaks protect --staged`) and for CI on every push. In CI run it against full history (`fetch-depth: 0`), not just the diff, so a secret merged last month still surfaces.
- `trufflehog` — its verification mode calls the provider to check whether a candidate credential is live (`trufflehog git file://. --results=verified`), which turns "looks like a key" into "is an active key" and cuts triage time sharply.

Wire gitleaks into `.pre-commit-config.yaml` and as a CI job with the action pinned to a full commit SHA like every other action in this repo. Keep a reviewed `.gitleaks.toml` for repo-specific allowlists (test RSA fixtures, documented dummy values); every allowlist entry carries a comment saying why it is not a real secret. Turn on GitHub push protection and secret scanning for the repo — provider-partnered detection catches formats (AWS `AKIA*`, GitHub `ghp_*`/`github_pat_*`, Slack `xoxb-*`) at push time, before CI runs.

## Rotation SLAs

- Leaked or suspected-leaked: revoke immediately — target under 1 hour from detection, regardless of severity assessment. Assessment happens after revocation.
- High-privilege, long-lived credentials (deploy keys, admin tokens, DB root): rotate every 90 days.
- Standard service credentials and API keys: rotate every 180 days.
- Anything that cannot be rotated without an outage is an architecture bug: file it, because un-rotatable credentials are the ones that stay compromised for years.

Rotation that requires a human runbook decays; prefer credentials that expire on their own (OIDC-issued, short-TTL tokens) over calendar-driven rotation of static keys.

## Leak playbook: revoke first

The clock matters: public honeytoken studies consistently measure first abuse of AWS keys pushed to public GitHub within minutes. History cleanup does nothing for a credential already harvested.

1. Revoke or rotate the credential at the provider. Do this before any git surgery, before root-cause, before notifying anyone who cannot help revoke.
2. Assess blast radius: pull the provider's audit logs (CloudTrail, GitHub audit log, DB access log) for the full exposure window — from the commit timestamp, not the detection timestamp — and look for unfamiliar principals, IPs, and API calls.
3. Clean history with `git filter-repo` or BFG and force-push; then remember that GitHub keeps orphaned commits fetchable by SHA until support purges them, and forks and clones keep their own copies. Cleanup reduces future scraping; it is not containment.
4. Close the loop: file the incident with `log_issue`, record the root cause and the fix with `save_decision`, add a gitleaks rule or allowlist correction so the same pattern is caught at pre-commit next time, and verify the new credential is delivered via the manager or env path, not a hotfix literal.

## Common pitfalls

- Deleting the secret from the latest commit and calling it handled; the value remains in history, reflog, forks, and every CI log that printed it — rotation is the only fix.
- Passing secrets as command-line arguments or interpolating them into shell strings, exposing them via `ps` and shell history.
- Echoing configuration in CI for debugging; GitHub masks exact matches only, so `base64`, JSON-embedding, or partial prints bypass masking.
- Real credentials in test fixtures "because it's just the sandbox account" — sandbox keys pivot, and fixtures get copied.
- A gitleaks allowlist entry with no justification comment, which quietly becomes a hole shaped exactly like a real key.
- Storing the SurrealDB root password in `docker-compose.yml` committed to the repo instead of env substitution.
- Rotating the leaked key but not the credentials it could mint or access (session tokens it authorized, webhooks it configured).
- Treating private repos as safe storage; repo access lists grow, and private history leaks through forks, backups, and laptop theft.

## Definition of done

- [ ] No credential literals in source, workflows, compose files, or fixtures; secrets arrive via env, `secrets.*`, or a manager.
- [ ] `.env` gitignored; `.env.example` committed with placeholders only.
- [ ] gitleaks runs in pre-commit (staged) and CI (full history, SHA-pinned action); trufflehog verification available for triage.
- [ ] GitHub push protection and secret scanning enabled.
- [ ] Every scanner allowlist entry has a written justification.
- [ ] Rotation SLAs assigned per credential class; un-rotatable credentials filed as issues.
- [ ] Any leak handled revoke-first, with audit-log review over the full exposure window and the incident recorded via `log_issue`/`save_decision`.
- [ ] A regression control (scanner rule, hook, or test) exists for the leak pattern that occurred.
