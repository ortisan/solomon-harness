# ADR-0012: Interactive-only capability ladder (automate -> guide -> degrade) for the GitHub wiki bootstrap

- Status: accepted
- Date: 2026-06-29
- Deciders: software_architect, product_owner, software_engineer
- Issue: #117

## Context and problem statement

The GitHub wiki is one of the harness's headline features: living docs
(`Code-Overview.md` and `Delivered.md`) published by the wiki step during the
`/solomon-release` close-out. GitHub creates a repository's `.wiki.git` content
repo only after the first wiki page is saved through its web UI, and it exposes
no REST, GraphQL, or `gh` path to create that first page. On any repo whose wiki
was never opened the wiki step therefore fails opaquely, surfacing a raw remote
error instead of an actionable instruction. A core feature looks broken out of
the box.

This forces an architecturally significant question that outlives the wiki: a
delivery workflow needs a capability whose only entry point is an uncontrolled,
interactive web UI, while that same workflow must remain safe in the headless and
CI contexts where no browser and no human exist. We must decide whether the
harness may take on driving that UI at all, and on what terms, without making any
delivery step depend on a browser being present.

## Decision drivers

- End the opaque failure: the wiki step must always terminate in an actionable
  outcome, never a raw clone or push error.
- Headless and CI safety: the step runs during `/solomon-release`, which often
  runs headless. It must degrade deterministically with no browser, no prompt,
  and no hang.
- Bound any new dependency: an uncontrolled external web UI may be admitted only
  as an optional, best-effort tier, never as load-bearing infrastructure.
- Robustness to vendor drift: because the UI is outside our control, success must
  be verifiable from observable system state, not from trusting the page.
- Idempotency: the capability must never act when the target already exists.
- Reusability: the shape chosen should generalize to other interactive-only
  capabilities and stay consistent with the existing headless and loop-safety
  posture, rather than being a one-off for the wiki.

## Considered options

- **A. Guide-only / manual.** Detect the uninitialized state and print the manual
  step; never automate. Rejected: it leaves the opaque failure replaced by a chore
  for the common interactive case, where the harness could have completed the work
  but chooses not to. It under-uses an available capability.
- **B. The interactive capability ladder (chosen): automate -> guide -> degrade.**
  Try a best-effort browser automation at the top, fall back to a guided manual
  step when interactive but unable to automate, and degrade to a deterministic,
  actionable non-zero exit in headless/CI or when the guide is declined.
- **C. Block init and release until the wiki exists.** Make the wiki a hard
  precondition of the delivery workflow. Rejected: it breaks headless and CI runs
  and `solomon-harness init` (which commonly runs non-interactive) by making them
  fail on a state they cannot remediate without a human at a browser. It converts
  an optional capability into a release-blocking dependency.

## Decision outcome

Chosen: **Option B — adopt the automate -> guide -> degrade ladder, with the
headless/CI degrade as the non-negotiable floor.** It is the only option that ends
the opaque failure (driver 1) while keeping the delivery workflow safe where no
browser or human exists (driver 2), and it does so as a reusable pattern rather
than a wiki-specific hack (driver 6).

Two things are decided.

### 1. A bounded new dependency class is admitted

Harness delivery workflows MAY drive an uncontrolled external web UI (GitHub's
`<repo>/wiki/_new`) through the claude-in-chrome MCP browser agent against an
already-authenticated interactive session. This is admitted only as the
best-effort, optional top tier of the ladder. It is never load-bearing: no
delivery step's success may depend on it. The cost of admitting it is stated
plainly and accepted: brittleness to vendor HTML and flow changes; reliance on an
interactive, externally authenticated session that does not exist headless; and a
new external-dependency class that the team now has to maintain and monitor.

### 2. The ladder is the standing pattern for interactive-only capabilities

