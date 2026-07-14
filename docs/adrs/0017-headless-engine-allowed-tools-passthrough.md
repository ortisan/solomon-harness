# ADR-0017: Forward each stage's allowed-tools frontmatter to the headless engine

- Status: accepted
- Date: 2026-07-04
- Deciders: software_architect, security
- Issue: #179

## Context and problem statement

`solomon-harness dev <stage>` runs a `/solomon-*` workflow stage headless by
building a prompt from `.claude/commands/solomon-<stage>.md` and piping it into
`claude -p` (or `gemini`/`agy`) with no TTY. That command file's YAML
frontmatter already declares an `allowed-tools:` line per stage (e.g.
`solomon-start.md`: `Bash(gh:*), Bash(git:*), Bash(uv run:*), ...,
mcp__solomon-memory__get_issue, ...`) — written and reviewed for exactly this
purpose, and honored automatically when a human invokes the same file
interactively as a slash command. `run_stage`'s `build_prompt`, however,
strips that frontmatter before sending the body to the engine, so it never
reaches the headless process. With no one present to approve a permission
prompt, every tool call outside the ambient, narrower project
`.claude/settings.json` allowlist (git status/diff/log, `gh pr *`) blocks —
so `dev refine`/`start`/`review` silently no-op on any stage that needs
`gh issue *` or an `mcp__solomon-memory__*` tool, which is most of them. This
breaks the entire premise of L2/L3 unattended autonomy and Autonomous Mode.

This is architecturally significant, not just a bugfix detail: it is a STRIDE
elevation-of-privilege change. Before this decision, an unattended process
could not effectively execute `gh`/`git`/memory-write tool calls at all
(they silently blocked); after it, the headless engine actually executes
whatever that stage's frontmatter grants. The review that produced this ADR
also surfaced, and this decision explicitly records, a related pre-existing
gap: `loop_policy.LoopPolicy.decide_stage` allows every stage — including
`release` — at the default, unconfigured `human` autonomy level, before any
`HUMAN_GATED_STAGES` check fires. The documented invariant that merge,
release, and moving a card to Done are "permanently human-gated at every
level" (`docs/solomon-workflow.md`) is therefore not fully backed by a
technical control at the default level today; this decision is what makes
that gap operationally reachable via the primary `claude` engine path for the
first time (the `agy` engine could already reach it via its own
`--dangerously-skip-permissions` bypass). Tracked separately, not fixed here,
as #183 (policy-layer gap) and #185 (the `Bash(gh:*)` wildcard in
review/release frontmatter covering merge/release with only prose stopping
self-merge under normal single-driver operation).

## Decision drivers

- Fix the reported defect: headless stages must actually be able to do the
  work their own already-reviewed frontmatter declares, not silently no-op.
- Least privilege: grant only what each stage's own frontmatter already
  declares — no blanket bypass, no broadening of the interactive baseline.
- No new trust boundary: whatever mechanism is chosen must not let a lower-
  trust input (an issue body, external skill content) influence what an
  unattended process is allowed to do.
- Minimal surface: the fix should not require redesigning the autonomy
  ladder, the single-driver lock, or the denylist to land.

## Considered options

- Pass `--dangerously-skip-permissions` to the `claude` engine (matching the
  `agy` engine branch).
- Broaden the project `.claude/settings.json` / `.claude/settings.local.json`
  allowlist to cover `gh issue *`, `gh project *`, and the
  `mcp__solomon-memory__*` tools repo-wide.
- Forward each stage's own already-declared, already-reviewed
  `allowed-tools:` frontmatter to the `claude` engine via its own
  `--allowed-tools <tools...>` flag.
- Do nothing beyond making the failure loud (non-zero exit, `loop_runs`
  status `failed`) instead of a silent no-op.

## Decision outcome

Chosen option: forward each stage's own `allowed-tools:` frontmatter via
`claude`'s `--allowed-tools` flag, scoped to the `claude` engine only,
because it satisfies least-privilege and reuses a scoping contract that
already exists and was already reviewed for interactive use, rather than
introducing a new one or blanket-bypassing everything.

