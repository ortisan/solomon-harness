---
name: roadmapping-and-release-planning
description: Governs building an outcome-based now/next/later roadmap, slicing releases into thin vertical increments, and planning milestone-driven releases where a tag is cut only when a milestone reaches zero open issues, forecast by Monte Carlo. Use when structuring a roadmap or a release plan.
---

# Roadmapping and Release Planning

Build a roadmap that commits to outcomes and problems, not to a dated list of features, and a release plan that ships value in thin vertical slices grouped into milestones. Treat the roadmap as a statement of intent under uncertainty: it tells stakeholders what problems you will attack and roughly when, while leaving the team free to discover the cheapest solution. Dates are forecasts with a confidence interval, never promises pulled from a Gantt chart. Releases themselves are milestone-driven: a tag is cut when a GitHub milestone reaches zero open issues with CI green on `main`, not on a calendar and not per merge, so "when will it ship" is a forecast of milestone burndown.

## Outcome-based roadmaps (now/next/later)

A roadmap is organized by outcome, not by output. Each item names a measurable change in user or business behavior (activation rate, time-to-first-value, churn, revenue per account) and the problem behind it, so the team owns the "how" and can swap solutions without renegotiating the roadmap.

- Structure with **now / next / later** horizons (popularized by ProductPlan and the GV/Roman Pichler school), not calendar quarters. "Now" is in-build and high-confidence; "next" is the validated queue; "later" is directional and deliberately vague. Confidence and detail decay as you move right; do not pretend "later" is estimable.
- Group work into a hierarchy: **theme** (a strategic bet, e.g. "reduce onboarding friction") -> **epic** (a shippable body of work serving the theme) -> **story** (an INVEST-sized increment, owned by `user_stories_invest`). A theme lives for one or more quarters; an epic for weeks; a story for days.
- Attach a target metric and a baseline to every theme. "Improve onboarding" is not a roadmap item; "raise day-7 activation from 38% to 50%" is. Without a baseline you cannot tell when the theme is done or whether it worked.
- Keep the roadmap to a single page per audience. The executive view shows themes and outcomes; the delivery view shows epics and rough sequencing. They are projections of the same data, not separate documents that drift.
- Record the strategic bet behind each theme with `save_decision` (the hypothesis, the metric, the alternatives rejected) so a later reader sees why it was prioritized, and re-link the theme to the epics that serve it.

A minimal delivery view:

```text
NOW (in build, high confidence)
  Theme: Reduce onboarding friction  -> day-7 activation 38% -> 50%
    Epic: One-tap social sign-in            (slices 1-3, in sprint)
    Epic: Skippable setup wizard            (slice 1 demoed, rest queued)
NEXT (validated, sequenced)
  Theme: Recover abandoning users    -> trial->paid 12% -> 18%
    Epic: Re-engagement email on day 3
LATER (directional, not estimated)
  Theme: Self-serve team plans       -> expansion revenue (baseline TBD)
```

Read the horizons as confidence bands, not a queue you promise to clear. The "now" theme has a hard baseline and target because it is funded and in build; the "later" theme deliberately carries "baseline TBD" because committing a number to it would be precision you do not have. When a "next" theme's riskiest assumption is validated and an epic is sliced and Ready, it earns promotion to "now"; nothing moves left on opinion.

## Prioritization: MoSCoW and where it fits

