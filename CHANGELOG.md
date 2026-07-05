# Changelog

## [0.12.0] - 2026-07-05

### Added
- stream progress to terminal and support python-wrapped pr-create (#204)
- prepare harness only for agy and claude, remove gemini (#202)
- cockpit per-user activity series — the velocity chart (slice 3b) (#193)
- auto-chain the Review stage after start and staff it with diff-selected domain lenses (#186)
- episodic work graph — worked_on edges and graph-based resume (#187)
- typed states, transitions, gated embeddings, and a closed durability funnel (#180)
- deepen roster to specialist depth and add long_run_strategist and scalper (#168)
- implement autonomous audit-trigger subcommand (#143)
- loop-auto stage and /solomon-loop-auto command (#154)
- scaffold, register, and compile a new agent (#142)

### Changed
- rename /solomon-loop to /solomon-workflow and /solomon-loop-auto to /solomon-loop (#164)

### Fixed
- check permanently human-gated stages before human autonomy early-return (#203)
- grant the headless start engine --add-dir into its worktree (#200)
- same-session lock reentrance for nested headless dev stage calls (#198)
- review owns the interactive merge; release never merges individual PRs (#195)
- headless /solomon-loop iterations execute instead of stalling (#196)
- renumber the episodic work graph ADR to 0018 to restore trunk CI (#189)
- pass allowed-tools frontmatter through to the headless claude engine (#181)
- never create a board from a failed or per-issue lookup (#169)
- preserve handoff contract_path in get_latest_activity (#146)
- run SurrealDB schema DDL statement-by-statement (#147)
- recompute the release window at tag time and guard prerelease SemVer parsing (#148)
- retry _gh once and self-heal the token on a transient gh failure (#139)
- use all issue statuses for the release wiki delivered-work section (#152)
- enumerate agents/*/agents/*.md on disk in validate-agents.py (#150)
- guard cockpit write routes against traversal and unauthenticated writes (#151)
- resolve gh via PATH and strip GIT_* env at every subprocess call site (#153)
- close single-driver loop lock gaps in autonomous mode and pid staleness (#155)
- batch velocity reads across tenants (#157)
- make save_loop_run resilient and mirror delete_memory (#159)

## [0.3.1] - 2026-06-27
