---
name: analytics-workflow-and-reproducibility
description: Governs reproducible analytics workflow: notebook discipline (restart-and-run-all, jupytext pairing), parameterized reports with papermill and Quarto, versioned queries pinned to data snapshots, and peer review before a number ships. Use when building or reviewing a recurring report or notebook analysis.
---

# Analytics Workflow and Reproducibility

Running analysis like software: notebooks that execute top-to-bottom from a clean kernel, reports parameterized instead of copy-pasted, every query versioned in git with the data snapshot it ran against, and a peer-review step before a number reaches a stakeholder. The stance: if a colleague cannot regenerate your headline number from the repository in one command, the analysis is an anecdote. Reproducibility is what makes an analysis reviewable, and review is what makes it trustworthy.

## Notebook discipline

Notebooks are for exploration and presentation; logic lives in modules.

- The non-negotiable gate: **Restart kernel and run all** must succeed before a notebook is shared or committed. Hidden state — cells run out of order, variables from deleted cells — is the single largest source of irreproducible findings.
- Keep notebooks thin: data access, transformations, and metric computations go into plain `.py` modules under `src/`, imported by the notebook and covered by unit tests per the house TDD rule. A cell longer than a screen is a function that has not been extracted yet.
- Pair notebooks with **jupytext** (`.ipynb` + `.py:percent`) so diffs are reviewable in pull requests; raw `.ipynb` JSON diffs are unreviewable and merge badly. Strip or ignore outputs in git (`nbstripout`) except for deliberately published report notebooks.
- Pin the environment: `uv` project with a committed lockfile (or an equivalent lock). "Works on my laptop with whatever pandas I had" is not an environment.
- Set every source of randomness explicitly — `numpy.random.default_rng(42)`, sampling seeds in SQL (`ORDER BY hash(id)` rather than `ORDER BY random()`) — so reruns produce identical samples.

## Parameterized reports

A recurring report is a template plus parameters, never a copy of last month's file with hand-edited dates.

- **papermill** executes a notebook per parameter set; **Quarto** renders `.qmd` to HTML/PDF with `params`. Both fit CI schedules.

```bash
papermill weekly_report.ipynb out/weekly_2026-06-29.ipynb \
    -p week_start 2026-06-29 -p region all
quarto render churn_report.qmd -P snapshot_date:2026-07-01
```

- All date logic derives from a single `as_of` parameter; no `datetime.now()` buried in cell 14, which makes every rerun a different report.
- Generated outputs are named by their parameters and archived; the copy sent to stakeholders is immutable, so "the number changed since you sent it" is answerable by diffing two archived runs.

## Versioned queries and pinned data

- Every query behind a published number lives in the repository (`analyses/<slug>/query.sql`), not in a BI tool text box or a chat message. The BI tool may display it; git owns it.
- Analytical results must pin their input. Against a live warehouse, that means an explicit snapshot predicate (`WHERE loaded_at <= '2026-07-01 00:00:00+00'`) or querying a snapshot/frozen table, because rerunning yesterday's query against today's data is a different analysis. Record the snapshot identifier in the report header.
- Materialize the intermediate dataset a finding rests on as Parquet keyed by run (`data/processed/churn_base_2026-07-01.parquet`) with row count and checksum logged. When the finding is challenged in a quarter, you reload the exact frame instead of archaeologically reconstructing it.
- Each analysis directory carries a short `README` header block: question, author, date, data sources with snapshot ids, and the one command that regenerates everything.

## Peer-reviewable analysis

Every analysis that informs a decision gets a reviewer, and the review has teeth:

1. Reviewer regenerates the headline number from the repo with the documented command. If it does not reproduce, review stops there.
2. Checks the load-bearing joints, not the prose: join grains and fan-out (see `sql_analytics`), denominators and segment mix (see `metrics_and_kpi_design`), filter and exclusion choices, date boundaries and timezones, and whether data-quality checks passed on the inputs (see `data_quality_and_validation`).
3. Hunts for the strongest alternative explanation: seasonality, a tracking change, a mix shift, a backfill. The analyst pre-empts this with a "threats to validity" section.
4. Statistical methodology — test choice, power, multiple comparisons, causal claims — is reviewed by `ml_engineer`; the analyst does not self-certify inference.

Record the review outcome and material decisions in the project memory (decision log), so the next analyst finds why a filter exists instead of re-deriving it.

## Common pitfalls

- A notebook that only produces the published number with its historical hidden state; restart-and-run-all was never tried.
- `datetime.now()` scattered through the code, so no two runs are the same report.
- The canonical query living only inside a BI dashboard, edited in place until nobody knows which version produced the board deck.
- Rerunning an old query against a moved warehouse and treating the difference as a data bug instead of a missing snapshot pin.
- Unpinned environments: the rerun six months later fails on a pandas API change, and the finding becomes unverifiable exactly when questioned.
- Committed `.ipynb` outputs bloating the repo and leaking data samples into git history.
- Review as prose proofreading — nobody reruns the code or checks a join grain.
- Sampling with `ORDER BY random()` and no seed, making "check a sample of mismatches" unrepeatable.

## Definition of done

- [ ] The notebook passes restart-and-run-all from a clean kernel; heavy logic is in tested modules, not cells.
- [ ] Notebooks are jupytext-paired (or output-stripped) so the diff is reviewable in the PR.
- [ ] The environment is locked and committed; all randomness is seeded.
- [ ] Recurring reports are parameterized (papermill/Quarto) with a single `as_of` parameter; generated outputs are archived immutably.
- [ ] Every query behind a published number is in git; inputs are pinned to a named snapshot recorded in the report header.
- [ ] The intermediate dataset for the headline finding is materialized with row count and checksum.
- [ ] One documented command regenerates the analysis end-to-end, and the reviewer actually ran it.
- [ ] Review covered joins, denominators, filters, and alternative explanations; statistical methodology was signed off by `ml_engineer`.
- [ ] The decision and review outcome are logged in project memory.
