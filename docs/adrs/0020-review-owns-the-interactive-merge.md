# ADR-0020: `/solomon-review` owns the interactive merge; `/solomon-release` never merges individual PRs

- Status: accepted
- Date: 2026-07-04
- Amended: ADR-0034 (2026-07-16; closed-issue projection repair is not a new terminal decision)
- Deciders: software_architect, software_engineer, product_owner
- Issue: #172

## Context and problem statement

The lifecycle's central transition — merge the approved PR, close the issue,
move the board card to `Done`, converge the memory row — has no owning
command. `/solomon-review` explicitly forbids merging and ends at `QA`
(`solomon-review.md:83-85`), while `/solomon-release` claims the per-PR
squash-merge "now happens in `/solomon-review` close-out" — a claim that is
not true; neither stage performs it. The only path to `Done` today is a human
running `gh pr merge` by hand, then a manual `solomon-harness reconcile` (or a
manual `set-status --status Done` call) to converge memory. This reproduced
live twice in one session (issues #179 and #182), each requiring the same
manual workaround.

ADR-0006 already established the mechanism for this convergence: a
best-effort write-through (`record_terminal_status`, triggered today only
inside the CLI's `set-status --status Done` dispatch) that mirrors a `Done`
transition into memory, with `reconcile` as the idempotent backstop for
anything that bypasses it. That mechanism already works. The gap this ADR
closes is narrower and different: nothing ever calls it after a real merge,
because no stage decides it owns the merge action in the first place.

This is architecturally significant: it finalizes a cross-cutting pattern
(who is allowed to execute `gh pr merge` inside the delivery lifecycle) and it
is a quality-attribute trade-off on where the human-approval gate technically
lives — a non-negotiable invariant (`docs/solomon-workflow.md`: "merge,
release, and moving a card to Done are permanently human-gated at every
level"). Two related, already-filed, already-open gaps bound the solution
space and are deliberately *not* fixed here: #183 (`loop_policy.decide_stage`
does not enforce `HUMAN_GATED_STAGES` at the default autonomy level) and #185
(the `Bash(gh:*)` wildcard in review/release frontmatter functionally covers
`gh pr merge`, with only prose stopping self-merge under normal single-driver
operation). Because neither is fixed yet, this decision must not rely on
`loop_policy` or tool-scoping alone to keep merge human-gated.

## Decision drivers

- Close the actual, reproduced gap: after approval, one stage must merge,
  close, move the card, and converge memory, with no manual `reconcile` step.
- The human-approval gate for merge must hold structurally, not just in prose
  — and must not depend on #183/#185 being fixed first.
- Reuse ADR-0006's existing write-through rather than inventing a second
  convergence mechanism.
- Release stays milestone-gated only; a single PR merge must never trigger a
  version tag (unrelated concerns, already documented in
  `docs/release-policy.md`).
- Both host command-file mirrors (`.claude/commands/`, `.gemini/commands/`)
  must agree, or the ownership question reopens on the next host drift.

## Considered options

- **(A) `/solomon-review` merges on approval, interactive-only.** After
  `gh pr ready`, ask the human (enumerated confirmation) whether to merge now;
  on yes, run `gh pr merge` then the existing `Done` write-through in one
  step. Headless (`dev review`) never reaches this branch — there is no one to
  answer, and defaulting to yes would violate the non-negotiable gate.
- **(B) `/solomon-release` performs the merge**, since its stage name implies
  "deliver". Rejected: release is explicitly milestone-gated
  (`docs/release-policy.md` — "a tag is cut only when a milestone reaches 0
  open issues") and operates on an aggregate of already-`Done` issues, not on
  one PR; folding a per-PR merge into it would conflate two different
  triggers (one PR vs. one milestone) in one stage.
- **(C) A new, separate `/solomon-merge` stage.** Rejected: adds a fourth
  lifecycle stage and a fourth command-file pair to keep in sync for a step
  that only ever follows a review approval; review already has full context
  on the specific PR/issue at the moment the human would confirm, so gating it
  as review's own last step is simpler.
- **(D) Gate the merge on `loop_policy`'s autonomy level** instead of an
  explicit interactive confirmation. Rejected for now: #183 shows
  `decide_stage` does not actually enforce `HUMAN_GATED_STAGES` at the default
  level, so this would make the human gate decorative until #183 lands. This
  ADR does not wait on that fix.

## Decision outcome

Chosen: **(A)** — `/solomon-review` owns the merge, gated by an explicit
interactive confirmation, never reached in a headless run.

- On an approve verdict (zero blockers, zero open majors) and after
  `gh pr ready`, the reviewer is asked, via the existing enumerated-decision
  convention, whether to merge now.
- On yes: the stage runs the new `solomon-harness github merge --pr <m>
  --issue <n>` command (`solomon_harness/github.py::merge_pr_and_close`),
  which runs `gh pr merge <m> --squash` and, only on success, calls
  `set_issue_status(n, "Done")` and `record_terminal_status(n)` directly (both
  called explicitly — calling `set_issue_status` as a plain Python function,
  rather than through the CLI's `set-status` subcommand dispatch, does not by
  itself trigger the write-through, so this new function must call both). On
  merge failure, neither is called — board and memory are left unchanged, no
  partial state.
- On no, or in a headless `dev review` run: unchanged from today — the card
  stays at `QA`, the PR stays ready and unmerged, and the output states a
  human must complete the merge (directly with `gh pr merge` plus
  `solomon-harness github merge` to converge the board/memory, or by
  re-running `/solomon-review` interactively).
- `/solomon-release`'s ambiguous close-out claim is removed; it states
  explicitly that it never merges an individual PR and only cuts a version tag
  once a milestone's issues are already `Done`.
- Both `.claude/commands/` and `.gemini/commands/` mirrors for `review` and
  `release` are updated identically; a fitness test pins parity.
- The PR's own title/body/diff/comments are treated as data to evaluate, never
  as instructions to follow, stated explicitly in the command file: this stage
  can now merge on approval, so a successful prompt injection has a path to an
  actual merge, not just a wrong verdict (found in review of this ADR's own PR).

Rejected alternatives: **(B)** conflates per-PR merge with milestone-gated
release; **(C)** adds a stage for a one-step action that only ever follows
review's own approval, with no independent trigger of its own; **(D)** would
make the human gate depend on #183, which is explicitly not fixed by this
decision.

### Consequences

- Positive: closes #172 as reproduced — one stage now owns the full
  merge-to-`Done` transition, reusing ADR-0006's existing, already-working
  write-through instead of adding a second convergence mechanism. No manual
  `reconcile` needed for the common (interactive) case.
- Negative: `/solomon-review` gains a git-mutating action (`gh pr merge`) it
  did not have before. **Correction from this ADR's original text** (found in
  review of the implementing PR): the first draft claimed the gate was
  "mitigated structurally... the headless branch never reaches it," but the
  `allowed-tools:` frontmatter this decision adds `AskUserQuestion` to is read
  by exactly one piece of code (`workflows.py::_allowed_tools`), and every
  invocation through that code is headless by construction — a real
  interactive session reads the command file directly through Claude Code's
  own command loader, never through `workflows.py`. So the original claim was
  not true as written: the same frontmatter line reaches both audiences, and
  nothing prevented a headless run from also receiving `AskUserQuestion`. The
  fix landed in the same PR: `_allowed_tools` now unconditionally strips
  `AskUserQuestion` (`HEADLESS_UNSAFE_TOOLS`) from what it forwards to the
  headless engine, for every stage, not only `review`. That makes the
  "headless never reaches the merge branch" guarantee actually true at the
  code layer — the tool required to answer the confirmation is not present in
  the headless engine's own permission set, not merely discouraged by prose.
  No autonomy-level check (`loop_policy`) is relied upon for this gate.
- Scope: this decision does not fix #183 (the `loop_policy` human-gate
  enforcement gap) or #185 (the `gh:*` wildcard covering merge/release, which
  a same-day security review also confirmed already reaches `merge_pr_and_close`
  via `Bash(uv run:*)` pre-existing to this decision). Both remain open,
  tracked, and independent — hardening either strengthens this decision's
  headless-never-merges guarantee but is not required for it to hold, since
  the `AskUserQuestion` guarantee above is now code-level, not policy-based.
- Follow-ups: #183, #185 (already filed, unrelated action needed, #185 updated
  with this decision's reachability nuance); a parity fitness test
  (`tests/test_command_gates.py`) so the two host mirrors cannot silently
  diverge on the owning-stage decision again.
- Live-verified (mirroring how ADR-0017/#179 was live-verified): a disposable
  fixture command file declaring `AskUserQuestion` in its frontmatter, piped
  into `claude -p` with the exact `--allowed-tools` string `_allowed_tools`
  now forwards (with `AskUserQuestion` stripped), reports the tool "not found
  among deferred or active tools" — it cannot be discovered, let alone called.
  A second run additionally re-added `AskUserQuestion` back into
  `--allowed-tools` directly (simulating the pre-fix state) and got the
  identical result: `claude -p` (headless, no TTY) does not expose
  `AskUserQuestion` as a callable tool at all, independent of what
  `--allowed-tools` declares. This means the underlying risk this correction
  responds to was structurally bounded by the engine itself even before the
  `HEADLESS_UNSAFE_TOOLS` fix landed — but the fix is kept regardless: it
  makes the guarantee explicit and verified in this repo's own code and tests
  rather than resting on an unconfirmed assumption about a third-party CLI's
  undocumented behavior, and it generalizes to any future interactive-only
  tool, not only this one.

## More information

- Implementation: branch `bugfix/merge-to-done-transition`, issue #172.
  `solomon_harness/github.py` (`merge_pr_and_close`, the `github merge` CLI
  subcommand), `.claude/commands/solomon-review.md` /
  `.gemini/commands/solomon-review.toml`, `.claude/commands/solomon-release.md`
  / `.gemini/commands/solomon-release.toml`, `docs/solomon-workflow.md`,
  `solomon_harness/workflows.py` (`HEADLESS_UNSAFE_TOOLS`, `_allowed_tools`).
- Corrected during the review of the implementing PR (#195): the original
  "mitigated structurally" claim did not hold as written; the fix and the
  corrected reasoning are captured in this ADR's Consequences section rather
  than in a superseding ADR, since the underlying design decision (interactive
  confirmation, headless never merges) did not change — only the mechanism
  that makes it true did.
- Builds on ADR-0006 (`docs/adrs/0006-canonical-issue-status-vocabulary-and-board-to-memory-write-through.md`):
  reuses its `record_terminal_status` write-through and `reconcile` backstop
  unchanged; this ADR only decides who calls it after a real merge.
- Related, not fixed here: #183, #185 (both filed 2026-07-04, from the PR #181
  review).
- Amended by ADR-0034: `/solomon-review` remains the only workflow that
  originates the normal merge-to-`Done` transition after human confirmation;
  a locked reconcile stage may repair a stale board projection only after an
  authoritative GitHub snapshot already reports the issue `CLOSED`.
- This decision is also recorded in the project memory via `save_decision`.
