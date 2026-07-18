---
name: ci-quality-gates
description: Defines the CI gate matrix per branch type (feature/*, release/*, nightly), required status checks, branch protection rulesets, and reusable GitHub Actions workflows that make a green merge the verification evidence. Use when configuring CI pipelines or deciding which checks are required versus advisory.
---

# CI Quality Gates

Encode the verification standard as automated gates the pipeline enforces, so no change reaches `develop` or `main` on a reviewer's good faith. A gate is a required status check whose failure blocks the merge; the gate matrix decides which checks are mandatory per branch type, branch protection makes them unbypassable, and the cost-versus-coverage tradeoff decides what runs on every push versus on a release candidate or a schedule. The goal is a pipeline where a green merge button is itself the verification evidence, not a thing a human still has to re-establish.

## The gate matrix per branch type

The project's Git Flow merges `feature/*` into `develop` and promotes `release/*` into `main`. Each junction gets a different gate set, sized by blast radius: a feature PR must be fast enough to run on every push, a release PR can afford the slow, exhaustive checks because it gates production.

| Gate | `feature/*` -> `develop` (PR) | `release/*` -> `main` (PR) | nightly on `develop` |
| --- | --- | --- | --- |
| lint + format | required, full | required | required |
| type-check (strict) | required, full | required | required |
| unit + coverage floor | required (80% / 90% core) | required | required |
| integration (Testcontainers) | required | required | required |
| critical-journey E2E | required (smoke set) | required (full matrix) | full cross-browser |
| mutation | incremental, changed lines | full on core modules | full on core, trend |
| flake rate < 2% | advisory, quarantine lane non-gating | required, blocks release at or above 2% | required, tracked as trend |
| dependency/SCA + secret scan | required, fast | required + license check | full audit |
| SAST (CodeQL/Semgrep) | diff-aware | full | full |
| contract `can-i-deploy` | required | required | - |
| UAT sign-off | - | required (manual gate) | - |

The rule behind the columns: anything O(minutes) sits on the feature PR; anything O(tens of minutes) (full mutation, full cross-browser E2E, deep SAST) moves to the release gate and the nightly job. `main` is reachable only through a `release/*` PR with every column green plus the manual UAT sign-off, never by direct push. See `mutation_testing` for why mutation is incremental on PRs and full on a schedule, and `integration_and_e2e_testing` for the integration/E2E split and `can-i-deploy` contract gating.

## GitHub Actions: reusable workflows and least privilege

Define the gate set once as a reusable workflow (`workflow_call`) and call it from the PR-triggered workflows, so `feature/*` and `release/*` share one definition and drift is impossible.

```yaml
# .github/workflows/gates.yml — the reusable gate definition
on:
  workflow_call:
    inputs:
      mutation_scope: { type: string, default: "incremental" }  # "incremental" | "full"

permissions:
  contents: read            # default the whole token to read-only; widen per-job only if needed

concurrency:
  group: gates-${{ github.ref }}
  cancel-in-progress: true  # supersede stale runs on force-push; saves runner minutes

jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full-40-char-sha>   # pin by commit SHA, never a moving tag
      - run: uv sync
      - run: uv run pytest --cov --cov-branch --cov-fail-under=80   # gate fails below the floor
```

```yaml
# .github/workflows/pr.yml — caller for feature PRs
on: { pull_request: { branches: [develop] } }
jobs:
  gates:
    uses: ./.github/workflows/gates.yml
    with: { mutation_scope: "incremental" }
  gate-summary:        # aggregation job, see below
    needs: [gates]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - run: '[ "${{ needs.gates.result }}" = "success" ]'
```

Non-negotiable workflow hygiene:

- Pin every third-party action by full commit SHA, not `@v4`. A tag is mutable and is a known supply-chain vector; Dependabot updates the SHA with a reviewable diff.
- Set `permissions: contents: read` at the top and grant the minimum extra scope per job (`id-token: write` for OIDC, `security-events: write` for CodeQL upload). The default token must never be write-all.
- Authenticate to cloud with OIDC short-lived tokens, not long-lived secrets in repo settings. Coordinate with the `security` agent on secret hygiene.
- Cache dependencies (`actions/cache`, `uv`/`pip`/`npm` lockfile keyed) to keep the feature gate fast; a slow gate gets disabled.

## Required status checks and branch protection

Gates only matter if they cannot be skipped. Configure protection with repository **rulesets** (the current replacement for legacy branch-protection rules; rulesets target multiple branch patterns and are themselves versioned config).

For `develop` and `main`:

- Require the exact gate check names as required status checks, and require the branch be up to date before merge (or use a **merge queue**, which rebases and re-runs gates in order so a green-when-opened PR cannot break the base via a semantic conflict).
- Require a pull request with at least one approval, code-owner review on protected paths, dismissal of stale approvals on new commits, and resolution of all conversations.
- Require linear history and signed commits; block force-pushes and branch deletion.
- Restrict who can push to `main` to the release process only; direct pushes are forbidden so promotion always passes the release gate.

The skipped-required-check trap: a required check that is skipped (by a `paths` filter or a conditional `if`) stays **pending forever** and blocks the merge, because GitHub cannot distinguish "skipped" from "not yet reported". Do not make path-filtered jobs directly required. Instead make one always-run aggregation job (`if: always()`, `needs:` every gate) required, and have it assert the combined result. That keeps path filters for runner-cost savings without deadlocking the merge.

## Per-gate thresholds and ownership

Each gate enforces a number that lives in config, not in a reviewer's head:

- Lint + format: `ruff check` / `ruff format --check` (Python), `eslint` or `biome` (JS/TS). Zero findings; formatting is a check, not a suggestion.
- Type-check: `mypy --strict` or `pyright`, `tsc --noEmit`. No new `# type: ignore` without a code and reason.
- Unit + coverage: `pytest --cov --cov-branch --cov-fail-under=80`, 90%+ on core/risk/money modules, per `coverage_a_floor_not_a_finish_line`. Branch coverage, not just line.
- Integration + E2E: required green per `integration_and_e2e_testing`; retries capped at one, any retry alerts.
- Mutation: break threshold anchored to the measured score and ratcheted up, per `mutation_testing`. Incremental on the PR, full on the release gate and nightly.
- Flake rate: **< 2% in the canonical suite**, tracked via `flaky_tests`' flip-rate and confirmed by `ai_test_hygiene_scan`'s isolation protocol before any failure is trusted as real or dismissed as noise. Advisory on `feature/*` (quarantined tests run but never gate); a hard `FAIL` on `release/*` at or above the threshold, regardless of the aggregate pass rate; tracked as a trend on the nightly job so a drifting suite is visible before it hits the release gate.
- Dependency/security: `pip-audit` / `osv-scanner` for known CVEs, a secret scanner (`gitleaks`/`trufflehog`) on the diff, `CodeQL` or `Semgrep` for SAST, and a license check on the release gate. Fail on any high/critical with no accepted-risk exception filed.

## Persisting gate decisions and handoffs

Gate configuration is a decision record, not folklore. Use the project memory so the matrix and its thresholds are auditable:

- `save_decision` when the matrix or a threshold changes (raising the mutation break floor, adding a SAST gate, moving a check from required to advisory) with the rationale; `get_decision` / `get_latest_activity` before editing a threshold so you do not silently undo a prior choice.
- `log_issue` when a nightly full run on `develop` regresses (new mutation survivor, new CVE, coverage drop), and `get_open_issues` to confirm the release branch is not promoting a known-failing gate.
- `log_handoff` when a `release/*` candidate passes every gate plus UAT sign-off, handing the SRE/deploy stage the green evidence; `save_session` to record the verification cycle that produced it.

## Common pitfalls

- Required checks defined but the branch protection ruleset not actually requiring them, so the gate is theater and a PR merges red.
- A path-filtered or conditional job marked required directly: it sits pending and deadlocks every PR. Use an always-run aggregation job instead.
- Actions pinned by mutable tag (`@v4`) rather than commit SHA, leaving a supply-chain hole in CI itself.
- `GITHUB_TOKEN` left write-all, or long-lived cloud secrets in repo settings instead of OIDC. The pipeline becomes the soft target.
- Running full mutation or the full cross-browser E2E matrix on every feature PR; the gate takes an hour, gets bypassed, and stops gating.
- "Up to date before merge" not enforced and no merge queue, so two independently green PRs combine into a broken `develop` (semantic merge conflict).
- Allowing direct pushes to `main`, so a hotfix skips the release gate entirely.
- A coverage or mutation threshold lowered to make a red build green, with no `save_decision` record; the floor silently erodes.
- Treating a manual UAT approval as optional on the `release/*` gate, shipping unverified acceptance criteria.

## Definition of done

- [ ] The gate matrix is implemented as reusable GitHub Actions workflows, with `feature/*` -> `develop` and `release/*` -> `main` callers sharing one gate definition.
- [ ] Branch-protection rulesets require the exact gate check names on `develop` and `main`, require up-to-date branches or a merge queue, code-owner review, linear history, signed commits, and block force-push and direct pushes to `main`.
- [ ] An always-run aggregation job is the required check so path filters cannot deadlock merges; no skip-able job is directly required.
- [ ] Lint, strict type-check, unit + coverage floor (80% / 90% core, branch coverage), and integration are required on every feature PR and run in O(minutes).
- [ ] Mutation runs incrementally on PRs and fully on the release gate and nightly, with the break threshold anchored and ratcheted, per `mutation_testing`.
- [ ] Flake rate stays below 2% in the canonical suite as a required, hard-`FAIL` release-gate check; below the threshold on `feature/*` it stays advisory (quarantine lane, non-gating), and it is tracked as a trend on nightly.
- [ ] Critical-journey E2E and `can-i-deploy` contract checks gate releases, per `integration_and_e2e_testing`; full cross-browser/E2E matrix runs on the release gate and on schedule.
- [ ] Dependency/SCA, secret scanning, and SAST gates fail on high/critical findings; the release gate adds a license check.
- [ ] Actions are pinned by commit SHA, the default `GITHUB_TOKEN` is read-only with per-job least privilege, and cloud auth uses OIDC, not stored secrets.
- [ ] `release/*` reaches `main` only with every gate green plus a manual UAT sign-off; the green merge is the verification evidence.
- [ ] Matrix and threshold changes are recorded with `save_decision`; nightly regressions open issues via `log_issue`; a passing release candidate is handed off with `log_handoff` and `save_session`.