- `_allowed_tools(workspace_root, stage)` (`solomon_harness/workflows.py`)
  extracts the frontmatter's `allowed-tools:` value from the same command
  file `build_prompt` already reads. `run_stage` appends
  `--allowed-tools <value>` to the `claude` engine's argv when present.
  Nothing changes for `agy` (already bypasses all permissions) or `gemini`
  (own `--skip-trust` mechanism, out of scope here).
- The command files themselves (`.claude/commands/solomon-*.md`) are
  git-tracked, hand-authored, and go through the same PR review as code —
  `bootstrap.py` copies them verbatim, with no templating from issue bodies
  or external skill sources — so this does not open a new lower-trust input
  channel into what an unattended process can do.
- The `loop` stage remaps to `workflow`'s command file via `prompt_stage`;
  `_allowed_tools` is called with `prompt_stage`, so the actual Autonomous
  Mode entrypoint is covered identically to a directly-invoked stage
  (verified by a dedicated test).

Rejected alternatives:

- `--dangerously-skip-permissions` for `claude`: rejected. This would bypass
  every tool check, not just the ones each stage's frontmatter already
  declares — including anything a future stage or a compromised prompt might
  attempt — and would defeat the purpose of having per-stage scoping at all.
- Broadening `.claude/settings.json`/`settings.local.json` repo-wide:
  rejected. That would also relax the baseline for every interactive session,
  not only headless `dev` invocations, and would require maintaining one
  global list in sync with N per-stage frontmatter declarations instead of
  reusing the ones that already exist.
- Fail loudly instead of fixing the gap: rejected as the only fix. Failing
  loudly is a strict improvement in observability the issue also names, but
  it does not restore the ability to actually run stages unattended, which
  is the entire point of L2/L3 autonomy and Autonomous Mode.

### Consequences

- Positive: `dev refine`/`start`/`review`/`release`/`workflow`/`loop` can now
  actually execute the `gh`/`git`/memory-write calls their own command files
  already declare, unattended, closing #179. No change to interactive
  sessions or to the `agy`/`gemini` engine paths.
- Negative: this makes the pre-existing gap between the documented
  "permanently human-gated" invariant and `loop_policy.decide_stage`'s actual
  behavior at the default level operationally reachable via the primary
  engine path for the first time (previously only reachable via `agy`).
  Likewise, it makes the `Bash(gh:*)` wildcard in review/release frontmatter
  (which functionally covers `gh pr merge`/`gh release create`, backed today
  only by prose telling the agent not to) live for `claude` too, whereas
  before, headless `gh` calls of any kind silently blocked.
- Follow-ups: #183 (harden `decide_stage` so `HUMAN_GATED_STAGES` is enforced
  at every autonomy level, including the default), #184 (denylist
  `.claude/commands/*` and `.claude/settings*.json` from autonomous
  edits — nothing currently stops a Write/Edit-capable autonomous run from
  tampering with its own permission surface before it's read), #185 (narrow
  the `gh:*` wildcards in review/release frontmatter, and/or add a hard,
  unconditional deny on `gh pr merge`/`gh release create` regardless of lock
  ownership). None of these are fixed by this ADR's decision; they are
  scoped as separate, owned hardening work.

## More information

- Implementation: branch `bugfix/headless-stage-permission-bypass`, PR #181;
  `solomon_harness/workflows.py` (`_read_command_file`, `_allowed_tools`, the
  `--allowed-tools` wiring in `run_stage`), `tests/test_workflows.py`.
- Live-verified: headless `claude -p --allowed-tools "Bash(gh issue view:*)"`
  succeeds and returns real data; the identical call without the flag
  reproduces the exact reported symptom (blocks, asks for approval that never
  comes).
- Tracking issue: #179. Follow-ups: #183, #184, #185.
- This decision is also recorded in the project memory via `save_decision`.
