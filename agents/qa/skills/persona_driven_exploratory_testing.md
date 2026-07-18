---
name: persona-driven-exploratory-testing
description: Plans and runs real-user exploratory QA as a living docs/qa/ tree — personas derived per project, journeys mapped as flows before any scenario exists, session charters that time-box a persona's single tour, and a state.csv scenario ledger — routing every finding through the defect_triage_and_lifecycle log_issue lifecycle instead of a parallel bug registry. Use when planning a QA cycle's persona and journey coverage, writing or re-running a session charter, or updating docs/qa/state.csv after an exploratory session.
---

# Persona-Driven Exploratory Testing

Scripted case-based QA answers "does this button work"; this skill answers a different question — "can a real person, in role, actually get the value this product promises." A persona walks a journey through the product's real interfaces, feels the friction, hits the edges, and the session's findings write back into one committed tree, `docs/qa/` by default, that every cycle appends to rather than replaces. Completeness is never a case count: it is whether every planned journey was walked by a persona this cycle — a session ledger, not a case count. This skill owns that tree's contract, the persona and journey methodology, the session-charter format, and how findings connect to the project's actual defect lifecycle.

## The living docs/qa/ tree

One committed tree per project, never a per-round `qa-v2/` folder living alongside it:

```
docs/qa/
├── README.md                 # area codes, entry points, changelog
├── state.csv                 # the living scenario tracker
├── personas.md                # project personas (instance data)
├── journeys/J-<NN>-<slug>.md  # journey maps: Mermaid flow + YAML anatomy
├── charters/CH-<NNN>.md       # session charters
└── templates/charter.md       # the charter template new charters are written from
```

Durable versus per-run matters for how the tree is maintained: `state.csv` rows, `personas.md`, `journeys/`, and `charters/` (the charter files themselves — missions persist and get re-run across cycles) grow and never reset; only a charter's appended debrief and a run's evidence are per-run artifacts. Resetting an id "for the new round," or drafting a fresh charter each cycle instead of re-running the existing one with a new debrief, both destroy the cross-cycle memory this tree exists to keep. This project's own scaffold — `docs/qa/README.md`, `state.csv`, `personas.md`, `templates/charter.md` — is the bootstrap seed; `journeys/` and `charters/` fill in as the first cycle maps its first journey and writes its first charter.

## Deriving personas per project

Write 3-6 personas to `docs/qa/personas.md`, each grounded in the product's real audience, never copied verbatim from a seed catalog. Start from who pays, who uses daily, who arrives for the first time, and who returns after something broke; map each to the nearest seed archetype and adapt it with a product-specific goal, device, network, and patience threshold:

- **New User** — zero familiarity, evaluating, abandons within 60 seconds of confusion. Reveals onboarding gaps and unclear primary actions.
- **Power User** — daily use, keyboard-driven, tolerant of rough UI but zero-tolerant of speed regressions. Reveals shortcut and bulk-operation breakage.
- **Casual User** — infrequent visits, remembers the goal not the steps, switches devices mid-task. Reveals discoverability and save-and-resume bugs.
- **Mobile User** — touch-first, small viewport, possibly slow network. Reveals touch-target and layout-break defects.
- **Accessibility-Reliant User** — screen reader, keyboard-only, or high-contrast mode. Reveals missing labels, focus traps, and unannounced dynamic content.
- **Recovering User** — returning after a prior failure, trust is fragile. Reveals stale error states and half-applied fixes.

Include at least one Mobile-based persona when a mobile surface exists, and one Accessibility-Reliant persona unless explicitly out of scope with the skip reasoning recorded in `personas.md` itself — a silent omission reads as coverage that was never actually there.

## Mapping journeys as flows before any scenario exists

The rule is flows before matrix: no `state.csv` row exists until its journey is mapped. A journey is entry -> actions -> goal -> exit, with branch points and abandonment paths hanging off it, and its terminal node is the **true end state** — the post-goal confirmation on a fresh reload, an email that cites the right order id, a setting that survives a reload — never the button click that submitted the request. Each journey file, `docs/qa/journeys/J-<NN>-<slug>.md`, carries a Mermaid flowchart (entry points, each action as a node, validation/empty/permission-denied branch points, side effects as explicit nodes, the true end state, at least one abandonment path) followed by the YAML anatomy: `id`, `name`, `value_statement`, `personas`, `entry_points`, `actions` with an `expected_observable` per step, `goal`, `true_end_state`, `exit`, `abandonment` (at_step, how, resume), and `crosses` for journeys spanning team or service boundaries — those get regression priority, because no single owner watches the whole contract. Walking the finished flowchart node by node and edge by edge is what derives the actual `state.csv` scenarios: the happy path end-to-end, each branch point a real persona plausibly hits, each abandonment-and-resume path, and each side effect's landing.

