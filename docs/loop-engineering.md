# Loop engineering adaptation

This document records how solomon-harness adapts to loop engineering and the
roadmap for that work. Loop engineering, named by Addy Osmani (June 2026), is the
shift from prompting an agent turn by turn to designing the system that prompts
it: a recursive goal that finds work, acts, verifies, remembers, and runs on a
cadence. The lineage includes Boris Cherny (Claude Code), Peter Steinberger
(OpenClaw), and Geoffrey Huntley (the Ralph loop).

## Where the harness already stands

The harness already holds five of Osmani's six building blocks; the gap is the
machinery that makes a cadence safe.

| Building block | State | Note |
| --- | --- | --- |
| Skills | Strong | `agents/<name>/skills/`, external skill sources |
| Sub-agents (maker/checker) | Strong | `/solomon-review` is a separate-agent gate |
| State / memory | Strong | SurrealDB + SQLite, handoff contracts |
| Connectors (MCP) | Partial | `solomon-memory` MCP + `gh`; no notification egress |
| Worktrees | Partial / fragile | `core.bare` flip, orphan accumulation |
| Automations / scheduling | Absent | `/solomon-workflow` is manual, one confirmed step per run |

## Hard constraints

These are non-negotiable and bound every option below.

- **C1 — The host tool is the model loop.** A self-hosted Python LLM loop was
  built and reverted; it must not return. Cadence comes from host-tool primitives
  (Claude Code scheduled tasks, the `/loop` skill, the shipped `ralph-wiggum`
  plugin, and the equivalent AGY or Codex scheduling surface). The harness
  supplies loop design and policy, not a replacement model runner.
- **C2 — The review gate is sacred.** Concurrent drivers once caused premature
  merges that bypassed review. Any autonomy preserves human approval before merge
  or release and serializes drivers with a single-driver lock. The loop is therefore
  host-orchestrated and human-gated, never fully autonomous: the host tool runs the
  markdown stages and a human approves every merge and release. No code decides the
  next stage on its own.
- **C3 — Conventions.** Branches `feature/<slug>` / `bugfix/<slug>` with no issue
  number; Conventional Commits with no `Co-Authored-By` trailer; enumerated user
  choices ending in "Other"; no emojis or AI cliches in artifacts.
- **C4 — Architecture.** Modular agents, single-concern skills, hexagonal by
  default, strict TDD.
- **C5 — Three-host parity.** Claude, AGY, and Codex adapters compile from the
  same `.agents/solomon` catalog. Native lifecycle hooks differ in syntax and
  trust behavior, so every hard gate also exists in portable Python.

## What each creator adds beyond Osmani

- **Boris Cherny (Claude Code):** standing maintenance loops that manufacture
  their own work — an architecture-scan loop and a duplicate-abstraction finder —
  and open draft PRs "like any coder". Autonomy terminates at the review gate.
- **Peter Steinberger (OpenClaw):** every decision traces back to a plain file on
  disk; self-improving skills; a multi-channel control surface (reduced here to
  outbound notification only, to respect C1/C2); Pi-style minimalism.
- **Geoffrey Huntley (Ralph loop):** fresh context every iteration, one bounded
  task per tick, success-criteria gating, filesystem + git as the only memory.
  The harness's per-invocation scan and handoff contracts already embody this; the
  sharpening is to make the reset and the exit condition explicit.

## Roadmap

Sequenced safety-first: nothing schedules itself until a single driver and an
auditable record are guaranteed.

- **Phase 0 — Safety floor (shipped).** Single-driver lock, portable gate in
  `run_stage`, normalized native pre-tool guards, the `loop_runs` run-log, and
  the `solomon-harness log` feed. See below.
- **Phase 1 — Day-to-day UX.** Board digest folded into `cli run`; a one-keystroke
  resume decision card (enumerated options) in `/solomon-workflow`.
- **Phase 2 — Governed autonomy (shipped).** An L1/L2/L3 maturity policy
  (`solomon_harness/loop_policy.py`) enforced portably in `run_stage`; merge,
  release and board-Done permanently human-gated; an unknown level fails closed; a
  denylist; the maker/checker model split surfaced; and a kill-switch
  (`solomon-harness loop-stop`, `loop-policy`). See below.
- **Phase 3 — Maintenance loops + budget (shipped).** `/solomon-scan-arch` and
  `/solomon-scan-dedup` (gated `dev` stages) that open draft PRs only; outbound
  notification egress (`notify.py`); a post-hoc cost ceiling (`loop_budget.py`)
  that degrades the automation path to report-only. See below.
