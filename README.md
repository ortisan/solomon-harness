# Solomon Harness

A multi-agent harness for controlling, planning, and delivering software. It
defines a team of specialist agents, a project memory, and an end-to-end,
GitHub-integrated delivery workflow that runs inside the host tool you already
use — Claude Code or the Antigravity CLI (agy). The harness supplies the agents and the
memory; the host tool supplies the model loop. The delivery loop is
host-orchestrated and human-gated, not fully autonomous: the host tool runs the
workflow prompts and a human approves every merge and release.

It ships a dual-backend memory layer (SurrealDB primary, SQLite fallback), a
non-destructive scaffolder, and a set of `/solomon-*` workflows that take a
piece of work from idea to release while persisting every decision and handoff.

---

## Getting started

`solomon-harness` is a single Python CLI — engine, installer, prerequisite check,
and headless workflow runner all in one. `solomon-harness doctor` checks the
prerequisites and installs the ones that are safe to install (uv) without sudo.

### Prerequisites

- **Python 3.10+** and [uv](https://github.com/astral-sh/uv) (`solomon-harness doctor` installs uv if missing).
- A **host tool** to run the workflows: [Claude Code](https://claude.com/claude-code) or the **Antigravity CLI (agy)**.
- **GitHub CLI** (`gh`), authenticated, for the issue/PR/board steps (`gh auth login`; the board needs the `project` scope).
- **Docker** (optional) to run SurrealDB locally; without it the harness falls back to SQLite.

### Install the CLI

```bash
git clone <this-repo> && cd solomon-harness
uv sync                 # create the venv and install dependencies
uv pip install -e .     # expose the `solomon-harness` CLI on PATH
```

### Install into an existing project

From your project directory, run init: it checks prerequisites, copies the harness
in (agents, the `solomon_harness` package, scripts, config), configures it,
generates the host-tool integrations, sets the project's memory tenant, and
indexes the codebase. The harness's own documents never travel: your project's
`docs/` receives only its own empty `adrs/` and `specs/` trees, seeded with
each convention's template and README (ADR-0029).

```bash
cd /path/to/your/project
solomon-harness init            # add --non-interactive for defaults
```

Running it from the harness repo itself configures it in place (no copy).

### Share the agents across projects (once per machine)

```bash
solomon-harness install-global
```

This installs the agents and `/solomon-*` commands into the user-global
`~/.claude` (and Antigravity plugins/commands into `~/.gemini`), registers the `solomon-memory`
MCP server, and sets up the shared memory home in `~/.solomon-harness`. After
this, every project on the machine uses the same agents with no per-project
copies; a project carries only its `.agent/config.json` (its tenant).

### Shared memory and tenancy

There is one memory backend per machine, not one per project. The SurrealDB
stack lives in `~/.solomon-harness/docker-compose.yml` and the harness starts it
on session start:

```bash
solomon-harness memory-up       # start the shared backend if it is not running
solomon-harness memory-down     # stop it
```

- **One shared instance.** All projects connect to the same SurrealDB, so there
  is no per-project container fighting over a port.
- **Per-project tenant.** Each project gets its own SurrealDB *database* (the
  tenant), derived from the git remote (e.g. `ortisan-solomon-harness`), inside
  the shared `solomon` namespace. Memory never leaks between projects.
- **Auto-assigned port.** The backend prefers host port 8099 (8000 is too
  contended) but, if it is taken, claims the next free port and records it in
  `~/.solomon-harness/memory.json`. The chosen port is written into the compose
  mapping and each project's config URL, so a busy port never blocks startup.
- **Conflict is safe.** If a non-SurrealDB process already holds the configured
  port, `memory-up` detects it, does *not* run `docker compose up` (which would
  fail to bind), and the client transparently uses SQLite under
  `memory/long_term/` — work is never blocked.

Provide credentials via the `SURREAL_USER` / `SURREAL_PASS` environment variables
(none are committed); locally they default to `root`/`root`. The Surrealist IDE is
at `http://localhost:3000`.

In Claude Code or the Antigravity CLI (agy), drive the lifecycle with slash commands:

```text
/solomon-workflow  (end-to-end / continue)
/solomon-issue     add rate limiting to the public API
/solomon-refine    42
/solomon-start     42
/solomon-review    17   # optional: review auto-runs at the end of start; invoke directly only for an existing PR
/solomon-release   17
```

Or headlessly, for CI and automation:

```bash
SOLOMON_ENGINE=claude solomon-harness dev start 42     # or SOLOMON_ENGINE=agy
```

Each command shapes the work with the right specialist agents, creates and moves
the GitHub issue/PR/board card, evaluates whether an ADR is warranted, and records
the decisions and handoffs in the project memory.

---

## How it works

Work flows across a GitHub Project (v2) board, each column owned by a workflow and
the specialists that drive it:

```
Ideas → Backlog → Ready → In Progress → Code Review → QA → Done
```

| Workflow | Stage | Driving agents |
| --- | --- | --- |
| `/solomon-workflow` | run a task end-to-end or continue | loop_engineer |
| `/solomon-idea` | capture an idea | product_owner |
| `/solomon-issue` | create a feature/story; a vague demand first passes the Socratic elicitation gate, and every issue gets a `docs/specs/` spec doc | product_owner |
| `/solomon-bug` | create a bug | qa, software_engineer |
| `/solomon-refine` | ready an issue | product_owner, scrum_master |
| `/solomon-start` | branch, plan, TDD, draft PR | scrum_master, software_engineer, software_architect |
| `/solomon-review` | review gates (auto-runs at the end of start) | qa, security, software_architect, plus up to two diff-selected domain lenses |
| `/solomon-release` | deliver and release | sre, software_engineer |

The conventions every workflow follows (board columns, Git Flow branches, labels,
the memory handoff contract, the ADR trigger) live in
[`docs/solomon-workflow.md`](docs/solomon-workflow.md).

---

## Capabilities

### Specialist agents

Twenty-nine role-specific agents, each defined modularly under `agents/<name>/`
(`persona.md`, the role profile `agents/<name>.md`, `skills/`, and
`.agent/config.json`). They are exposed to the host tools as Claude Code
subagents and Antigravity commands. The count above is the number of `agents/*/agents/*.md`
role profiles; `tests/test_readme_sync.py` fails if this table (or the count) drifts
from that directory listing.

| Agent | Focus |
| --- | --- |
| `agent_builder` | scaffolds new specialist agents |
| `product_owner` | PRDs, user stories, acceptance criteria, roadmapping, traceability |
| `scrum_master` | milestones, backlog, sprints, flow metrics, Git Flow |
| `software_architect` | C4, ADRs, design contracts, resilience patterns, review gate |
| `software_engineer` | TDD, clean code, REST/error handling, debugging, Git Flow |
| `qa` | the full test pyramid (unit, integration, E2E, mutation), CI gates |
| `security` | STRIDE threat modeling, SAST, dependency and vulnerability checks |
| `sre` | progressive delivery, DORA, PRR, Kubernetes, incident runbooks |
| `observability` | logging, metrics, tracing, dashboards, OpenTelemetry |
| `auth_engineer` | OAuth/OIDC, MFA/passkeys, sessions/tokens, RBAC/ABAC, OPA |
| `frontend` | React and Angular, state, design tokens, accessibility |
| `android` | Kotlin, Jetpack Compose, MVVM, Coroutines/Flow, Play delivery |
| `apple` | Swift, SwiftUI, Swift Concurrency, SwiftData, App Store delivery |
| `flutter` | Flutter/Dart, clean architecture, widget and integration tests |
| `ml_engineer` | model training/validation, statistical modeling, leakage checks |
| `quant_trader` | strategies, backtests, slippage/cost, Sharpe/drawdown risk |
| `long_run_strategist` | long-horizon strategies: trend/momentum, factors, allocation, rebalancing |
| `scalper` | intraday scalping: microstructure, order flow, execution, tick-data backtests |
| `swing_trader` | daytrade and swing strategies (minutes-to-weeks holds), overnight risk, spec handoff |
| `data_analyst` | SQL analytics, big data (Spark/ClickHouse), reporting |
| `dba` | data modeling, performance tuning, migrations, replication |
| `documenter` | technical and business docs, user guides, design docs |
| `seo` | semantic structure, metadata, indexing, page speed, audits |
| `educational_psychologist` | Cognitive Load Theory, retrieval practice, spaced repetition, dual coding |
| `legacy_modernizer` | dependency/risk-ordered legacy modernization planning, human-gated delegation |
| `loop_engineer` | autonomous-loop mechanics: single-driver lock, autonomy ladder, run-log, cost budget |
| `practice_curator` | benchmarks delivered work and agent guidance against the state of the art |
| `peer_reviewer` | independent peer review of AI work: claim verification, adversarial re-testing, verdicts |
| `research_analyst` | fundamental/qualitative research: DCF, multiples, sum-of-the-parts, sources playbook |

The shared rules, the memory guide, and the agent index are the single source of
truth in [`agents/AGENTS.md`](agents/AGENTS.md); `CLAUDE.md`, `AGY.md`, the root
`AGENTS.md`, and the Copilot instructions all point there.

### Skills

Each agent carries granular, single-topic skills under `agents/<name>/skills/` —
deep, version-current references (real APIs, thresholds, code, pitfalls, and a
definition of done), modeled on the `auth_engineer` set. The format is documented
in `agents/AGENTS.md`. You can also pull skills from external skill-server
repositories listed in `skill-sources.json` with `solomon-harness skills`.

### Delivery workflows

Eleven `/solomon-*` commands — the count of `.claude/commands/solomon-*.md` files,
guarded by `tests/test_readme_sync.py` — are authored once as Claude Code
commands under `.claude/commands/` and mirrored to Antigravity commands under
`.gemini/commands/`. Eight drive the lifecycle table above; `/solomon-loop`
runs the autonomous parallel loop over Ready issues; and the remaining two,
`/solomon-scan-arch` and `/solomon-scan-dedup`, are standing maintenance loops that
scan the codebase for architectural drift and duplication (see
`docs/solomon-workflow.md`). They orchestrate the specialist agents, the `gh` CLI, the
GitHub board, and the project memory, and confirm before any outward-facing action
(creating issues/PRs, merging, releasing).

### Project memory and MCP

A SurrealDB-primary, SQLite-fallback store (`solomon_harness/tools/database_client.py`)
records decisions, sessions, handoffs, issues, milestones, and backtests. It is
exposed as the `solomon-memory` MCP server (`solomon_harness/mcp_server.py`),
registered for Claude Code (`.mcp.json`) and the Antigravity CLI (`.gemini/settings.json`),
with tools: `save_decision`/`get_decision`, `save_memory`/`get_memory`,
`log_issue`/`get_open_issues`/`get_issue`, `create_milestone`/`list_milestones`,
`save_release`/`get_release`/`list_releases`, `save_backtest`,
`save_session`/`get_session`, `log_handoff`, and `get_latest_activity`.

The SurrealDB backend is a single shared instance per machine, defined in
`~/.solomon-harness/docker-compose.yml` and managed by `solomon_harness/memory.py`.
Each project is isolated as its own SurrealDB database (the tenant, derived from
the git remote by `solomon_harness/home.py`), and the host port is auto-assigned to
avoid clashing with whatever already holds the preferred port. See *Shared memory and tenancy*.

### Architecture Decision Records

The `start` and `release` workflows evaluate whether a change is architecturally
significant (the checklist in `docs/adrs/README.md`) and, if so, write a MADR record
to `docs/adrs/NNNN-*.md` and persist it with `save_decision`.

### Stack-based agent selection

`solomon_harness/agent_selection.py` inspects the project's files and manifests and
enables only the agents the stack needs (a core delivery/planning set plus platform
and domain agents on detected signals), instead of all twenty-six.

### GitHub project board

`solomon_harness/github.py` wraps the `gh` CLI to ensure a Project (v2) board
exists and move issue cards across the lifecycle columns; `init` creates the board
for GitHub-hosted projects. Each repository gets one board, titled after the
repository and linked to it. The harness configures the seven lifecycle columns as
the Status field options, but GitHub's API has no mutation to create or lay out
views, so switching the default view to a Board grouped by Status is a one-time
manual step in the project UI (`ensure-board` prints the reminder).

### Codebase indexing

`solomon-harness index` walks the project (excluding binaries, build output, and
large files) and stores each file in the memory so agents can query the codebase.

### Host-tool integrations

`scripts/generate-integrations.py` regenerates the Claude Code subagents
(`.claude/agents/`) from `agents/` and the Antigravity commands (`.gemini/commands/`)
from `.claude/commands/`. `solomon-harness compile` runs it automatically so the
integrations never drift from their sources.

### Non-destructive scaffolding

`solomon-harness compile` only scaffolds genuinely-missing agent entrypoints and
config — it never overwrites a hand-authored persona or config — and regenerates
the host-tool integrations. A test guards that scaffolding never mutates tracked
source.

### Engineering conventions

The project-wide architecture, observability, and security defaults (Hexagonal,
OpenTelemetry, secure-by-default) live in the owning agents' skills (for example
`software_architect/skills/architecture_styles`) and in `agents/AGENTS.md`;
deviating from one requires an ADR.

### Quality and invariants

Strict TDD is the standard; the suite (run with the command below) covers the
scaffolder, memory client, MCP server, agent selection, the board helpers, the
host integrations, the Antigravity mirror, and the prerequisite/workflow CLI, plus
invariant guards (scaffolding is non-destructive, the MCP server builds, the
SurrealDB path works against a live server). The humanizer rules forbid emojis and
AI cliches in all generated output.

---

## CLI reference

### `solomon-harness`

The table below lists every subcommand `solomon_harness/cli.py` registers on
`build_parser()`, in the order they are defined there — it is meant to be
regenerated from that function rather than hand-counted; `tests/test_readme_sync.py`
fails CI if a subcommand is added, removed, or renamed here without updating this
table.

| Command | Description |
| --- | --- |
| `db-init` | Initialize the long-term database client and tables |
| `eval` | Run the agent evaluations test suite |
| `run [task]` | Show the resume point (latest activity, open issues) and list the workflows |
| `init [--non-interactive]` | Install into / bootstrap a project: prerequisites, files, config, tenant, board, index |
| `compile` | Compile agent harnesses and regenerate host-tool integrations |
| `index` | Index the project codebase into the memory |
| `wiki` | Refresh the living code-overview wiki page from the index |
| `memory-up [--wait N]` | Start the shared memory backend (docker compose) if it is not already serving |
| `memory-down` | Stop the shared memory backend |
| `memory sync` | Replay pending mirror records to SurrealDB and report the counts |
| `reconcile [--dry-run]` | Repair shared-memory issue/tracking rows from GitHub and canonicalize non-terminal status tokens |
| `install-global [--no-mcp]` | Install agents + `/solomon-*` commands into `~/.claude`/`~/.gemini`, the MCP server, and the shared memory home |
| `doctor [--no-install]` | Check prerequisites and install the safe ones (uv) |
| `healthcheck` | Report runtime readiness and pending init items (Docker, memory, board, global install) |
| `git-repair` | Repair local git config by unsetting stray `core.worktree` and setting `core.bare` to false |
| `loop-lock [status\|release]` | Inspect or clear the single-driver loop lock (crash recovery) |
| `claim status\|release <issue>` | Inspect or release an issue claim/lease |
| `log [--last N]` | Show the read-only loop activity feed (loop runs, decisions, handoffs) |
| `loop-guard` | PreToolUse hook: block push/merge while another driver holds the loop lock |
| `loop-stop [--clear]` | Kill-switch: halt all autonomous loop stages immediately (or clear it) |
| `loop-policy` | Show the autonomy level, kill-switch state, denylist, and per-stage gates |
| `notify <message> [--event EVENT]` | Send an outbound status notification (console or webhook) |
| `loop-budget` | Show today's autonomous-loop cost spend versus the ceiling |
| `dev <stage> [args]` | Run a delivery workflow headless (idea, issue, bug, refine, start, review, release) |
| `release plan\|prep [version]\|check\|wiki-page [version]` | Plan, prepare, check, or document a milestone-gated release |
| `worktree <branch> [--base REF]` | Create or locate the isolated git worktree for a branch (used by `/solomon-start`) |
| `skills sources \| list <src> \| add <src> <skill> --agent <name>` | Manage external skills |
| `broker route \| apply --file <json>` | Capability broker (ADR-0008): build the route/gap verdict, or run a human-approved acquisition |
| `agents list \| help \| show <name>` | List or show the generated subagents |
| `github <args>` | GitHub board and PR helpers (ensure-board, set-status, add-issue, merge, pr-create) |

For `dev`, set `SOLOMON_ENGINE=claude` (default) or `agy` to choose the engine.
`python -m solomon_harness.github ensure-board | set-status --issue N --status "<col>" | add-issue --issue N`
manages the board directly.

---

## Repository layout

```
solomon-harness/
├── agents/                  # Source-of-truth specialist agents + AGENTS.md (the rules)
│   └── <name>/              #   persona.md, agents/<name>.md, skills/, .agent/config.json
├── .claude/                 # Claude Code: agents/ (subagents) and commands/ (/solomon-*)
├── .gemini/                 # Antigravity CLI plugin: commands/ (generated) and settings.json (MCP)
├── docs/                    # adr/ (ADRs) and solomon-workflow.md (conventions)
├── solomon_harness/         # Core package
│   ├── bootstrap.py         #   init / install / scaffold / codebase indexing
│   ├── cli.py               #   the solomon-harness CLI (init, doctor, dev, compile, ...)
│   ├── agent_selection.py   #   stack -> agents
│   ├── prereqs.py           #   prerequisite check / uv install (doctor)
│   ├── workflows.py         #   headless /solomon-* runner (dev)
│   ├── github.py            #   GitHub project board helpers
│   ├── mcp_server.py        #   solomon-memory MCP server
│   ├── memory_service.py    #   memory service layer
│   ├── skills.py            #   external skill fetching
│   ├── evals.py             #   per-agent evaluation suite
│   ├── templates/           #   bundled harness scaffold template
│   └── tools/               #   database_client.py
├── scripts/                 # generate-integrations, document-skills, scrum-master, validators
└── tests/                   # Verification suite
```

---

## Customization

- **Add an agent:** create `agents/<name>/agents/<name>.md`, `persona.md`, `skills/`,
  and `.agent/config.json`, add the agent to the `agents/AGENTS.md` index, then run
  `solomon-harness compile` and `scripts/document-skills.py`.
- **Override templates:** create a `templates/harness` or `templates/patterns` folder
  in the project root; the compiler prefers local templates over the bundled ones.

---

## Verification

```bash
uv run python -m unittest discover -s tests
uv run ruff check solomon_harness scripts tests
```
