---
name: ai-test-hygiene-scan
description: Scans an AI-authored or AI-assisted test diff for self-report gaming — inserted skips, strict-to-permissive assertion weakening, mocks hiding a declared-integration dependency, and unjustified snapshot drift — and isolates a suspicious red or green before either is cited as evidence. Use when reviewing a pull request's test diff at /solomon-review, auditing a headless dev-loop iteration's test changes, or triaging a suddenly-green run before signing off a defect fix.
---

# AI Test-Hygiene Scan

An implementing agent — or a human under deadline pressure — can make a red suite go green by editing the test instead of fixing the code: skip the failing case, loosen the assertion, mock away the dependency the test claimed to exercise, or update a golden file until it agrees with the wrong output. None of these show up in a coverage number or a passing CI badge; the run is green and the report says "done." This skill is the independent scan for exactly that failure mode. It treats the test diff as a thing to audit, not a self-report to trust — the same stance behind independent-evaluator review practice for AI-implemented work: a claim of completion is a hypothesis, and the diff, not the agent's narration, is the evidence. Run it on any change set where the same diff that claims new behavior also edits its own test file.

## When to run it

- At the qa lens of `/solomon-review`, before the suite run is cited as evidence — a green run over a weakened test proves nothing, and `qa_report_the_required_output`'s verdict line should not be built on it.
- On any headless dev-loop iteration where the driving agent reports "tests added" or "tests fixed" for its own change.
- When verifying a defect fix that touches its own regression test — `defect_triage_and_lifecycle`'s closure gate already demands red-then-green; this scan is what confirms the red was a real reproduction and the green is not a rigged one.

## Scan window

Diff against the PR's base with the merge-base (three-dot) form, not the last commit — a weakening introduced early in the branch and never revisited still ships if the scan only looks at the tip:

```bash
git diff main...HEAD -- '*test_*.py' '*_test.py' '*/tests/*.py'
```

Use `git log --follow <test_file>` to recover the file's baseline when it was renamed or moved mid-branch, so the diff window does not silently drop history.

## RF-1 — Skipped or disabled tests inserted

```bash
git diff main...HEAD -- '*test_*.py' '*_test.py' \
  | rg -nP '^\+.*(@pytest\.mark\.skip|@pytest\.mark\.xfail|pytest\.skip\(|@unittest\.skip)'
```

A newly added `skip`/`xfail` marker on a test whose sibling production code changed in the same diff is disqualifying regardless of the reason text attached to it. A legitimate quarantine goes through `flaky_tests`' dedicated `quarantine` marker with a named owner and a fix-by date, never a bare `pytest.mark.skip` — the two are not interchangeable. **Verdict: blocker, always**, independent of risk band. File via `log_issue` with Type Functional.

## RF-2 — Assertion weakened from strict to permissive

Match in two stages: the removed line held a strict assertion, and the added line in the same test replaces it with a permissive one.

```bash
git diff main...HEAD -- '*test_*.py' '*_test.py' | rg -nP '^-.*assert .*(==|!=) '
git diff main...HEAD -- '*test_*.py' '*_test.py' \
  | rg -nP '^\+.*(assert .*is not None|assert .*truthy|pytest\.raises\(Exception\)|assert .* in |\.assert_called\(\)\s*$)'
```

Read both hits against the same test function before concluding a weakening; refactoring `==` into a named helper that still asserts the exact value is not this flag — only a genuine loss of specificity counts. **Verdict:** blocker when the weakened assertion covers a High-risk criterion (RTM risk >= 15 or FMEA RPN >= 200, the same High band `test_planning_and_traceability` uses to size test depth); non-blocking, but still logged, when it covers only an edge-case check. Either way, name the original strict assertion in the filed issue's root-cause field — that line is the evidence, and reconstructing it later from a fix-round diff is unreliable.

## RF-3 — Mock inserted on a dependency the RTM declared Integration or E2E

```bash
git diff main...HEAD -- '*test_*.py' '*_test.py' \
  | rg -nP '^\+.*(unittest\.mock|mock\.patch\(|MagicMock\(|monkeypatch\.setattr\()'
```

Cross-reference every hit against the RTM's `Level` column (`test_planning_and_traceability`) for that test's linked criterion. A test the matrix lists at `integration` or `e2e` level that now mocks the dependency under test has quietly downgraded itself to a unit test while the matrix keeps counting it as integration coverage — the exact gap `mocking_and_isolation_mock_all_external_services`' boundary rule is meant to prevent. **Verdict: blocker, always.** Tag the filed issue `mock-hides-integration`; the fix removes the mock (preferred) or explicitly downgrades the RTM row to `unit` with a recorded reason, never leaves the mismatch standing silently between the matrix and the test file.

## RF-4 — Snapshot or golden-file drift without a requirement change

```bash
git diff --name-only main...HEAD \
  | rg -nP '(__snapshots__/|testdata/golden/|/fixtures/.*\.(json|ya?ml)$|\.golden$)'
```

Open every matched file and check the change against the PR's linked acceptance criteria. A snapshot updated to match new, intentional output is fine; a snapshot updated with no corresponding AC change is the test being taught to agree with whatever the code now produces, bug included. **Verdict:** blocker on a High-risk criterion, non-blocking (but logged) elsewhere — cite the AC in the filed issue either way, so a reviewer can confirm the drift against the requirement rather than against the author's word.