- **Phase 4 — Ownership (loop_engineer shipped).** A dedicated `loop_engineer`
  agent now owns the lock/policy/run-log/budget/notify modules, with six skills
  citing their real APIs (the precedent `practice_curator` set for a deferred
  agent), and is indexed in `agents/AGENTS.md`. Remaining: worktree hygiene and
  state GC.

## Phase 0, as shipped

| Piece | Where |
| --- | --- |
| Single-driver lock (git-common-dir anchor, O_EXCL, heartbeat TTL, reclaim) | `solomon_harness/loop_lock.py` |
| Per-issue claim/lease (git-ref CAS, TTL + heartbeat, fail-closed reclaim) | `solomon_harness/claim.py` |
| Portable gate for mutating stages | `run_stage` in `solomon_harness/workflows.py` |
| Native pre-tool guards (defense-in-depth, fail-open) | `host-hook pre-tool-use` + `.claude/settings.json`, `.agents/hooks.json`, inline hooks in `.codex/config.toml` |
| Lock inspection / recovery | `solomon-harness loop-lock status` / `release` |
| Run-log ledger | `loop_runs` table + `save_loop_run` / `list_loop_runs` |
| Read-only activity feed | `solomon_harness/loop_log.py` + `solomon-harness log` |

The lock is the precondition for every later phase: it converts the documented
concurrent-driver race into impossible-by-construction, in code rather than in
advisory prose.

Codex 0.144.4 may omit project hooks in a linked Git worktree even when it loads
the MCP section from the same trusted `.codex/config.toml`; normal repositories
load both generated hooks. No global hook or trust bypass is installed as a
workaround. The Python policy and single-driver lock remain the enforcement of
record.

## Phase 1, as shipped

`solomon_harness/digest.py` renders the board digest and next step options into
`solomon-harness run` (the normalized start/first-invocation hook): resume point,
open issues, the last loop run, and PRs awaiting review. It checks memory for
pending tasks (or shows open issues if empty) and automatically prints the
enumerated options. Claude, AGY, and Codex consume the same card through their
native lifecycle adapters.

## Phase 2, as shipped

| Piece | Where |
| --- | --- |
| L1/L2/L3 ladder + `human` default, fail-closed on a bad level | `solomon_harness/loop_policy.py` |
| Portable enforcement (all three hosts), exit 3 on deny | `run_stage` in `solomon_harness/workflows.py` |
| Permanent human gate for merge / release / Done | `HUMAN_GATED_STAGES` |
| Path denylist + maker/checker split surfaced | `is_denied_path`, `checker_split_ok` |
| Kill-switch (sentinel beside the lock) | `solomon-harness loop-stop` / `loop-policy` |

Set the level in the project's `.agents/solomon/config/project.json` `loop` block (or
`SOLOMON_LOOP_AUTONOMY`); see `docs/solomon-workflow.md`.

## Phase 3, as shipped

| Piece | Where |
| --- | --- |
| Standing maintenance loops (one lens each, draft-PR-only) | `/solomon-scan-arch`, `/solomon-scan-dedup` (gated `dev` stages) |
| Their guardrail skills (one-open-PR budget, denylist, run note) | `agents/software_architect/skills/architecture_scan_loop.md`, `agents/software_engineer/skills/duplication_scan_loop.md` |
| Outbound-only notification (console / webhook, env URL) | `solomon_harness/notify.py`, `solomon-harness notify` |
| Post-hoc cost ceiling -> report-only | `solomon_harness/loop_budget.py`, `solomon-harness loop-budget` |

The scan loops are generative — their input is the repo state, not a queued issue
— and they terminate at a draft PR routed to the unchanged `/solomon-review` gate,
under the autonomy ladder (L2/L3), the single-driver lock, and the denylist. This
is Cherny's always-on-maintenance practice, bounded.

## Sources

- Addy Osmani, "Loop Engineering" (addyosmani.com/blog/loop-engineering, June 2026).
- Boris Cherny, Acquired / WorkOS interview on loops vs. agents (June 2026).
- Peter Steinberger, OpenClaw (github.com/openclaw/openclaw).
- Geoffrey Huntley, the Ralph Wiggum loop; `anthropics/claude-code` `ralph-wiggum` plugin.
