---
name: sast
description: Standardizes static analysis on this Python codebase — the ruff-S, bandit, semgrep, and CodeQL tool stack, where each runs in pre-commit and CI, what severity blocks a merge, and how findings are triaged and suppressed with a justified, attributable comment. Use when adding a scanner to CI, writing a custom Semgrep rule, or reviewing whether a suppression is justified rather than a bare bypass.
---

# Static Application Security Testing (SAST)

The standard for running static analysis on this Python codebase: which scanners run, where they run (pre-commit and CI), what blocks a merge, and how findings are triaged and suppressed. SAST is a merge gate, not a dashboard — a finding that does not block or get a justified suppression is noise, and noise kills the program through alert fatigue.

## Tool stack for this repository

Layer the tools; each catches what the previous one cannot.

- `ruff` security rules: the flake8-bandit port lives in ruff's `S` rule family. Enable it in `pyproject.toml` (`[tool.ruff.lint] extend-select = ["S"]`) so `uv run ruff check solomon_harness tests` — already in `.github/workflows/ci.yml` — flags `S602` (`shell=True`), `S301` (pickle), `S506` (`yaml.load`), `S105`-`S107` (hardcoded passwords) in milliseconds. Fastest feedback, weakest analysis: pattern-only, no dataflow.
- `bandit` for AST-level checks: run `bandit -r solomon_harness -ll -ii` (HIGH severity, HIGH confidence) as the blocking tier; report MEDIUM without blocking. Bandit and ruff-S overlap heavily; keep bandit if you need its config granularity, otherwise ruff-S alone avoids double-reporting.
- `semgrep` for cross-line patterns and taint: run `semgrep --config p/python --config p/security-audit --config p/owasp-top-ten --error`. Semgrep is where repo-specific rules live (below). Use `--baseline-commit $BASE_SHA` on PRs so only introduced findings surface.
- CodeQL for interprocedural dataflow on the default branch: `github/codeql-action` (pinned to a full commit SHA like every action in this repo) with the `python` language pack, on PRs plus a weekly `schedule:` cron, with `security-events: write` as the only elevated permission on that job. CodeQL finds source-to-sink flows across functions that pattern tools miss; it is also the slowest, so it does not gate pre-commit.

Keep dependency scanning (`pip-audit`, osv-scanner) out of the SAST lane — different signal, different SLA (see the dependency skill).

## Custom rules

Generic rulesets do not know this project's sinks. Write Semgrep rules for them. Example: the memory client must never build SurrealQL by interpolation — bound parameters only:

```yaml
rules:
  - id: surrealql-string-interpolation
    languages: [python]
    severity: ERROR
    message: SurrealQL must use bound parameters, never f-string/format interpolation.
    patterns:
      - pattern-either:
          - pattern: $DB.query(f"...", ...)
          - pattern: $DB.query("..." % $X, ...)
          - pattern: $DB.query("...".format(...), ...)
```

Commit rules under `.semgrep/`, give each a test file with true-positive and true-negative cases (`semgrep --test`), and treat a rule change like code: reviewed, with rationale in the PR.

## CI wiring

Order the pipeline cheap-to-expensive: ruff (with `S` enabled) already runs in the `validate` job; add semgrep as a step in the same job so one red check reports all pattern findings; run CodeQL as a separate workflow because it needs `security-events: write` and its own runtime budget. Mirror ruff-S and gitleaks in `.pre-commit-config.yaml` so developers see findings before push. CI remains authoritative — pre-commit can be skipped locally, the merge gate cannot.

## Triage discipline and budgets

Every new finding is triaged within one business day into exactly one bucket:

- True positive: fix it, with a regression test first (house TDD rule).
- False positive: suppress with justification (below) and record the rule id.
- True positive, accepted: compensating control plus an expiry-dated exception per the remediation-SLA skill.

Budget the noise, not just the fixes. Track per-rule false-positive rate; when a rule exceeds roughly 30% false positives over a month, tune it (narrow the pattern, add `pattern-not`) or demote it from blocking to report-only. A gate that engineers routinely bypass with blanket suppressions is worse than no gate. The zero-new-HIGH rule stays absolute: no HIGH-severity finding introduced by a PR merges, ever; the pre-existing backlog is burned down under the SLA skill, not by the PR author.

## Suppression policy

A suppression is a reviewed, justified, attributable artifact:

- ruff: `# noqa: S602  # vetted: argv built from a literal list, no user input`
- bandit: `# nosec B602  # vetted: see threat model TM-12` — always with the specific test id; a bare `# nosec` silences every check on the line and is rejected in review.
- semgrep: `# nosemgrep: surrealql-string-interpolation  # value is a compile-time constant`

Rules: the comment names the rule id and states why the finding does not apply here — "false positive" alone is not a justification. Temporary suppressions reference the tracking issue and carry an expiry. Audit the suppression inventory quarterly (`grep -rn "nosec\|noqa: S\|nosemgrep" solomon_harness/`) and delete stale ones; an unjustified suppression found in audit is reopened as a finding.

## Common pitfalls

- A bare `# nosec` or file-wide `# noqa` that silences all rules instead of the one intended, hiding future real findings on the same line.
- Scanning the whole repo on every PR without a baseline, so authors face a wall of pre-existing findings and learn to ignore the check.
- Treating tool severity as triage: bandit HIGH on a test fixture is not a production HIGH; triage considers reachability and context, the gate considers severity.
- Running only pattern tools and claiming dataflow coverage; `S`-rules cannot see a tainted value passed through two function calls — that is CodeQL's or Semgrep-taint's job.
- Letting semgrep or CodeQL versions float to `latest` in CI, so rule updates change the gate without a reviewable diff.
- Excluding `tests/` entirely: hardcoded-credential rules must still run there, because fixtures leak real secrets more often than production code does.
- Suppression comments that restate the finding ("bandit flags this") instead of arguing why it is safe.

## Definition of done

- [ ] ruff `S` rules enabled in `pyproject.toml` and green in the CI `validate` job.
- [ ] Semgrep runs diff-aware on PRs with the pinned rulesets plus repo-specific rules under `.semgrep/`, each custom rule with passing rule tests.
- [ ] CodeQL runs on the default branch and a weekly schedule, action pinned by full SHA, `security-events: write` scoped to that job only.
- [ ] Zero new HIGH findings in the PR; the check fails the build, not just annotates it.
- [ ] Every suppression carries the specific rule id and a substantive justification; temporary ones reference an issue and an expiry.
- [ ] Every fixed finding has a regression test that failed before the fix.
- [ ] Per-rule false-positive rates reviewed; rules above the noise budget tuned or demoted with the decision recorded via `save_decision`.
