# ADR-0001: Isolated worktree and implementation-mode choice on /solomon-start

- Status: accepted
- Date: 2026-06-28
- Deciders: product_owner, software_architect, software_engineer
- Issue: #8, #23

## Context and problem statement

`/solomon-start` is the entry point for implementing every issue, so how it sets up
work is a cross-cutting pattern for the whole lifecycle. Two properties were missing.
First, it switched the single working checkout onto the new branch (`git switch -c`),
coupling one branch to the working directory: a dirty tree blocked the start and only
one issue could be in flight at a time. Second, it assumed the agent writes the code,
with no point at which a human could choose to implement by hand — yet the team still
has hands-on developers. Both concerns change the start stage's execution model, so
they are decided together.

## Decision drivers

- Parallelism: several issues must be able to be in flight without one start disturbing
  another or the primary checkout.
- Non-destructiveness: a start must never mutate or block on the primary checkout's state.
- Tooling hygiene: the isolated working directory must not be double-traversed by
  recursive tools (test collection, IDE indexers).
- Human agency: a developer must be able to keep a manual workflow while still using the
  harness for setup, review, and release.
- Determinism in CI: the headless path must never block on an interactive prompt.

## Considered options

- Worktree location: a sibling root `<parent>/<repo>-worktrees/<branch>` vs. an in-repo
  `.solomon/worktrees/<branch>`.
- Implementation control: always-automatic (status quo) vs. an explicit per-start choice
  between automatic and manual.
- Headless mode handling: a `--mode` CLI flag vs. a deterministic prompt-level default.

## Decision outcome

Chosen: create each issue's branch in its own git worktree at the **sibling** path
`<parent>/<repo>-worktrees/<branch with '/' as '-'>`, and add an **implementation-mode
choice** (Automatic / Manual / Other) at the head of the implementation step, defaulting
to Automatic deterministically when non-interactive.

The sibling layout best satisfies tooling hygiene: an in-repo worktree, even when
gitignored, is double-traversed by tools that ignore `.gitignore`. The explicit mode
choice satisfies human agency without removing the automatic default. A prompt-level
default (rather than a `--mode` flag) keeps the headless path deterministic with no new
CLI surface; a flag remains a contingency if that proves insufficient.

### Consequences

- Positive: starts no longer disturb the primary checkout; multiple issues can be in
  flight; hands-on developers are first-class; CI cannot hang on the mode prompt.
- Negative: each worktree consumes roughly one working tree of disk; the convention adds
  a sibling directory beside the repo.
- Follow-ups: automatic worktree removal on merge/release is out of scope (manual
  `git worktree remove` for now) and should become its own issue.

## More information

Implemented by `solomon_harness/worktree.py` and the `solomon-harness worktree`
subcommand, wired into `.claude/commands/solomon-start.md` (steps 2 and 5) and mirrored to
the Gemini command. Convention documented in `docs/solomon-workflow.md`. Recorded in the
project memory via `save_decision`.