## Session charters: CH-NNN

A charter is the atomic planning unit — a written mission for one time-boxed session, not a test case. Six parts: mission (one sentence, what and why), persona (from `personas.md`), journey (`J-NN`), exactly one tour (the thematic lens driving off-script exploration — a Back-Button Tour, an Error-Injection Tour, a Money Tour; pick one, mixing dilutes findings), a time-box (30 / 60 / 90 minutes, and the box ends when it ends — piled-up findings at the deadline become a follow-up charter, not an extension), and the `state.csv` scenario ids this session can settle. One file per charter at `docs/qa/charters/CH-<NNN>.md`, ids global and monotonic; charters are durable and get re-run in later cycles with a fresh debrief appended per run, never redrafted. Pick the cycle's cadence tier first, and the tier picks the journeys: **Smoke** (2-4 highest-value journeys, happy path, 30-minute charters, every deploy), **Targeted** (journeys the diff touches plus one adjacent canary, 30-60 minutes, every branch/PR with a user-visible change), **Full** (every P0/P1 journey, every project persona, 60-90 minutes, release candidates), **Sanity** (the fixed journey plus one adjacent, 30 minutes, after a hotfix). Order sessions by risk — highest-impact journey times highest-blast-radius tour first.

## The coverage inversion

The completeness question is never "does every persona have at least one test case" — that instinct produces case-accumulation with zero confidence behind it. It is "was every journey in scope walked by a persona this cycle" — a session ledger, not a case count. A cycle with five deep sessions that walked five journeys end to end beats a cycle that generated forty test-case files and walked nothing. A session without a debrief is wasted exploration: stop the timer, write findings within five minutes before surprises normalize, update the settled scenarios, and suggest the next charter — what this session did not reach.

## The state.csv scenario ledger

One row per scenario — a persona-visible behavior derived from a journey flow, not a feature and not a test case. The column contract: `id` (`<AREA>-NNN`, stable, never reused, never renumbered), `area` (a code defined once in `docs/qa/README.md`), `title`, `persona`, `journey` (`J-NN`), `expected` (the observable that proves success, in user language), `entry_points`, `qa_status`, `bug_ids`, `fix_status`, `retest_status`, `fix_commits`, `evidence`, `last_report`, `overlaps` (cross-linked scenario ids, canonical owner first), and `notes` — the only free-prose column. `qa_status` is `untested` / `pass` / `fail` / `blocked-verify` (only a human can complete it — real payment, external email, OAuth with a real account) / `blocked-decision` (needs a human product decision first) / `skipped` (deliberately out of scope, reasoning in `notes`). `fix_status` is empty, `pending`, `fixed`, or `deferred`; `retest_status` is empty, `pending`, `pass`, or `fail`, and is only meaningful once `fix_status` is `fixed`. Ids mint as `<AREA>-NNN`, monotonic per area, next id equal to the highest existing plus one; a retired scenario is marked `skipped` with a reason, never deleted and never renumbered into reuse. Planning creates and updates columns 1-7, 15, and 16; execution updates 8-14 after a session runs.

### Keeping the tracker honest between cycles

Whoever lands a user-visible behavior change — a UI change, a CLI verb, an API route, a config key, copy — resets the affected rows to `untested` as part of calling that work done, including an implementing agent finishing a task that is not itself a QA task. New behavior adds new `untested` rows; changed behavior resets the rows it touches; a pure refactor with no user-visible change states that explicitly and touches nothing. Flag, do not retest — the next cycle's targeted tier picks up the `untested` rows as its scope automatically. This is the honesty rule the harness's `/solomon-start` workflow enforces at its handoff step, and it is what keeps the tracker alive between QA cycles instead of accumulating silent staleness.

## Filing findings: no parallel bug registry

