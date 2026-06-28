# Mutation Testing

Mutation testing measures whether the test suite actually detects defects, not merely whether it executes lines. The tool injects small faults (mutants) into the code under test, reruns the suite against each one, and reports which mutants the tests killed and which survived; a surviving mutant is a concrete, located defect the suite would have shipped. Use it as the assertion-quality gate that sits above line and branch coverage, which only prove code ran, not that anything was checked.

## What it measures: score, and mutant outcomes

Every mutant lands in exactly one bucket. Read them precisely, because reviewers routinely conflate the last two.

- Killed (detected): at least one test failed while the mutant was active. The goal.
- Survived: the full suite passed with the fault present. Direct evidence of a missing or weak assertion. This is the number you act on.
- Timeout: the mutant caused a hang (for example a flipped loop bound). Counted as killed: divergence was detected, just via the time guard rather than an assertion.
- No coverage: no test executed the mutated line. This is a coverage gap, not an assertion gap. Fix it by first adding a test that reaches the line; decide whether it belongs in unit, integration, or E2E using `the_test_pyramid_target_distribution` and `integration_and_e2e_testing`.
- Errored / suspicious / skipped: the mutation produced invalid code or an unrelated runtime error. Excluded from the score.
- Equivalent: behaviourally identical to the original, so unkillable by any test. Reviewed and suppressed, never counted against you.

Two ratios, do not confuse them:

- Mutation score = killed / total generated mutants. Drags in no-coverage mutants, so it blends coverage and assertion quality.
- Test strength = killed / (killed + survived) = killed among covered mutants. This isolates assertion quality from reachability and is the headline QA metric. PITest reports both under exactly these names; track test strength on core logic, mutation score for the whole picture.

## Tools per stack (2026)

Pick the tool for the language and scope it to core, risk, and money-handling modules. Mutating the whole repo is wasteful and slow.

Python, fast everyday loop with mutmut 3.x (`pyproject.toml`):

```toml
[tool.mutmut]
paths_to_mutate = ["src/strategy/", "src/risk/"]
tests_dir = ["tests/"]
```

```bash
mutmut run            # mutate, rerun suite per mutant
mutmut results        # killed / survived / timeout / no-coverage summary
mutmut browse         # TUI to inspect survivors and their diffs
mutmut html           # static report
```

Python, fine-grained operators and distributed runs on large modules with Cosmic Ray 8.x:

```toml
# cosmic-ray.toml
[cosmic-ray]
module-path = "src/risk"
timeout = 30.0
test-command = "pytest -x tests/risk"
[cosmic-ray.distributor]
name = "local"
```

```bash
cosmic-ray init cosmic-ray.toml session.sqlite
cosmic-ray exec cosmic-ray.toml session.sqlite
cr-rate session.sqlite          # prints the survival/score rate, CI-friendly
cr-html session.sqlite > report.html
```

JS/TS with StrykerJS v8.x (`stryker.config.json`):

```json
{
  "testRunner": "vitest",
  "mutate": ["src/**/*.ts", "!src/**/*.spec.ts"],
  "thresholds": { "high": 80, "low": 70, "break": 60 },
  "incremental": true,
  "reporters": ["html", "clear-text", "progress"]
}
```

```bash
npx stryker run                  # full run (nightly)
npx stryker run --since=main     # PR gate: mutate only files changed vs main
```

JVM / JUnit 5 with PITest 1.17.x via the Maven plugin:

```xml
<plugin>
  <groupId>org.pitest</groupId>
  <artifactId>pitest-maven</artifactId>
  <version>1.17.0</version>
  <dependencies>
    <dependency>
      <groupId>org.pitest</groupId>
      <artifactId>pitest-junit5-plugin</artifactId>
      <version>1.2.1</version>
    </dependency>
  </dependencies>
  <configuration>
    <targetClasses><param>com.example.risk.*</param></targetClasses>
    <mutators><mutator>STRONGER</mutator></mutators>
    <mutationThreshold>75</mutationThreshold>
  </configuration>
</plugin>
```

```bash
mvn test-compile org.pitest:pitest-maven:mutationCoverage   # full (nightly)
mvn org.pitest:pitest-maven:scmMutationCoverage             # PR gate: SCM-changed files only
```

Rust with cargo-mutants 25.x:

```bash
cargo install cargo-mutants
cargo mutants                    # full run, exits non-zero if any mutant survives
cargo mutants --in-diff pr.diff  # PR gate: only lines in the diff
```

Go with gremlins (go-gremlins/gremlins v0.5.x) or ooze. Go has no first-class diff mode, so scope by package on PRs:

```bash
gremlins unleash --threshold-efficacy 70 --threshold-mcover 80 ./internal/risk/...
```

```go
// ooze runs as a normal Go test, killing mutants with `go test`.
func TestMutation(t *testing.T) {
    ooze.Release(t, ooze.WithRepositoryRoot("."))
}
```

## Equivalent mutants

