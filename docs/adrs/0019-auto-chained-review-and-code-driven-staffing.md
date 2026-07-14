# ADR-0019: Auto-chained Review stage and code-driven reviewer staffing

- Status: accepted
- Date: 2026-07-04
- Deciders: software_architect, qa, security, product_owner
- Issue: #182

## Context and problem statement

The Review stage was operator-triggered: `/solomon-start` ended by telling the
operator that qa should run `/solomon-review`, so every PR waited on a manual
invocation or on the next session's digest. Reviewer staffing was also fixed at
three lenses (qa, security, software_architect) regardless of what the diff
touched: a cockpit UI change got no frontend eyes, a SurrealDB schema change no
dba, a CI/release change no sre. Two decisions were needed: where the
chaining lives, and how domain reviewers are selected.

## Decision Drivers

- Review must be part of the workflow, not a separate manual step (maintainer directive).
- One mechanism must cover both hosts (Claude Code, Gemini CLI) and both modes (interactive, headless `dev start`).
- Staffing must be auditable and deterministic, not prompt discretion.
- Reviews must stay bounded: more parallel reviewers add latency past a point.
- The human merge gate must remain untouched.

## Considered Options

- **Chaining — Option 1 (prompt-level):** the final step of the start command file continues directly into the Review flow. Headless `dev start` builds its prompt from the same markdown (`workflows.py.build_prompt`), so one edit covers every host and mode.
- **Chaining — Option 2 (STAGES-level):** `workflows.py` invokes the review stage after start succeeds. Covers only the headless path, duplicates flow logic, and needs the PR number resolved out-of-band.
- **Staffing — Option A (fixed roster):** keep qa, security, software_architect for every PR.
- **Staffing — Option B (code-driven conditional lenses):** a pure module maps changed paths to domain lenses, added on top of the mandatory gates.

## Decision Outcome

Chosen: **prompt-level chaining (Option 1)** and **code-driven staffing (Option B)**.

- `/solomon-start` step 6 continues directly into the Review flow for the PR it
  just opened. A blocker verdict halts the chain and returns to the human — no
  fix-and-re-review inside the same run. The review records whether it was
  auto-chained (provenance in `save_decision`), so an auto-chained approval is
  distinguishable from an independently invoked one.
- The Review stage always runs the three mandatory gates. In addition,
  `solomon_harness/review_roster.py` selects up to two conditional domain
  lenses from `gh pr diff --name-only`, in fixed priority order
  (auth_engineer, dba, sre, loop_engineer, frontend, observability,
  practice_curator, documenter). The module is pure (no gh calls), the lens
  vocabulary is closed, the cap is 2 (beyond three gates plus two lenses,
  reviewers stop adding signal and start adding latency), and a mandatory gate
  can never be returned.
- **Roster-match rule:** every lens name in the selection table must be a
  deployable agent (`agents/<name>/agents/<name>.md`), guarded by a fitness
  test. ux_designer is therefore not in the table yet; it joins when its agent
  definition lands (in flight on feature/ux-designer-agent).
- Handoff status literals in the command files are aligned to the canonical
  handoff vocabulary (`open`, `accepted`, `done` — `database_client.HANDOFF_STATUSES`).

### Consequences

- **Positive:** every PR gets a domain-aware review with zero manual triggering; the selection is testable and auditable; both hosts and both modes share one definition.
- **Negative:** the authoring context orchestrates its own review (self-review by construction). Mitigations: gates run as fresh-context subagents reading the PR from gh, blockers halt the chain, provenance is recorded, and the merge stays human.
- **Negative:** the path rules encode this repository's layout; on projects the harness is installed into, unmatched rules simply select nothing and the three gates run — graceful, but config-extensible rules are a follow-up.
- **Follow-ups:** align the remaining command files and skills that prescribe non-canonical handoff statuses; add ux_designer to the table once its agent definition merges; consider config-driven lens rules for host projects.

## More information

This decision is also recorded in the project memory via `save_decision`.
