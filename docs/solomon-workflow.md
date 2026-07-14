# solomon workflow conventions

Shared conventions for the `/solomon-*` workflows. Every workflow command
reads this file and follows it so the lifecycle is consistent, auditable, and
backed by the project memory. The host tool (Claude Code or Antigravity CLI) provides
the model; these workflows orchestrate the specialist agents, the GitHub project,
and the memory layer.

## Lifecycle and board

Work flows through a GitHub Project (v2) board with these Status columns:

`Ideas` → `Backlog` → `Ready` → `In Progress` → `Code Review` → `QA` → `Done`

| Stage | Workflow | Driving agents | Board move |
| --- | --- | --- | --- |
| Orchestrate (scan + next) | `/solomon-workflow` | scrum_master | runs a task end-to-end or continues |
| Capture an idea | `/solomon-idea` | product_owner | → `Ideas` |
| Create a feature/story | `/solomon-issue` | product_owner | → `Backlog` |
| Create a bug | `/solomon-bug` | qa, software_engineer | → `Backlog` |
| Refine for readiness | `/solomon-refine` | product_owner, scrum_master | `Backlog` → `Ready` |
| Implement | `/solomon-start` | scrum_master, software_engineer, software_architect | `Ready` → `In Progress` → `Code Review` |
| Review | `/solomon-review` (auto-runs at the end of start) | software_architect (code), then qa, security, plus up to two diff-selected domain lenses | `Code Review` → `QA`, then on approval and interactive confirmation, merges the PR and moves `QA` → `Done` (ADR-0020) |
| Deliver and release | `/solomon-release` | sre, software_engineer | milestone-level: cuts the version tag once a milestone's issues are already `Done`; never merges an individual PR |

The board and helpers live in `solomon_harness/github.py`. Create the board once
with `ensure_project_board`; move cards with `set_issue_status`.

### Board columns mapped to lifecycle stages

The board columns above are the operational surface a card moves across; the named
delivery lifecycle is `Backlog -> Refinement -> Implementation -> Tests -> Review ->
Release -> Milestone`. They are not one-to-one — a column is where a card sits, a
stage is what the work is doing — so this table reconciles them:

| Board column | Lifecycle stage(s) |
| --- | --- |
| `Ideas` | Discovery (pre-Backlog); an idea graduates to a Definition of Ready and a Definition of Done at Refinement |
| `Backlog` | Backlog (captured, not yet refined) |
| `Ready` | Refinement complete (Definition of Ready met) |
| `In Progress` | Implementation and Tests (the TDD Red/Green/Refactor loop writes the covering tests here) |
| `Code Review` | Review (the software_architect code-review gate) |
| `QA` | Tests and Review verification (the qa and security gates; acceptance criteria and the Definition of Done are checked) |
| `Done` | Entered via Review's own merge (ADR-0020); Release and Milestone is what happens once enough `Done` cards close a milestone (the tag is cut when the milestone reaches 0 open issues with CI green) |

## The loop and session resumption

`/solomon-workflow` is the orchestrator. It scans the project memory and the board to
find where work stopped, then proposes the single best next step — one of the
workflows above — and runs it on confirmation. It advances one stage per
invocation: when work is in flight it proposes development, review, or release;
when nothing is in progress it proposes creating a feature, bug, or refinement.

The loop is host-orchestrated and human-gated, not fully autonomous: no code
decides the next stage — the host tool (Claude Code or the Antigravity CLI) runs these
markdown prompts — and the merge, release, and move-to-Done gates always require a
human.

At the start of every Claude Code or Antigravity CLI session, the harness surfaces the
project status (latest activity and open issues) through a SessionStart hook that
runs `solomon-harness run`. This hook automatically checks memory for pending tasks
(or prints open issues if none) and outputs the options card. The agent reads this
on start and immediately prompts the user with the enumerated choices.

## Interaction style