Detecting equivalence is undecidable in general, so you cannot automate it away; budget for roughly 5-15% of survivors being equivalent (a `<=`→`<` on a bound that is never hit at the boundary, a reordering with no observable effect). Handle them per mutant, never by lowering the global threshold, which would also hide real survivors. Suppress inline at the source with a reason:

- Stryker: `// Stryker disable next-line all: equivalent, bound unreachable`
- cargo-mutants: `#[mutants::skip]` on the item
- mutmut: `# pragma: no mutate`
- PITest: exclude via config (`excludedMethods`) or an arcmutate `@DoNotMutate` annotation

A rising suppression count is a smell. Review it: most "equivalent" claims are actually a missing assertion the author did not want to write.

## Where it runs in CI

Mutation testing cost is O(mutants x suite runtime); a few thousand mutants against a multi-minute suite is hours. It never sits on the PR critical path as a full run.

- Nightly or weekly scheduled job: full run on core modules, publish the HTML report, track the score trend, and open an issue for each new survivor.
- PR gate: incremental, changed-lines only, using the diff/SCM modes above (`--since`, `scmMutationCoverage`, `--in-diff`). Fail the PR when a line it touches introduces a survivor. This keeps the gate to seconds-to-minutes and prevents fresh code from regressing test strength.
- Cache results between runs (Stryker `incremental`, PITest history files) so unchanged code is not re-mutated.

## Thresholds and ratcheting

- Do not chase 100%. Equivalent mutants make it unreachable, and the last 10% costs more than it returns.
- Targets: test strength 75-85% on core domain, risk, and money-handling logic; 60-70% is acceptable for peripheral code. This lines up with the 70%+ mutation-score floor named in `coverage_a_floor_not_a_finish_line`.
- Set the break threshold to the current measured score, not an aspirational one, so the gate can only hold or improve. Ratchet up in small steps (+2-3 points) as survivors are killed. It is a one-way valve: the number never drops.
- Wire the gate to tool exit codes: PITest `mutationThreshold`, Stryker `thresholds.break`, gremlins `--threshold-efficacy`, cargo-mutants non-zero exit on any survivor.

## Reading a report to find weak assertions

A survivor names the file, line, the original operator, and the mutation applied (relational `<`→`<=`, arithmetic `+`→`-`, conditional-boundary, negate-conditional, return-value or empty-return replacement, void-method-call removal, constant replacement). The mutation tells you the exact assertion that is missing.

- A survived `<`→`<=` on a drawdown or position limit means no test pins the boundary value. Add a test at the threshold and one either side.
- A survived return-value mutant means the caller asserts only that the call did not raise, never the value it returned. This is the classic weak test called out in `common_pitfalls_to_reject`; assert the result.
- A cluster of survivors in one function usually means that function is under-asserted or doing too much. A cluster of no-coverage means a missing path, not a missing assertion; route it back through the pyramid.
- Triage by module risk, not by count: one survivor in position sizing outranks ten in logging.

## Common pitfalls

- Treating line or branch coverage as proof of test quality. Coverage shows code ran; only a killed mutant shows a check exists.
- Running a full mutation pass on every PR. It is hours long; the PR gate must be incremental on changed files only.
- Counting no-coverage mutants against assertion quality, or the reverse. No-coverage is a missing test path; survived is a weak assertion. Fix them differently.
- Suppressing survivors as "equivalent" to hit a threshold. Most are genuine missing assertions; suppression must carry a reason and be reviewed.
- Setting the break threshold above the current score, so the gate is red from day one and gets disabled. Anchor it to the measured value and ratchet up.
- Mutating the whole repository instead of core, risk, and money modules, producing a multi-hour run nobody waits for.
- Mutation testing on a flaky suite: random failures masquerade as kills and inflate the score. Stabilise flakes first (see `flaky_tests`).
- Killing a mutant by loosening the test (broadening a range, removing an assertion) instead of tightening it. That raises the score while weakening the suite.

## Definition of done

- [ ] Mutation testing is configured for the stack with a pinned tool version (mutmut 3.x / Cosmic Ray 8.x, StrykerJS v8.x, PITest 1.17.x, cargo-mutants 25.x, gremlins/ooze) and scoped to core, risk, and money-handling modules.
- [ ] A full run executes on a nightly or weekly schedule, publishes an HTML report, and opens an issue per new survivor.
- [ ] The PR gate runs incrementally on changed lines only (`--since` / `scmMutationCoverage` / `--in-diff`) and fails when changed code introduces a survivor.
- [ ] A break threshold is enforced via tool exit code, anchored to the current measured score and ratcheted upward, targeting 75-85% test strength on core logic.
- [ ] Survivors are triaged by module risk; each is either killed by a new or tightened assertion, or suppressed inline with a documented reason after equivalence review.
- [ ] No-coverage mutants are resolved by adding the missing test at the correct pyramid level, not by suppression.
- [ ] The suite under mutation is stable (no flakes) so kill results are trustworthy.
