# CH-001: Behavioral-evaluation feature tour

- Persona: Operator
- Journey: J-01-behavioral-evaluation-pilot
- Tour: Feature
- Time-box: 60 minutes
- Scenarios in scope: BE-001, BE-002, BE-003

## Mission

Confirm that an operator can prepare, score, and compare the offline pilot from
the documented entry points, verify the directional verdict, and recover from an
incomplete comparison without creating a report.

## Debrief (append per run, newest first)

### 2026-07-19: pass, offline schema-version-2 fixture replay

- The Operator persona walked J-01 from preparation through the persisted comparison
  report with the committed manifest and recording fixtures.
- `prepare` exited 0 and produced 54 run entries, 54 unique scratch paths, 54
  `request.json` files, and one propagated golden-set digest across every request.
- `score` exited 0 and produced 54 results with mode `0600`. Closed `load_results`
  parsing returned 54 records. One cache value and one reported-cost value remained
  `null`; one observed all-zero usage envelope remained zero.
- A repeated score produced byte-identical output. Both `score` commands and `cmp`
  exited 0.
- `compare` exited 0 and its closed loader returned `eligible=false`. Baseline and
  candidate each passed 26 of 27 runs. The report named the `review-happy` repetition
  2 regression and recorded usage attribution as `met`.
- A repeated comparison produced byte-identical output. Both `compare` commands and
  `cmp` exited 0.
- Removing `planning-happy`, baseline repetition 1 made comparison exit 2 with
  `incomplete_comparison`. The error named the missing identity and no output file was
  created.
- Replaying a version-1 recording made scoring exit 2 with `unsupported_schema` and
  created no result file.
- The source checkout HEAD and pre-existing worktree status were unchanged across the
  command session. Results and comparison files were created with mode `0600`.
- Findings filed: none. `BE-001`, `BE-002`, and `BE-003` moved from `untested` to
  `pass`.
- This run replayed committed evidence and made no model call. It did not execute a
  paid host session, so host identity and containment remain self-reported evidence,
  as the product contract states.