## RF-5 and RF-6 — owned elsewhere, applied here

Two more AI-hygiene signals exist, but their mechanics live in sibling skills; this scan reads their verdicts rather than re-deriving them:

- **Happy-path-only coverage on a multi-branch criterion.** A High-risk criterion whose only tests are positive-path is a gap the canonical boundary checklist and decision-table rule in `test_design_rules` already define precisely — no failure row, no `pytest.raises`, no empty/null/None case. This scan's job is to notice the absence in the diff and route it there; it does not restate the boundary set.
- **Test-implementation symbiosis.** Whether a test that exists actually verifies its criterion is the `covers` / `weak` / `missing` judgment in the traceability matrix owned by `test_planning_and_traceability`. Every RF-1 through RF-4 finding above feeds that column directly: a skip-fenced test cannot read `covers`; a mock-hidden integration test is at best `weak`.

## Isolate before you trust a red — or a green

Before classifying any suite failure, or a suspiciously convenient pass, as real, isolate it: run the single test 3 to 5 times in a clean working tree, on the same commit SHA, with no other tests scheduled and no code change between runs. A failure that clears at least once without a code change is `flaky-suspect`, not a confirmed regression — record the attempts and the outcome, and never promote a fail to pass because a single retry cleared it (`flaky_tests` owns the deflake workflow once isolation confirms the failure's class). The same isolation run catches a rigged green from the other direction: a test that only passes because of order-dependent state leaking from an earlier skipped or mocked sibling will fail the moment it runs alone.

**Threshold: flake rate must stay below 2% in the canonical suite** before this scan can support an unconditional pass recommendation to the qa gate. At or above 2%, treat the run as inconclusive — re-isolate the unstable set before citing the suite as evidence in either direction, and let `ci_quality_gates` enforce the same number as a hard release-gate `FAIL`.

## Verdict matrix

| Flag | Fires on | Verdict | File via |
|---|---|---|---|
| RF-1 | any inserted skip/xfail | Blocker, always | `log_issue`, Type Functional |
| RF-2 | strict -> permissive on a High-risk criterion | Blocker | `log_issue`, name the original assertion |
| RF-2 | strict -> permissive on an edge-case only | Non-blocking, logged | `log_issue` |
| RF-3 | mock on a declared-integration/E2E dependency | Blocker, always | `log_issue`, tag `mock-hides-integration` |
| RF-4 | snapshot/golden drift on a High-risk criterion | Blocker | `log_issue`, cite the AC |
| RF-4 | snapshot/golden drift elsewhere | Non-blocking, logged | `log_issue` |
| flake rate >= 2% | canonical suite, this run | Inconclusive | re-isolate before citing either way |

When several flags fire on the same test, the strictest verdict wins. File every finding through `log_issue` per `defect_triage_and_lifecycle` — there is no separate scan-specific ledger; the project memory is the system of record for every defect this scan surfaces, exactly as it is for every other defect QA finds.

## Common pitfalls

- Scanning only the last commit instead of the merge-base diff, missing a weakening introduced three commits earlier in the same PR.
- Treating a rerun-until-green as evidence the suite is healthy; that is the retry-as-pass pattern `flaky_tests` exists to forbid, and this scan exists to catch when an agent does it silently.
- Flagging RF-3 on a mock whose dependency the RTM never declared Integration or E2E in the first place — check the matrix's `Level` column before filing, or the finding is noise that erodes trust in the scan.
- Accepting a snapshot update as "obviously fine" without opening the diff; the drift that ships a wrong number looks identical to the drift that fixes a copy typo until someone reads it against the AC.
- Re-deriving the boundary checklist or the RTM's covers/weak/missing rule inline instead of citing `test_design_rules` and `test_planning_and_traceability` — this scan routes findings to the skill that owns the mechanics, it does not duplicate them.
- Downgrading a blocker to "just flaky" without running the 3-5x isolation protocol first; an unverified excuse is not a diagnosis and does not clear the gate.

## Definition of done

- [ ] The scan runs against the full PR diff (`git diff main...HEAD`, merge-base form), not just the last commit, with renamed test files traced via `git log --follow`.
- [ ] RF-1 (skip/xfail inserted) and RF-3 (mock on a declared-integration dependency) are checked on every test file in the diff and fire as blockers unconditionally when present.
- [ ] RF-2 (weakened assertion) and RF-4 (snapshot/golden drift) are checked against the RTM's risk band; a High-risk hit is a blocker, an edge-case-only hit is logged non-blocking.
- [ ] RF-5 and RF-6 findings are routed to `test_design_rules` and `test_planning_and_traceability` respectively, never re-derived inline in this scan.
- [ ] Any failure, or a suspiciously convenient pass, is isolated 3-5 times on the same SHA before being classified; the run's flake rate is computed and compared against the 2% threshold before the suite is cited as evidence.
- [ ] Every fired flag is filed through `log_issue` per `defect_triage_and_lifecycle`; no parallel scan-specific bug file exists anywhere in the repository or the review artifacts.
- [ ] The qa lens's review record states which flags fired, their verdicts, and the measured flake rate — not just an aggregate pass/fail count.
