# Milestones

Governs how a milestone is planned, tracked, and closed in this repository: one milestone equals one release scope with a hard due date and a written acceptance bar, recorded both on GitHub and in the project memory. No open-ended milestones; every milestone must be answerable with "shipped on time, in scope, or not."

## Defining a milestone

A milestone is a time-boxed scope, not a label. Hold each one to four properties before it accepts any issue.

- Title format: `Sprint <n>` for cadence sprints or `v<MAJOR.MINOR.PATCH>` for release milestones (`Sprint 4`, `v1.4.0`). Pick one scheme per project and keep it consistent so `list_milestones` reads cleanly.
- A written goal in the description: one sentence of outcome plus the bulleted objectives that satisfy it. "Ship the walk-forward backtest pipeline" with the concrete deliverables under it.
- A hard due date. The date is a commitment, not an aspiration; it is what makes the milestone falsifiable.
- An acceptance bar: the explicit condition for calling it done (for example "all child issues closed, CI green on `main`, release notes published").

Cap scope to measured velocity, not optimism. Use the team's recent throughput, not a best case, to decide how many issues fit. Work that arrives mid-milestone goes to the backlog or the next milestone; it never expands the current one, because moving the due date to absorb scope destroys the signal a milestone exists to give.

## Memory and GitHub hooks

Milestones live in two places and both must agree. GitHub is where issues attach; the project memory is where the scrum context and history persist for the next session.

Create a GitHub milestone with the scrum script:

```bash
scripts/scrum-master.sh milestone-create "v1.4.0" \
  "Walk-forward backtest pipeline: rolling split, slippage model, report." \
  "2026-07-15"
scripts/scrum-master.sh milestone-list
```

Record the same milestone in the project memory through the `solomon-memory` MCP tools, which back onto `DatabaseClient.create_milestone(title, description, due_date, state)` and `list_milestones()`:

- `create_milestone(title, description, due_date, state)` — `state` is the lifecycle marker, one of `active`, `pending`, or `complete`. A milestone in flight is `active`; one queued behind the current one is `pending`; a closed one is `complete`.
- `list_milestones()` — returns milestones most recent first, for resuming where planning stopped.

Keep the two in step: when you open the GitHub milestone, write the memory record with `state="active"`; when you close it on GitHub, update the memory state to `complete` so `/solomon-workflow` reads an accurate picture on the next session.

## Mapping issues to a milestone

Every issue that counts toward the release is assigned to exactly one milestone; an unassigned issue is invisible to the burndown.

- Assign on GitHub at refinement time, the moment an issue reaches Ready, so the milestone's scope is always the sum of its child issues.
- Only Ready issues enter an active milestone. A vague or unestimated issue inflates the scope with work that cannot be planned; refine it first or leave it in the backlog.
- The milestone's progress is its closed-versus-open issue count. Do not track progress in prose; let the issue states be the burndown.
- An issue belongs to one milestone at a time. Splitting work across milestones means splitting the issue, not double-assigning it.

## A worked milestone

Planning the `v1.4.0` release for the backtest pipeline:

1. Define it: title `v1.4.0`, goal "Deliver the walk-forward backtest pipeline so strategies are evaluated out-of-sample across regimes," due `2026-07-15`, acceptance bar "all child issues closed, CI green on `main`, release notes published via `scripts/wiki-sync.sh`."
2. Create it on GitHub and in memory:

```bash
scripts/scrum-master.sh milestone-create "v1.4.0" \
  "Walk-forward backtest pipeline. Acceptance: all child issues closed, CI green on main, notes published." \
  "2026-07-15"
```

```python
create_milestone(
    title="v1.4.0",
    description="Walk-forward backtest pipeline. Acceptance: all child issues "
                "closed, CI green on main, release notes published.",
    due_date="2026-07-15",
    state="active",
)
```

3. Assign the Ready issues to it: #142 walk-forward split, #143 slippage model, #144 backtest report. Three issues sized to the team's measured velocity, not five squeezed in to look ambitious.
4. Track by issue count: as #142, #143, #144 close, the milestone burns down. A late-arriving "add Sharpe ratio chart" request lands in the backlog for `v1.5.0`, not in this milestone.
5. Close it only when every child issue is closed or explicitly deferred with the reason recorded in memory, then set the memory state to `complete` and cut the release.

## Common pitfalls

- An open-ended milestone with no due date: it cannot be late, so it gives no schedule signal and never forces a scope decision. Always set a hard date.
- Moving the due date to absorb new scope: it converts the milestone from a commitment into a moving target and destroys the velocity data the next plan depends on. Push new work to the next milestone instead.
- Sizing to optimism rather than measured velocity: the milestone overruns predictably, and a chronically missed date trains the team to ignore the date entirely.
- The GitHub milestone and the memory record drifting out of state: `/solomon-workflow` reads memory to resume, so a milestone marked `active` in memory but closed on GitHub makes the loop propose dead work.
- Assigning vague, unestimated issues to an active milestone: they cannot be planned and silently inflate the scope; only Ready issues belong in an active milestone.
- Closing a milestone with issues still open and no deferral note: the history loses why the scope was cut, and the dropped work vanishes instead of returning to the backlog.
- Tracking milestone progress in prose instead of issue states: the burndown becomes opinion; let the closed/open count be the truth.

## Definition of done

- [ ] Title follows `Sprint <n>` or `v<MAJOR.MINOR.PATCH>`, consistent with the project's scheme.
- [ ] The description states a one-sentence goal, the bulleted objectives, and an explicit acceptance bar.
- [ ] A hard due date is set on both the GitHub milestone and the memory record.
- [ ] Scope is capped to measured velocity, and every assigned issue is Ready.
- [ ] The milestone exists on GitHub (`milestone-create`) and in memory (`create_milestone` with the correct `state`), and the two agree.
- [ ] Each child issue is assigned to exactly one milestone; progress is read from issue states, not prose.
- [ ] Mid-milestone arrivals were routed to the backlog or a later milestone, never added to the active one.
- [ ] The milestone is closed only when every child issue is closed or deferred with a reason recorded in memory, and the memory state is set to `complete`.
