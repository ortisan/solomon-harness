# PLAN — isolated worktree + implementation-mode choice on /solomon-start

Delivers issues #8 (dedicated git worktree on start) and #23 (automatic vs manual
implementation mode) in one branch, #8 leading. Both edit the same start stage.

## Problem statement

- #8: `/solomon-start` switches the single checkout onto the new branch
  (`git switch -c`), which couples one branch to the working directory, blocks on a
  dirty tree, and prevents parallel in-flight issues.
- #23: the stage then falls straight into the agent-driven TDD loop, with no point
  where a human is asked whether the agent implements automatically or a developer
  implements by hand. The team still has hands-on developers.

## Proposed change and the boundary it touches

- New module `solomon_harness/worktree.py` — the single source of truth for the
  worktree contract (path computation, idempotent create/locate, conflict
  reporting). This is the real, unit-tested logic.
- New CLI subcommand `solomon-harness worktree <branch> [--base <ref>]` wrapping
  the module: prints the absolute worktree path to stdout and exits 0 on
  success/reuse; prints a diagnostic to stderr and exits non-zero on conflict.
- `.claude/commands/solomon-start.md`:
  - step 2 calls the worktree helper instead of `git switch -c`, and steps 3-6 run
    inside the worktree;
  - step 5 asks the implementation mode (Automatic / Manual / Other) before any
    code is written, with the manual-mode behavior and a deterministic
    non-interactive default (Automatic) for the headless path.
- `.gemini/commands/solomon-start.toml` regenerated from the source (never
  hand-edited); a drift check guards it.
- `docs/solomon-workflow.md` documents the sibling worktree-location convention and
  the two implementation modes.
- `docs/adr/0001-isolated-worktree-and-implementation-mode-on-start.md` records the
  cross-cutting decision (worktree layout + mode gate).

Boundary: the worktree contract is owned by `solomon_harness/worktree.py`; the
command file and the CLI are thin callers. The mode choice is prompt-level
(host tool is the LLM), verified by command-file/Gemini content assertions.

## Worktree-location convention (decided in refinement, #8)

`<PARENT>/<NAME>-worktrees/<branch with '/' replaced by '-'>` where
`NAME = basename(repo top-level)`, `PARENT = dirname(repo top-level)`. Sibling, not
in-repo, so recursive tooling never double-traverses a nested checkout.

## Target files

- `solomon_harness/worktree.py` (new)
- `tests/test_worktree.py` (new)
- `solomon_harness/cli.py` (add `worktree` subcommand)
- `.claude/commands/solomon-start.md` (steps 2 and 5)
- `.gemini/commands/solomon-start.toml` (regenerated)
- `tests/test_integrations.py` (assert start-command + Gemini mirror carry the
  worktree call, the mode prompt, and the non-interactive default line)
- `docs/solomon-workflow.md` (conventions + modes)
- `docs/adr/0001-*.md` (new)

## Edge cases as observable outcomes

- New branch + new worktree from base: `git worktree list` shows the computed path
  on the branch; helper prints the path; exit 0 (AC-8.1).
- Dirty main checkout: create still succeeds; main checkout's changes untouched
  (AC-8.2) — inherent to `git worktree add`, asserted by test.
- Idempotent reuse: path already a worktree on the expected branch -> no
  `git worktree add` runs; same path printed; exit 0 (AC-8.3).
- Conflict: path exists as a non-worktree dir, or the branch is checked out in
  another worktree -> raise, no partial worktree added, diagnostic to stderr,
  non-zero exit (AC-8.4).
- Mode prompt present before codegen; three options Automatic/Manual/Other;
  manual leaves the card In Progress and writes no code; headless prints
  "Implementation mode: Automatic (non-interactive default)" (AC #23).
- Gemini start command mirrors the same prompt + default line; drift check passes.

## TDD breakdown (one commit each, Red -> Green)

1. `test_worktree.py`: `worktree_path` computation + `ensure_worktree` happy /
   idempotent-reuse / conflict (path-occupied, branch-checked-out-elsewhere) on a
   temp git repo. Implement `solomon_harness/worktree.py`. (Refs #8)
2. `test_worktree.py`: CLI `worktree` subcommand contract (stdout path + exit 0;
   stderr + non-zero on conflict). Wire the subcommand in `cli.py`. (Refs #8)
3. `test_integrations.py`: start command step 2 invokes the worktree helper and
   the worktree-location convention is documented. Edit `solomon-start.md` step 2
   and `docs/solomon-workflow.md`. (Refs #8)
4. `test_integrations.py`: start command step 5 carries the Automatic/Manual/Other
   prompt, the manual-mode no-code/In-Progress behavior, and the exact
   non-interactive default line. Edit `solomon-start.md` step 5 and the doc.
   (Refs #23)
5. `test_integrations.py`: `.gemini/commands/solomon-start.toml` mirrors the
   worktree call, the mode prompt, and the default line. Regenerate via
   `scripts/generate-integrations.py`. (Refs #8 #23)
6. Write ADR-0001; assert it exists and is linked from the PR. (Refs #8 #23)

## STRIDE notes

- Tampering / Injection: branch names flow into `git worktree add` and into a
  filesystem path. Validate the branch (allow `[A-Za-z0-9._/-]`, reject `..` path
  segments and a leading `-`) before path construction or subprocess use; pass git
  args as a list (never `shell=True`). Reject a computed path that escapes the
  worktree root.
- Denial of service: `git worktree add` is bounded; idempotent reuse runs no add.
- No secrets, auth, or PII surface in this change.

## Verification criteria

- `python -m unittest tests.test_worktree tests.test_integrations tests.test_workflows`
  passes.
- `ruff check solomon_harness/worktree.py tests/test_worktree.py` clean.
- `git worktree list` shows a created worktree at the documented path; re-running
  the helper adds nothing; a conflicting path exits non-zero with a clear message.
- `solomon-start.md` and the regenerated `.toml` both contain the mode prompt and
  the exact non-interactive default line; the drift check passes.