When a workflow needs a decision or confirmation from the user — which next step,
which option, which target — present the choices as an enumerated list (1, 2, 3, …),
with the final option always being "Other", where the user types a free-form answer.
In Claude Code this is the AskUserQuestion tool; in the Antigravity CLI, present a numbered
list and invite a free-text reply. Lead with the recommended option first and keep the
options mutually exclusive. This is mandatory, not a preference (the non-negotiable
Enumerable decisions rule in `agents/AGENTS.md`): never end a turn with an open prose
question, and never hand the user a command to copy ("run `/solomon-start 55` when you
want") in place of a clickable option — the closing "what next" block of every turn that
offers a choice MUST be the enumerated menu. Discrete numbered choices keep the user's
context focused and prevent dispersion.

This applies to the **closing "next step" recommendation of every turn**, not only the
big branching choices. Never end a report with prose the user must copy (for example
"run `/solomon-start 5` or `/solomon-workflow`"): present the candidate next actions as the
enumerated menu itself — in Claude Code an AskUserQuestion the user clicks — so advancing
the lifecycle costs one selection, not a copy-paste. The same holds for every small
"proceed / retry / push-or-PR" confirmation. A turn that ends by offering what to do next
without an enumerated, selectable menu is a defect.

### Elicitation gate (`/solomon-issue`)

Before shaping a feature/story, `/solomon-issue` evaluates the user's demand
against six readiness criteria — the explicit doubt-detection checklist. A
demand is ready when all six hold:

1. **Problem** — the pain or trigger is stated (why this matters now).
2. **Persona** — who is affected is identifiable (a real user type, never
   "the user").
3. **Outcome** — the observable change that means success is stated.
4. **Boundary** — at least one scope limit or constraint is stated.
5. **Single reading** — the text does not support two conflicting
   interpretations of comparable plausibility.
6. **Job behind the solution** — if the demand names a solution, the
   underlying need is also stated (a request is an untested solution to an
   unstated job).

When every criterion holds, shaping starts immediately and the issue body
carries the line `Elicitation: skipped — all 6 readiness criteria met`. When
any criterion fails, the command enters Socratic mode: questions follow the
enumerated-options convention above, at most 4 questions per round and one per
failed criterion — only for failed criteria, never re-asking one already
satisfied — for at most 3 rounds before shaping proceeds. An empty demand
starts from the job-to-be-done question. If the user declines to answer,
elicitation stops immediately and each unanswered criterion is recorded under
an `Assumptions (unelicited)` heading in the issue body. Non-interactive runs
never block: they ask nothing, print `Elicitation: skipped (non-interactive)`,
and record assumptions the same way. The gate changes only how the demand is
understood before shaping; the confirm-before-create step is untouched. The
question ladder lives in the product_owner `socratic_elicitation` skill.

### Capability check (`/solomon-refine`, `/solomon-start`)

Before refining or starting an issue, the workflow verifies the project has
the capability (agent + skills) the issue needs. The division of labor is
ADR-0008's: the host LLM supplies the match judgment as data, and the
deterministic router core (`capability_router.route`) owns the verdict —
matcher-contract validation, alternatives, the suggested action, and
fail-closed behavior on an empty catalog. The prompts never build inline
Python over issue text: they write a JSON file with the Write tool and run
`solomon-harness broker route --file <path>`; on a gap verdict they present
the enumerated choice (acquire via the broker, recommended; proceed without
acquiring; Other). Acquisition runs only through
`solomon-harness broker apply --file <path>`, which validates every field
(snake_case names, a numeric issue, single-line bounded free text) and is
permanently human-gated: a headless stage subprocess, an automation autonomy
level, or an engaged kill-switch is refused (exit 3) before any change — the
loop surfaces gaps, a human applies them.

### Spec generation (`/solomon-issue`)

Every feature/story issue gets a durable spec document: after creation,
`/solomon-issue` copies `docs/specs/0000-spec-template.md` to
`docs/specs/<N>-<slug>.md` via the Write tool and pre-fills the nine mandated
sections (Context, Problem, Requirements, Implementation Pointers, Acceptance
Criteria, Verification, Design Constraints, Out of Scope, Traceability) from
the shaped issue body, with the explicit placeholder `TBD (refine)` wherever
content is unknown at creation. The spec is the artifact the implementing model
reads, so it must be **implementation-ready** before work starts (maintainer
directive 2026-07-14): `Implementation Pointers` gives the exact `file:line`
targets, the current versus expected behavior, and the concrete approach;
`Verification` gives the exact command(s) that prove the change works. A model
should be able to implement from the spec without asking anything.

`/solomon-refine` resolves every placeholder and flips the spec to
`Status: ready`. `scripts/spec-lint.py` enforces the convention (filename rule,
sections present and non-empty, Traceability citing the issue) and, once a spec
is `Status: ready` or `implemented`, asserts that no section still holds a
`TBD (refine)` line — the mechanical gate that a refined issue is implementable
without guessing. It runs in the CI validators job. The spec ships with the
issue's first implementation PR — never pushed to a protected branch directly.
The convention's full definition lives in `docs/specs/README.md`; its decision
record is ADR-0028, shipped with the migration of the decision tree to
`docs/adrs` (#221 S2a). The implementation-ready bar — the two sections plus the
Ready-status placeholder gate — amends that convention in ADR-0032.

## Implementation mode (automatic or manual)

`/solomon-start` asks, before any code is written, whether the change is implemented
**automatically** by the agent or **manually** by a developer — the team still has
hands-on developers who want to write the code themselves. The choice uses the
enumerated-options style above (Automatic, recommended and first; Manual; Other).

- Automatic: the agent runs the TDD loop (Red/Green/Refactor) per PLAN.md, then opens the
  draft PR and moves the card to Code Review, then continues directly into
  `/solomon-review` for the new PR — the review runs automatically as part of the
  workflow; only the merge stays a human gate.
- Manual: the agent writes no production or test code and opens no PR. It hands back the
  prepared worktree, branch, PLAN.md, and the ADR decision, and leaves the card in
  `In Progress`. The developer implements by hand, then re-runs `/solomon-start` to open the
  PR (or opens it and runs `/solomon-review`).
- Headless (`solomon-harness dev start`): with no one to answer, the stage does not block on
  the prompt — it defaults to Automatic and prints
  `Implementation mode: Automatic (non-interactive default)`, so CI never hangs on stdin.

## Discovered-problem protocol (`/solomon-start`, `/solomon-loop`)

Implementing one issue routinely surfaces a *different* problem — an unrelated
defect, a better approach, a missing test, a refactor worth doing. The rule is
fixed (maintainer directive 2026-07-14):

- **File it as a new issue; do not comment it onto the in-flight issue.** A
  discovery becomes a fresh issue — `/solomon-bug` for a defect, `/solomon-issue`
  for a feature or improvement, a `type:chore` for cleanup — whose body links
  the parent with a `Refs #<parent>` line. Appending it as a comment on the
  issue being worked pollutes that thread and loses tracking. *(Exception: if
  the discovery exposes a security vulnerability, it must never be filed as a
  public issue; route it privately through a private GitHub Security Advisory
  or direct maintainer alert instead.)* (The single status comment `/solomon-start`
  posts — the branch back-link — is not a discovery and stays.)
- **Do not silently widen the current change.** The diff stays inside the
  PLAN.md target-files fence. A discovery outside that fence is out of scope for
  the current PR; it goes to its own issue and its own branch.
- **If the discovery blocks the current issue,** stop and surface it to the
  human as an enumerated choice (file-and-continue, file-and-switch, or Other) —
  never decide unilaterally to abandon or rescope in-flight work. A headless run
  files the `Refs #<parent>` issue, records the block in its run report, and
  stops the current issue rather than expanding it.
- **Rate-limit automated issue creation.** To prevent API denial of service or
  infinite loops under autonomous run sessions (`/solomon-loop`), a runner is
  strictly capped to creating at most 3 automated issues per run session. If
  this threshold is reached, issue creation halts and the session reports a
  budget limit block.

This keeps each issue's record clean and every discovered unit of work
independently trackable, refinable, and claimable. The protocol is recorded
with the implementation-ready bar in ADR-0032.

## Review staffing

The Review stage always runs three mandatory gates — qa, security, and
software_architect. In addition, `python -m solomon_harness.review_roster`
selects up to two domain lenses deterministically from the PR's changed paths
(`gh pr diff <n> --name-only` piped in): auth_engineer for credential-named
files, dba for `database_client`/`.surql`/migrations, sre for CI workflows and
deploy files, loop_engineer for `loop_*` files and `solomon_harness/workflows.py`, frontend
for `ui/`, observability for instrumentation, practice_curator for agent skill
and persona content, and documenter for Markdown under `docs/` (recursively).
ux_designer joins the ui rules once its agent definition lands. The cap keeps
reviews bounded; the mapping lives in `solomon_harness/review_roster.py` with
covering tests, so the selection is auditable and deterministic.

## The merge-to-Done transition

`/solomon-review` owns the merge (ADR-0020): on an approve verdict, in an
**interactive** session, the reviewer is asked — via the enumerated-decision
convention — whether to merge now. On yes, `uv run python -m
solomon_harness.github merge --pr <n> --issue <issue>` squash-merges the PR
and, in the same call, moves the board card to `Done` and writes the terminal
status through to memory (the ADR-0006 write-through), so no separate
`reconcile` is needed for the common case. A **headless** review run
(`solomon-harness dev review`) never merges — there is no one to answer the
confirmation, and the non-negotiable human-approval gate for merge holds by
never reaching that code path, not by an autonomy-level check (`#183` is a
separate, unresolved gap this does not depend on). `/solomon-release` never
merges an individual PR; it remains purely milestone-gated, cutting a version
tag once a milestone's issues are already `Done`, with a board-hygiene
backstop for any card GitHub auto-closed outside the CLI `Done` path.

## Deliver and release

`/solomon-release` (sre, software_engineer) does not move an individual card to
`Done` — that already happened when `/solomon-review` merged the PR (ADR-0020).
Its own role is milestone-level: once a milestone's issues are already `Done`,
it drives the version tag through CI, plus a board-hygiene backstop for any
card GitHub auto-closed outside the CLI `Done` path. The full, canonical
standard is `docs/release-policy.md` (decision recorded in
`docs/adrs/0004-milestone-gated-releases.md`); this section is the operational
summary the workflow follows.

**Release criterion — milestone-gated, never per-PR.** A tag is cut only when a
GitHub milestone reaches 0 open issues with CI green on `main`. Merging a single PR
closes its issue and burns down its milestone; it never cuts a release. Every issue
rolls up to exactly one milestone:

- An **epic** milestone is titled with its SemVer minor (`v0.4.0`, `v0.5.0`) — the
  title *is* the version; closing it (`open_issues == 0`, CI green) cuts the MINOR.
- A **theme / hardening** milestone is titled by theme (`memory-durability`,
  `test-ci-hardening`, `worktree-lifecycle`); closing it cuts a PATCH whose version
  is computed at cut time. `/solomon-refine` creates the milestone and assigns every
  Ready child; a parentless bug or chore goes to the nearest theme milestone.

An on-demand escape valve, `solomon-harness release prep`, may cut a PATCH for an
accumulated batch without waiting for a milestone to fully close.

**Version — computed, never hand-picked.** The bump is derived from the
Conventional Commits in `git log <last-tag>..main --first-parent` (highest wins).
Pre-1.0 (current `0.x`): a window with any `feat` or a `BREAKING CHANGE` bumps the
MINOR; otherwise `fix`/`perf`/`refactor`/`revert` bumps the PATCH; a window of only
`chore`/`docs`/`ci`/`test`/`style`/`build` is non-releasable (no tag). Post-1.0:
`BREAKING CHANGE` → MAJOR, `feat` → MINOR, `fix`/`perf` → PATCH. A published tag is
immutable — never moved; a bad release is superseded by the next PATCH (a revert PR
that ships forward), never by re-tagging.

**Branch model — trunk-only.** Slices squash-merge into `main`; there is no
`develop` branch and no long-lived `release/*` or `hotfix/*` branch. The only
release branch is the ephemeral `chore/release-vX.Y.Z` prep branch, which lives
minutes: `solomon-harness release prep` opens a PR carrying the `pyproject` version
bump and the new `CHANGELOG.md` section, commits `chore(release): vX.Y.Z`, then
stops. The human merges that PR — that merge **is** the release gate — and the
branch is deleted.

**Tag and publish — CI is the single owner.** On the prep-PR merge, the `main` push
carries the `chore(release): vX.Y.Z` commit; the release workflow creates and pushes
the annotated tag and publishes (`draft: false`) the GitHub Release with the
CHANGELOG section as its notes. There is no manual `gh release create`. CI pushes
only the tag (tags are not branch-protected) using the default `GITHUB_TOKEN` with
`contents: write` — no PAT, and CI never pushes a commit to protected `main`.

**Fail-closed gate.** `solomon-harness release check` asserts that the tag, the
`pyproject` version, and the top `CHANGELOG.md` heading (Keep a Changelog, dated
today) all agree, that the tag does not already exist, and that tests and `ruff` are
green; it exits non-zero on any mismatch, and CI enforces it on every
`chore/release-*` PR. Humans never hand-edit `pyproject.version` or add a CHANGELOG
heading — `release prep` writes them, and a CI check rejects any non-release PR that
touches them, which structurally prevents three-way version drift.

**Library readiness gate.** Because the harness is distributed as an immutable git
tag and GitHub Release of the source tree — not a running service and not published
to PyPI — the SLO-burn / canary / blue-green / on-call production-readiness review
does not apply. The release gate is a library readiness check: tests and `ruff`
green on `main`, `python -c "import solomon_harness"` succeeds, the
`solomon-harness` console script runs, and `release check` passes. The one kernel
carried over from progressive delivery is reversibility: immutable, never-moved
tags; rollback as a revert PR that auto-ships the next patch; and
backward-compatible expand/contract migrations for the SurrealDB / SQLite memory
store.

The CLI surface for this stage is `solomon-harness release plan | prep | check | audit-trigger`:
- `plan` — read-only and headless-safe (the loop may *propose* a release with it);
- `prep` — opens the prep PR and stops, never merging;
- `check` — the read-only fail-closed gate.
- `audit-trigger` — autonomous audit trigger, read-only and degrade-safe. It runs `practice_curator`'s Slice 1 audit on the delivered release artifact to automate continuous benchmarking. Any failure exits 0 and logs "audit skipped: sourcing unavailable".

## GitHub conventions

- Issues are created with `gh issue create`. Labels: `type:feature`, `type:bug`,
  `type:idea`, `type:chore`; plus `priority:p0|p1|p2` and `area:<domain>`.
- Branches (trunk-based): `feature/<slug>` for features, `bugfix/<slug>` for defects,
  both cut from `main` and squash-merged back to `main`. There is no `develop` and no
  long-lived `release/*` or `hotfix/*`; a production-critical fix is a `bugfix/<slug>`
  off `main` that ships in the next patch. The only release branch is the ephemeral
  `chore/release-vX.Y.Z` prep branch. The branch name carries NO issue number (kept
  deliberately clean); `<slug>` is the kebab-cased issue title. The issue is linked
  instead by the back-link comment and the `Refs #`/`Closes #` trailers.
- Worktrees: `/solomon-start` creates each issue's branch in its own isolated git
  worktree rather than switching the primary checkout, so a dirty checkout never blocks
  a start and several issues can be in flight at once. The worktree lives at a sibling
  path beside the repo — `<parent>/<repo>-worktrees/<branch with '/' as '-'>`, e.g.
  `../solomon-harness-worktrees/feature-add-csv-export` — never nested inside the repo,
  so recursive tooling (test collection, IDE indexers) does not double-traverse it.
  Creation is idempotent; a conflicting path or a branch already checked out elsewhere is
  reported, never forced. Removal on merge/release is manual for now
  (`git worktree remove <path>`). The helper is `solomon-harness worktree <branch> [--base <ref>]`.
- Commits: Conventional Commits, no emojis (the commit-msg hook enforces this).
- Pull requests: conventional title, body that contains `Closes #<issue>`, opened
  as a draft until `/solomon-review` approves. Link the ADR if one was written.

## Issue body templates

- Feature/story: context, user story (`As a … I want … so that …`),
  acceptance criteria as Given/When/Then, scope and out-of-scope, definition of ready.
  The implementation-ready detail (exact `file:line` pointers, current versus
  expected behavior, the concrete approach, and the verification command) lives
  in the issue's spec doc under `docs/specs/` — see "Spec generation".
- Bug: summary, steps to reproduce, expected vs actual, environment, severity, the
  suspected location as `file:line`, the verification command that proves the fix,
  and a note that a regression test is required before the fix is closed.
- Idea: the job-to-be-done, the opportunity, the riskiest assumption to validate,
  and what evidence would justify promoting it to the backlog.

## Handoff contracts (bounded context)

To keep each stage's context bounded and avoid re-reading everything, every stage
transition produces a compact **handoff contract** artifact, and the receiving
stage reads that contract as its primary input — opening additional files only
through the pointers the contract gives. This is what prevents context overflow as
work moves across stages and sessions.

Rules:

- At the end of a stage that hands off, WRITE the contract to
  `.solomon/handoffs/issue-<N>-<from>-to-<to>.md` (the `.solomon/` directory is
  gitignored local state), then call
  `log_handoff(sender, recipient, contract_type, contract_path, status)` with
  `contract_path` set to that file.
- At the start of a stage, READ the latest incoming contract first
  (`get_latest_activity` returns the most recent handoff and its `contract_path`).
  Treat it as your bounded input; open the artifacts it points to (PLAN.md, the
  diff, the ADR, the PR) only when you actually need them. Do not re-derive prior
  context from scratch.
- The contract is a summary plus pointers, kept short on purpose. The full detail
  lives in the artifacts it references and in the project memory.

Contract template:

```
# Handoff: <from-stage> -> <to-stage> · issue #<N>
- Date: <YYYY-MM-DD> · Author: <agent>
- Issue: #<N> <url> · Branch: <branch> · PR: #<M> <url> · Board: <column>

## What this stage did
<2-5 lines>

## Artifacts (open only if needed)
- PLAN.md · docs/specs/<N>-*.md · docs/adrs/NNNN-*.md · PR #<M> · test plan · ...

## Acceptance criteria status
<which acceptance criteria are met; what remains>

## Input for the next stage (<to-stage>)
<exactly what the next stage needs to act — the bounded handoff>

## Open questions / risks
<anything the next stage must watch>
```

Each stage also persists the lifecycle facts to the project memory:

- `log_issue(github_id, title, type_, status, milestone_id)` when an issue is created
  or its status changes.
- `save_decision(title, rationale, outcome, author, branch, commit_sha)` for product,
  design, review, and release decisions (and for every ADR).
- `save_session(session_id, agent_name, task, messages)` to checkpoint long work.
- `get_open_issues` / `get_latest_activity` to resume where the team stopped.

## Single-driver lock and the loop run-log

Loop engineering turns the harness into a system that can advance work on a
cadence, so two drivers must never act on one repository at once. A documented
incident — two concurrent `/solomon-workflow` drivers — produced premature merges
that bypassed the review gate and flipped `core.bare=true` on a worktree. The
safety floor prevents that by construction:

- **Single-driver lock.** Before a stage that touches git/board state runs
  (`workflow`, `loop`, `start`, `review`, `release`, and the `scan-arch` /
  `scan-dedup` maintenance loops — and, at L3, every stage the policy's
  `requires_lock` names), the headless runner acquires one advisory lock anchored at the git
  *common* directory (`<common>/solomon-loop.lock`), so every linked worktree of
  the repository contends on the same file. A second driver is refused. The lock
  is a plain JSON file (the holder is auditable). Staleness favors safety: a
  **live process on the same host is never stale**, however long it has held the
  lock, so a long-running stage is never reclaimed mid-run; only a dead same-host
  pid, or a cross-host lock past the TTL (`DEFAULT_TTL_SECONDS = 1800`, since a
  remote pid cannot be probed), is reclaimed. Implementation:
  `solomon_harness/loop_lock.py`; the portable gate lives in `run_stage` so it
  enforces on both Claude Code and the Antigravity CLI. (`workflows.LOCKED_STAGES` is
  the source of truth for the static set.)
- **PreToolUse guard (Claude Code only).** A `loop-guard` hook in
  `.claude/settings.json` blocks `git push` / `gh pr merge` while another live
  driver holds the lock. It is defense-in-depth on top of the portable gate and
  fails open — the run_stage gate, not the hook, is the enforcement of record.
- **Recovery.** `solomon-harness loop-lock status` shows the current holder and
  whether it is stale; `solomon-harness loop-lock release` clears a stuck lock
  after a crash.
- **Run-log.** Each driven stage appends one entry to the `loop_runs` ledger in
  the project memory (the single source of truth). `solomon-harness log` renders
  a read-only, chronological feed over loop runs, decisions and handoffs, so the
  loop's own decisions are auditable. The concurrent-driver guard is the
  lockfile, never a row count — under the SQLite fallback each worktree has its
  own database, so a cross-worktree count would be invisible.

Human approval before any merge or release is unchanged: the lock bounds *who*
may drive, not *whether* a human approves. See `docs/loop-engineering.md` for the
full adaptation roadmap.

### Per-issue claims (second concurrency layer)

The single-driver lock above governs who may drive one checkout; it says
nothing about two checkouts, or two host tools, picking the same issue.
ADR-0027 layers a second mechanism on top of it, never a replacement: the
repo-wide lock (ADR-0010) serializes headless drivers per checkout; the
per-issue claim serializes sessions per issue across every checkout and host.

- **Authoritative substrate.** The sole source of truth is the git ref
  `refs/claims/issue-N`, compare-and-swapped via `git push --force-with-lease`
  — no database needed, so it works unchanged under the SQLite memory
  fallback, where every worktree otherwise has its own isolated database.
  Implementation: `solomon_harness/claim.py`.
- **Claim fields and TTL.** A claim's commit message is a JSON object with
  `session_id`, `acquired_at`, and `heartbeat_at`, active for 1800 seconds
  since the last heartbeat. A headless `dev start` spawns a daemon thread
  that re-touches `heartbeat_at` every
  `SOLOMON_CLAIM_HEARTBEAT_INTERVAL_SECONDS` (default 600 seconds), so a
  stage outliving the TTL before a PR exists never becomes reclaimable
  mid-implementation.
- **Stale-claim reclaim.** Past the TTL, another session may reclaim the
  issue unless its board card sits in `Code Review` or `QA`; when that
  liveness check cannot be determined (a `gh` failure, not "no PR found"),
  `claim_issue` fails closed rather than risk a double-pick on a transient
  outage.
- **Best-effort mirror and degrade paths.** `claim_issue`/`release_claim`
  also write or clear a mirror record in the project memory, purely so the
  holder is queryable via the memory MCP tools and the digest without a git
  fetch — never consulted for the decision itself. Memory down: the git ref
  still governs. Git fetch failing: the board-scan filters degrade to the
  unfiltered list, since the real enforcement point is the compare-and-swap
  inside `claim_issue` at `start` time, not the scan.
- **Operator commands and release.** `solomon-harness claim status <issue>`
  shows the holder, age, and PR/review protection; `claim release <issue>`
  clears it. A successful `gh pr merge` also force-releases the claim.

See ADR-0027 for the full decision, and ADR-0010 for the repo-wide lock this
layers on top of.

## Autonomy levels and the kill-switch

How far the automation path (`solomon-harness dev <stage>` and any host-scheduled
cadence) may act is one dial, set in the project's `.agent/config.json` `loop`
block (overridable with `SOLOMON_LOOP_AUTONOMY`) and enforced in portable Python
inside `run_stage` (`solomon_harness/loop_policy.py`), so it holds on both Claude
Code and the Antigravity CLI — not only in a Claude-only hook.

```json
"loop": { "autonomy": "L2", "maker_model": "...", "checker_model": "...",
          "denylist": ["**/*.enc", "**/secrets/**"] }
```

- **human (default):** no restriction. A repository with no `loop` block behaves
  exactly as before — the human is driving.
- **L1 (report):** the loop may only scan and propose (`loop`); every mutating
  stage is denied.
- **L2 (assisted):** the loop may create work and open draft PRs (`idea`..`review`)
  but never merge or release.
- **L3 (unattended):** as L2, but may run on a cadence and only while it holds the
  single-driver lock.

Three rules no level can widen: **merge, release, and moving a card to Done are
permanently human-gated**; an unknown/typo'd level **fails closed** (denied); and
the **kill-switch** halts every stage at once. A blocked stage exits non-zero (3),
never silently.

- `solomon-harness loop-policy` — show the level, kill-switch state, denylist, and
  the per-stage allow/deny table.
- `solomon-harness loop-stop` / `loop-stop --clear` — engage or clear the
  kill-switch (a sentinel beside the lock at the git common dir).

The maker/checker split (a verifier on a *different* model than the maker) is
declared in the same block and surfaced by `loop-policy`; it complements, and does
not replace, the human `/solomon-review` gate.

## Maintenance loops, notifications and budget

Two standing maintenance loops give the harness a generative source of work — their
input is the repository's current state, not a queued issue — bounded by the
autonomy ladder, the single-driver lock, and the denylist:

- `/solomon-scan-arch` (software_architect) — one architectural-drift finding per
  run.
- `/solomon-scan-dedup` (software_engineer) — one duplicated abstraction per run.

Each acts on at most one finding and terminates at a **draft PR** routed to the
unchanged `/solomon-review` gate (low-confidence findings go to `Ideas`/`Backlog`
instead). They are `dev` stages, so a host scheduler can run them on a cadence and
the autonomy policy gates them (allowed at L2/L3, denied at L1). Their contracts
live in the agents' `architecture_scan_loop` / `duplication_scan_loop` skills.

- **Notifications** (`solomon-harness notify`, `solomon_harness/notify.py`) are
  outbound-only: status flows out to the console or a webhook
  (`SOLOMON_NOTIFY_WEBHOOK`, never committed), but the only state-changing approval
  path stays the human gh review. No inbound listener.
- **Budget** (`solomon-harness loop-budget`, `solomon_harness/loop_budget.py`)
  records each run's reported cost; when the daily ceiling
  (`loop.daily_cost_ceiling_usd`) is reached, the automation path degrades to
  report-only.

## ADR trigger

`/solomon-start` and `/solomon-release` must evaluate whether the change is
architecturally significant using the checklist in
`agents/software_architect/skills/architecture_decisions_in_project_memory.md` and
`docs/adrs/README.md`. If significant, the software_architect agent writes
`docs/adrs/NNNN-<slug>.md` from `docs/adrs/0000-adr-template.md`, records it with
`save_decision`, and links it in the PR. If not significant, state that explicitly
in the PR so the decision to skip an ADR is also visible.

The statement is machine-checked (ADR-0031): every PR body carries exactly one
canonical line — `ADR: docs/adrs/NNNN-<slug>.md` or
`ADR: not warranted — <reason>` — enforced by `scripts/check-adr-gate.py` in a
dedicated workflow that re-runs on body edits, and re-checked mechanically by
the review stage before the architect judges whether the line's content is
honest. Every flow that opens a PR (start, release prep, the scan loops)
writes the line.

## Authorization

These workflows perform outward-facing actions (creating issues, branches, PRs,
merges, releases). Confirm with the user before any merge or release, and never
push to a protected branch directly.