MoSCoW (Must / Should / Could / Won't) scopes a single release — here, a single milestone; it answers "what is in this milestone" once you already know relative value. Use a scoring method to rank the backlog, then MoSCoW to draw the line for a specific milestone.

- **Must**: the milestone fails to meet its goal without it. If everything is a Must, you have not prioritized. Cap Musts at roughly 60% of milestone capacity (DSDM guidance) so the plan has slack to absorb estimation error.
- **Should**: important but the milestone still delivers value if it slips. **Could**: desirable, the first to drop under pressure, your contingency buffer. **Won't (this time)**: explicitly out of scope for this milestone, recorded so it is a decision and not an oversight; feed it into `scope_boundaries`.
- MoSCoW ranks within a milestone. For ranking the whole backlog, use a quantified method from `prioritization` (RICE, WSJF) and show the numbers; MoSCoW alone has no value model and degrades into opinion.
- Re-apply MoSCoW each milestone, not once. A Could that keeps slipping is signaling that its parent theme is mis-ranked; escalate it, do not silently carry it forward.

## Slicing into thin vertical increments

A release is a sequence of the smallest changes that each deliver observable user value end to end. Slice vertically (a complete capability through every layer) rather than horizontally (a whole layer with no user-facing behavior).

- Each slice must cross the full stack: UI, logic, persistence, and an observable outcome. "Build the database schema" is a horizontal slice that ships nothing; "a user saves one draft and reloads it" is vertical and demoable.
- Apply SPIDR (Spike, Path, Interface, Data, Rules) or the story-splitting patterns when an epic is too big: split by workflow step, by happy-path-then-edge-cases, by data variation, or by business rule. The first slice is usually the thin happy path with everything else deferred.
- Target a slice that fits inside one sprint with margin; if it cannot be demoed at the review, it is too big. Vertical slices keep `acceptance_criteria_given_when_then` testable and let QA verify behavior each iteration instead of at the end.
- Sequence slices to retire the biggest risk or unlock the biggest learning first (walking-skeleton first), not the easiest work first. The earliest slices should validate the theme's hypothesis cheaply.
- The team owns story-level decomposition during refinement; you own that each slice maps to a roadmap epic and carries its outcome. Hand the sliced, Ready set to `scrum_master` for sprint planning; the release milestone is opened and filled by `/solomon-refine` (see the milestone section below).

Worked slicing example, the "One-tap social sign-in" epic above:

```text
Epic: One-tap social sign-in  (serves: reduce onboarding friction)
  Slice 1  Google sign-in, happy path only, account auto-created
           -> demoable, retires the OAuth integration risk first (walking skeleton)
  Slice 2  Link social identity to an existing email account (account-merge rule)
  Slice 3  Apple sign-in + error/edge handling (revoked token, declined scope)
  Deferred Enterprise SSO  -> not in this train; recorded as "Won't this time"
```

Slice 1 ships value and kills the integration risk on day one; slices 2 and 3 add data variation and business rules; the enterprise case is an explicit MoSCoW "Won't this time" fed to `scope_boundaries`, not a silent omission.

## Flowing roadmap items through the /solomon-* board

Roadmap items do not live only in a planning document; they move through the project board columns **Ideas -> Backlog -> Ready -> In Progress -> Code Review -> QA -> Done**, and each column maps to a horizon and a workflow step. Follow the project lifecycle and use the project tooling rather than ad hoc notes, so the next agent inherits the context and the rationale.

- **Ideas** holds discovery items and "later" themes: a JTBD, an opportunity, and a riskiest assumption (captured with `solomon-idea`). These are not commitments and carry no baseline yet; they correspond to the directional right edge of the roadmap.
- **Backlog** holds validated opportunities promoted from Ideas once their riskiest assumption passed (see product_discovery_and_jtbd). This is roadmap "next": create the structured issue with `solomon-issue` (INVEST + Given/When/Then), carrying the target outcome and baseline, not just a feature title. Do not open a milestone yet — release scope is created by `/solomon-refine` when the first child reaches Ready (see the milestone section below), so milestones never sit empty at capture time.
- **Ready** is the refined, sliced set (`solomon-refine`): each item is a thin vertical slice with sharp acceptance criteria, an estimate, and a Definition of Ready, and is assigned to exactly one release milestone (its epic's `vX.Y.0` milestone, or a theme milestone). A "next" epic only crosses into roadmap "now" once at least its first slice is Ready.
- **In Progress** is roadmap "now" in build (`solomon-start`): the PLAN.md for any change references the PRD's in-scope list, target files, edge cases, and the verification criteria you defined, so delivery traces back to the validated bet.
- **Code Review -> QA** are the verification gates (`solomon-review`): quality, specification compliance, and acceptance-criteria checks before a slice is callable done.
- **Done** is a slice merged with its acceptance criteria met and its issue closed, burning its milestone down by one (`solomon-review` -> `solomon-release`). A merged slice is not yet a release: the tag is cut only when the slice's milestone hits zero open issues with CI green. The real signal that the bet paid off is the theme's *outcome metric moving*, observed after the milestone ships — distinct from any single merge.
- Persist the decisions that shape this flow in project memory: `save_decision` for scope and prioritization calls (which Must/Should/Could, which theme funded), `log_issue` for gaps and risks that surface mid-flow, and `log_handoff` when an item crosses a column so the receiving specialist inherits the evidence. This is the same memory trail the roadmap forecasts depend on.

## The milestone is the release-scope object

In solomon-harness a release is not a calendar event and not a per-PR push; it is a GitHub **milestone reaching zero open issues with CI green on `main`**. The milestone is the unit scope is planned against and the unit a tag is cut from. Every issue — epic child, story, bug, or chore — rolls up to **exactly one** milestone; an issue with no milestone is invisible to release scope and is a planning defect to fix, not tolerate.

There are two kinds of milestone, and the kind determines the SemVer bump:

- **Epic milestone** — titled with its SemVer minor (`v0.4.0`, `v0.5.0`); the title *is* the version. It groups the stories that complete one shippable epic. When it hits zero open issues with CI green, the **MINOR** is cut. You name it for the next minor when you refine the epic; that number is a planning declaration that `release check` later confirms against the commit history.
- **Theme / hardening milestone** — titled by theme (`memory-durability`, `test-ci-hardening`, `worktree-lifecycle`), not by version, because several may batch into one patch. It collects parentless bugs, chores, and cross-cutting hardening. When it closes, a **PATCH** is cut whose version is **computed at cut time**, not chosen in advance.

Who creates and fills a milestone:

- **`/solomon-refine` creates the milestone and assigns its children.** It opens the milestone when it refines an epic's first child (titling it with the target minor `vX.Y.0`) or the first issue of a theme (titling it by theme), then assigns every Ready child to it. You do not pre-create empty milestones at capture time; scope accretes as items reach Ready.
- A parentless bug or chore is routed to the nearest open theme milestone, so nothing ships untracked.
- A single PR merge **closes its issue and burns the milestone down by one** — it does not cut a release. The release is the milestone hitting zero, gated by CI green and a human merging the ephemeral `chore/release-vX.Y.Z` prep PR; the on-demand escape valve is `solomon-harness release prep`, which can cut a PATCH for an accumulated batch without waiting for a milestone to fully close.

MoSCoW (above) draws the line for a single milestone: Musts must close before the milestone can; Coulds are the first issues dropped from the milestone under pressure; "Won't this time" is excluded from this milestone's scope and recorded in `scope_boundaries`.

### Versioning is computed, not chosen in planning

State this so planning never argues over version numbers:

- The bump is **SemVer derived from Conventional Commits** in `git log <last-tag>..main --first-parent` (highest wins), computed at cut time. Pre-1.0, a window containing any `feat` or a BREAKING CHANGE cuts a MINOR; a window with only `fix`/`perf`/`refactor`/`revert` cuts a PATCH; a window of only `chore`/`docs`/`ci`/`test` is non-releasable. You do not pick the bump in a planning meeting.
- The only version a planner writes is the **epic milestone's title** (`vX.Y.0`), which declares the intended minor; a theme milestone's patch version is computed when it closes (which is why theme milestones are not version-titled — several may batch). Planners and humans never hand-edit `pyproject.version` or add a CHANGELOG heading: `solomon-harness release prep` writes both, and `release check` fails closed on any drift between the tag, `pyproject.version`, and the top CHANGELOG heading.
- A published tag is immutable and never moved; a bad release is superseded by the next PATCH (a forward revert PR), never by re-tagging.
- This skill governs how scope is planned into milestones. The mechanics of turning a closed milestone into a tag — `release plan` / `prep` / `check`, the CI tag-and-publish owner, and the library readiness gate — live in `docs/release-policy.md`; defer to it for the procedure.

## Release cadence: milestone-driven, not a train and not per-PR

The two textbook cadence models are worth knowing, but solomon-harness uses neither in pure form. State the distinction so "when will it ship" has a consistent meaning.

- **Release train**: fixed-cadence, date-driven releases (e.g. every two weeks or, in SAFe, a Program Increment of 8-12 weeks). The train leaves on schedule; unfinished work waits for the next one. Scope flexes, the date does not. Useful when many teams or external partners must synchronize, or when downstream (marketing, app-store review) needs a predictable window. solomon-harness does **not** run a train: there is no fixed release date and no calendar cut.
- **Continuous delivery**: each increment ships when it passes the pipeline; there is no release event. Useful when one team owns the surface and can release independently. solomon-harness does **not** release per-PR either: a merge to `main` closes an issue and burns its milestone down, but a slice going green is not a release.
- **What solomon-harness actually does** is event-driven and trunk-based: slices squash-merge into `main` (no `develop`, no long-lived `release/*` or `hotfix/*` branch), and a tag is cut when a *milestone* closes — epic milestone -> MINOR, theme milestone -> PATCH — or on demand via `solomon-harness release prep`. The cadence is set by milestone burndown, not by a clock and not by each merge.
- The roadmap stays cadence-agnostic, but the release plan is milestone-shaped: show which themes and epics map to which milestone, and read "when will it ship" as "when will this milestone hit zero open issues," which the throughput forecast below predicts. There is no separate "feature-complete vs generally available" gap to manage here — this is a tag-released library with no running service and no flags; the slice is released when its milestone's tag is cut.

## Probabilistic plans, not fixed dates

Commit to a confidence range, never a single date you cannot defend. Forecasts come from measured throughput, not from summing optimistic estimates, and they predict when a milestone reaches zero open issues — the release event — not a calendar day.

- Forecast with **Monte Carlo simulation** over historical throughput (stories completed per week) rather than story-point summation. Run 5,000+ trials against the milestone's remaining open issues and report a distribution: "milestone `v0.4.0` 85% likely closed by week 9, 50% by week 7." Tools: Actionable Agile, the Nave/FlowViz simulators, or a short script over the team's cycle-time history. A bare-bones simulation samples past weekly throughput to drain the milestone:

```python
import random
def weeks_to_finish(backlog, history, trials=10000):
    results = []
    for _ in range(trials):
        remaining, weeks = backlog, 0
        while remaining > 0:
            remaining -= random.choice(history)  # sample an observed week
            weeks += 1
        results.append(weeks)
    results.sort()
    return {"p50": results[trials // 2], "p85": results[int(trials * 0.85)]}
# weeks_to_finish(backlog=40, history=[6, 4, 7, 5, 3, 8, 5]) -> e.g. {"p50": 8, "p85": 9}
```
- Quote forecasts at named confidence levels. Plan internal commitments at P85; never communicate the P50 (the coin-flip date) as a deadline. If a hard external date exists, flex scope (MoSCoW Coulds drop from the milestone first), not quality or the date.
- Track empirical flow metrics and let them drive the forecast: throughput, cycle time, work-in-progress, and aging work items. A rising cycle time or aging item invalidates the current forecast; re-run it rather than reassuring stakeholders from the old number.
- Re-forecast every iteration and publish the change with its cause. Persist each forecast snapshot with `save_memory` and the decision to re-scope or hold the milestone with `save_decision`, so the trail of "what we believed and when" survives. When a forecast crosses a threshold that endangers a milestone, raise it with `log_issue` and hand the context to the next stage with `log_handoff`.
- Reflect dates on the roadmap as ranges or horizons (now/next/later, or "milestone `v0.4.0` targeting Q3, P70"), never as a single pinned day, and never in the "later" column. Precision you do not have is a lie stakeholders will hold you to.

## Common pitfalls

- A feature-list roadmap with no outcomes or baselines: every item is an output, so you can never tell whether shipping it worked. Reject; demand a metric and baseline per theme.
- Dated quarters treated as commitments. A roadmap that promises specific features on specific dates beyond "now" is fiction; it must degrade to ranges and horizons as confidence drops.
- Promising a fixed calendar release date as if there were a train: this project has no train. Release timing is milestone burndown, forecast as a range, not a pinned day.
- Treating a single PR merge as a release, or hand-cutting a tag per merge: a merge only closes its issue and burns the milestone down; the release is the milestone hitting zero open issues with CI green, then the human merge of the `chore/release-*` prep PR.
- An issue with no milestone, sitting outside all release scope: every issue rolls up to exactly one milestone (its epic's `vX.Y.0`, or a theme milestone). Route parentless bugs and chores to the nearest theme milestone.
- Hand-picking a version number, or hand-editing `pyproject.version` or the CHANGELOG during planning: the bump is SemVer computed from Conventional Commits at cut time; the only version planning writes is the epic milestone's `vX.Y.0` title. Mechanics live in `docs/release-policy.md`.
- Everything marked Must in MoSCoW. That is the absence of prioritization; cap Musts near 60% of milestone capacity and force real Should/Could/Won't splits.
- Horizontal slices ("build the API", "build the schema") presented as roadmap increments. They ship no user value and hide integration risk to the end. Require vertical, demoable slices.
- A single forecast date with no confidence level, derived from summed estimates instead of measured throughput. Reject; require a Monte Carlo range, over the milestone's open issues, at a stated percentile.
- Communicating the P50 as the deadline, then treating the inevitable slip as a failure. Commit at P85 and flex scope.
- A "Won't this time" item that quietly reappears in a milestone without a recorded decision, eroding the scope boundary.
- A roadmap item that lives only in a slide and never enters the board, so its state is invisible to delivery. Every funded theme must have epics and stories tracked through Ideas -> Backlog -> ... -> Done, each rolled up to a milestone, with decisions in project memory.
- Slices sequenced easiest-first, leaving the theme's core hypothesis untested until late. Sequence by risk and learning.

## Definition of done

- [ ] The roadmap is organized by outcome with now/next/later horizons; every theme has a target metric and a baseline, and detail decays toward "later".
- [ ] Work is structured theme -> epic -> story, and each epic links to the theme outcome it serves.
- [ ] Release scope is set with MoSCoW per milestone, Musts are capped near 60% of capacity, and "Won't this time" items are recorded in the scope boundary.
- [ ] Backlog ranking uses a quantified method (RICE/WSJF) with the numbers shown; MoSCoW is applied per milestone, not once.
- [ ] Every increment is a thin vertical slice that crosses the full stack, fits in one sprint, and is demoable with testable acceptance criteria.
- [ ] Every issue rolls up to exactly one milestone; epic milestones are titled `vX.Y.0` (one MINOR) and theme/hardening milestones are titled by theme (a PATCH), and `/solomon-refine` creates the milestone and assigns its Ready children.
- [ ] Releases are milestone-driven, not time-boxed or per-PR: a tag is cut when an epic milestone (MINOR) or a theme milestone (PATCH) hits zero open issues with CI green, or on demand via `solomon-harness release prep`; a single merge only burns a milestone down.
- [ ] Versioning is SemVer computed from Conventional Commits at cut time, not chosen in planning; no one hand-edits `pyproject.version` or the CHANGELOG, and the mechanics are governed by `docs/release-policy.md`.
- [ ] Each roadmap item is tracked on the board through Ideas -> Backlog -> Ready -> In Progress -> Code Review -> QA -> Done using the matching `/solomon-*` step, with decisions and handoffs persisted in project memory.
- [ ] Dates are expressed as probabilistic forecasts from measured throughput (Monte Carlo) of when a milestone reaches zero open issues, quoted at named confidence levels, with internal commitments at P85.
- [ ] Forecasts are re-run each iteration; the strategic bet, forecast snapshots, and re-scope decisions are persisted via `save_decision` / `save_memory`, and milestone-threatening slips raised via `log_issue` and `log_handoff`.