A session finding is a defect like any other in this project — file it with `log_issue` per `defect_triage_and_lifecycle`'s state machine, never as a separate markdown file in the QA tree. The project memory is the system of record for every defect; a file-based registry running alongside it is a second source of truth that will drift the moment the two disagree. Dedup before filing: check `get_open_issues` and the affected row's existing `bug_ids` for the same symptom. A re-found, not-yet-fixed symptom updates the existing issue rather than minting a new one; a symptom that recurs after `retest_status: pass` reopens its issue rather than filing fresh — a regression on the same id is far more informative than a new one. Link the returned issue identifier into the affected row's `bug_ids` column (semicolon-separated when more than one applies), and let `fix_status`/`retest_status` mirror that issue's lifecycle state: when `defect_triage_and_lifecycle` moves the issue to Verified, retest the row's persona/journey walk and record `retest_status: pass` before the row reads as done.

## Five user-impact tiers

Classify every finding by what it does to a real person, not to the technology — a "critical" exception in an admin log can matter less than a "minor" copy bug on the only checkout button. Pick exactly one tier; when torn between two, pick the higher. **Blocks-Completion**: a user on a value-delivering journey cannot complete it and gives up or works around into an incorrect state. **Data-Loss**: entered, uploaded, or configured data is destroyed, corrupted, or made inaccessible without consent, often unnoticed by the user. **Trust-Damage**: nothing is technically broken, but confidence erodes — a confirmation email citing a different order id than the UI, an error with no next step, a screen reader announcing "image image image." **Friction**: the journey completes, but with extra effort, confusion, or repetition. **Cosmetic**: visual or wording issues affecting neither completion nor trust, though Cosmetic on a hero or first-impression surface is at least Friction and should be re-classified. These five tiers map onto this roster's release-gate severity scale — the concrete translation table lives in `uat` (Blocker/Critical/Major/Minor/Trivial); it is not re-derived here. When filing via `log_issue`, translate the tier toward `defect_triage_and_lifecycle`'s independent severity/priority axes with the same default: Blocks-Completion and Data-Loss default to S1/P0, Trust-Damage to S2/P1, Friction to S3/P2, Cosmetic to S4/P3 — `defect_triage_and_lifecycle` still owns the final call once reach and frequency are known.

## Common pitfalls

- Running a session as "just a user" instead of committing to one persona; a generic session optimizes for the tester's own reflexes and finds what the tester already expected to find.
- Enumerating scenarios from a feature or file list before any journey is mapped as a flow — matrix-before-flows produces page tests, and the breakage that lives between pages never surfaces.
- Counting completeness by test-case volume instead of journeys walked by a persona — the exact case-accumulation failure mode the coverage inversion exists to prevent.
- A charter with no debrief, or a debrief written the next day after surprises have normalized into "that's just how it is."
- Filing a session finding as a new markdown file in the QA tree instead of through `log_issue`, creating a second bug ledger that silently drifts from the memory-backed one.
- Landing a user-visible change and leaving `state.csv` rows at a stale `pass`, so the tracker keeps certifying a surface that has since changed underneath it.
- Skipping the Mobile or Accessibility-Reliant persona with no recorded reasoning, leaving a real segment of the audience unverified every single cycle.
- Mixing two tours into one charter to save time; the findings blur and neither tour's theme produces a clean signal.

## Definition of done

- [ ] Personas are derived from the product's real audience (3-6, at least one Mobile-based and one Accessibility-Reliant unless explicitly scoped out with reasoning recorded) and live as durable instance data in `docs/qa/personas.md`.
- [ ] Every in-scope journey has a flowchart with a true end state and at least one abandonment path, filed at `docs/qa/journeys/J-<NN>-<slug>.md`, mapped before any scenario was derived from it.
- [ ] Every in-scope journey has at least one session charter (`docs/qa/charters/CH-<NNN>.md`) naming a mission, one persona, one journey, exactly one tour, and a time-box.
- [ ] Every run charter's debrief is appended within five minutes of the time-box closing, and the cycle's completeness is reported as journeys walked by a persona, never a case count.
- [ ] `docs/qa/state.csv` carries one row per scenario with the full sixteen-column contract, enum-only status columns, and ids minted per the `<AREA>-NNN` rule, never reused or renumbered.
- [ ] A user-visible change resets its affected `state.csv` rows to `untested` as part of the change being called done; a pure refactor states "no user-visible change" explicitly instead.
- [ ] Every finding is filed through `log_issue` (no parallel bug-registry file anywhere in the tree), deduped against `get_open_issues` and the row's `bug_ids` first, and linked back into the affected row.
- [ ] Each finding carries exactly one of the five user-impact tiers, mapped onto `uat`'s Blocker/Critical/Major/Minor/Trivial scale and translated toward `defect_triage_and_lifecycle`'s severity/priority axes.