The automate -> guide -> degrade ladder is adopted as the standing pattern for any
capability whose only entry point is interactive, not just the wiki. The
headless/CI degrade is the non-negotiable floor of that pattern: when there is no
TTY, no browser, or the guide is declined, the capability must end in a
deterministic non-zero exit and an actionable message that names the cause and the
exact `<repo>/wiki/_new` remediation step, bounded by a short (~10s) detection so
the step cannot hang, surfacing no raw clone/push stderr and no secrets. This
extends the harness's existing headless and loop-safety posture from "who may
drive" to "what a capability may assume about its runtime."

### Design contract

The robustness and verification stance is a contract on every tier, not a third
standalone decision:

- **Detection is the gate.** The wiki step proceeds only when an observable check
  of system state, `git ls-remote --heads <wiki-url>` bounded by a ~10s timeout,
  reports at least one ref. Detection state, not UI state, drives the ladder.
- **Success is asserted by observable state.** The top tier is judged to have
  succeeded only by re-running that same detection and seeing a ref appear, never
  by trusting the browser's return value or the page DOM. A changed or tampered
  page cannot report a false success.
- **Idempotent.** When refs already exist, no bootstrap is attempted; the step is
  a pure no-op against the wiki remote.
- **Detect-and-hint at init.** `solomon-harness init` only detects the
  uninitialized state and hints; it never bootstraps, because init commonly runs
  non-interactive.

### Relationship to prior decisions

- **ADR-0004 (milestone-gated releases).** The wiki step runs during the
  `/solomon-release` close-out, the same workflow ADR-0004 governs. The degrade
  floor is the same fail-closed, headless-safe stance ADR-0004 takes for the
  library-readiness gate and the headless-safe `release plan`: a step that may run
  unattended must terminate deterministically and safely without a human in the
  loop.
- **ADR-0001 (loop single-driver lock / autonomy ladder).** The interactive
  versus headless axis this ADR formalizes is the same axis loop-safety governs.
  ADR-0001 decides who may drive a mutating stage; this ADR decides what an
  interactive-only capability may assume about its runtime, and mandates a safe
  degrade when those assumptions do not hold. They are consistent halves of one
  posture.

### Consequences

- Positive: the opaque wiki failure is replaced by either a completed bootstrap or
  a clear, actionable instruction, so a headline feature works out of the box or
  tells the operator exactly what to do. The delivery workflow stays safe headless
  and in CI because the degrade floor is mandatory and browser-free. The verify-by-
  observable-state contract makes the top tier robust to vendor UI drift: it cannot
  silently claim a success that did not happen. The pattern is reusable, so the next
  interactive-only capability inherits a vetted shape instead of reinventing one.
- Negative: the harness now owns a new external-dependency class (an uncontrolled
  web UI driven through a browser agent) that is brittle to GitHub markup and flow
  changes and depends on an externally authenticated interactive session; it needs
  maintenance and a maintenance issue when the flow breaks. The ladder is more
  moving parts than a single manual hint, and its top tier is exercised only
  interactively, so its happy path cannot be fully covered by headless tests and
  must be proven manually.
- Numbering note: this record was renumbered from 0007 to 0012 after the multi-model
  memory work (#119) merged its ADR renumber to `main`, which took 0007 for
  `0007-memory-resilience-model.md`. 0012 is the next free number (main occupies
  0000-0011). The `save_decision` record is updated to match.
- Follow-ups: prove the top-tier browser save manually against
  ortisan/solomon-harness and republish the v0.8.0 Code-Overview and Delivered.md
  as the end-to-end acceptance proof (issue #117, I-1); if GitHub ever exposes a
  first-page API the browser tier becomes obsolete and should be retired in favor
  of that API while keeping the degrade floor.

## More information

- Issue: #117 (milestone wiki-publish, #9). PLAN.md on the feature branch.
- Related ADRs: ADR-0004 (milestone-gated releases, the workflow this step runs
  in), ADR-0001 (loop single-driver lock, the interactive-vs-headless axis).
- This decision is also recorded in the project memory via `save_decision`.
