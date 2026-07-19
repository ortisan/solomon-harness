# QA living documentation

This tree is the committed, version-controlled record of persona-driven
exploratory testing, maintained per the `qa` agent's
`persona_driven_exploratory_testing` skill. It is separate from the
requirements traceability matrix (criterion-to-test coverage): here the unit is
a persona walking a journey, and coverage means "every planned journey was
walked by a persona this cycle", a session ledger rather than a per-case count.

## Layout

- `personas.md` — the personas whose goals and constraints frame every session.
- `journeys/J-NN-<slug>.md` — journey maps (a persona's path to a true end state,
  including abandonment paths).
- `charters/CH-NNN.md` — session charters (mission, persona, journey, one tour,
  a time-box), updated in place with a per-run debrief.
- `state.csv` — the scenario tracker. Every non-`notes` column is an enum, id,
  path, or one-line value so any question ("all failing scenarios") is one grep.
- `templates/` — the charter and (as needed) report templates.

## Area codes

- `BE` — offline behavioral-evaluation pilot commands and evidence flow.

## `state.csv` columns

`id, area, title, persona, journey, expected, entry_points, qa_status, bug_ids,
fix_status, retest_status, fix_commits, evidence, last_report, overlaps, notes`.

- `qa_status`: `untested | pass | fail | blocked-verify | blocked-decision | skipped`.
  A `fail` row must carry non-empty `bug_ids`.
- `fix_status`: *(empty)* `| pending | fixed | deferred`; a `fixed` row carries the SHA in `fix_commits`.
- `retest_status`: *(empty)* `| pending | pass | fail`.

## The honesty rule

Whoever lands a user-visible behavior change — a UI, CLI verb, API route, config
key, or copy change, including an agent completing a non-QA task — resets the
affected scenario rows to `untested` as part of task completion. A stale `pass`
is worse than no verdict; the next cycle's targeted tier picks up the `untested`
rows as its scope. Flag, do not retest.

## Bugs

Defects are filed through the `defect_triage_and_lifecycle` `log_issue`
lifecycle and the project memory, never as a parallel file-based registry (the
memory is the single source of truth). The five user-impact tiers
(Blocks-Completion, Data-Loss, Trust-Damage, Friction, Cosmetic) map onto the
existing `uat` Blocker/Critical/Major/Minor/Trivial scale.

## Changelog

- 2026-07-19: Added the issue #369 behavioral-evaluation operator journey,
  targeted charter, and untested scenario rows.
- Bootstrapped with epic #341 package 6 (persona-driven exploratory testing v1).
