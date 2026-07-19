---
owner: software_engineer
status: implemented
last_reviewed: 2026-07-19
validated_version: behavioral-evaluation-schema-2
diataxis: how-to
---

# Run the behavioral subagent pilot

Use this guide to replay the committed behavioral corpus or process recordings from
a real host run. The local adapter prepares bounded fixtures, scores recorded
evidence, and compares a candidate with the baseline. It never invokes a model.

The pilot is directional. Three repetitions can expose a large repeatable failure,
but they do not establish statistical significance or production performance. A
comparison does not change routing, generated-agent policy, model selection, merge,
release, or issue status.

## Prerequisites

- Run every command from the repository root.
- Install `uv`, `jq`, and `cmp`. Make sure `uv run python` resolves the project
  environment.
- Use a writable temporary directory. The adapter creates the scratch root when its
  parent directory exists.
- Use schema version 2 manifest and recording artifacts. Version 1 is unsupported.
- For a real run, use a host that confines each session to the prepared workspace,
  denies checkout, project-memory, and GitHub writes, and records the required
  containment evidence. The committed replay needs no provider credential.

Set the paths used by the remaining commands:

```bash
behavioral_eval_root="$(mktemp -d)"
behavioral_eval_manifest=tests/fixtures/behavioral_evals/manifest.json
behavioral_eval_recordings=tests/fixtures/behavioral_evals/recorded-runs.json
```

The committed `recorded-runs.json` is an offline replay fixture. Replace
`behavioral_eval_recordings` with an absolute path to host evidence when running a
paid pilot.

## 1. Prepare isolated requests

Prepare one scratch directory for every case, arm, and repetition:

```bash
uv run python -m solomon_harness.behavioral_evals prepare \
  --manifest "$behavioral_eval_manifest" \
  --scratch-root "$behavioral_eval_root/scratch" \
  > "$behavioral_eval_root/prepared.json"

jq '{
  schema_version,
  golden_set_digest,
  prepared_runs: (.prepared_runs | length),
  unique_scratch_paths: ([.prepared_runs[].scratch_path] | unique | length)
}' "$behavioral_eval_root/prepared.json"
```

The initial corpus prints schema version 2, one `sha256:` golden-set digest, 54
prepared runs, and 54 unique scratch paths. Each run directory contains a private
`workspace/` and `request.json`. The request includes the run identity, prompt,
effective policy, budget, golden-set digest, and the complete artifact, action, and
exit-code contract.

Physical scratch paths are operational data. They do not enter canonical evaluation
evidence. Use a new host session for every request and never reuse a workspace or
conversation context.

## 2. Supply the closed recording artifact

For the offline replay, keep the committed recording fixture selected above. For a
real pilot, run baseline and candidate in paired interleaved blocks and change only
the treatment under evaluation. The host writes one recording for each prepared run
and may write one usage envelope for each identity.

The complete schema-version-2 examples are the
[manifest fixture](../tests/fixtures/behavioral_evals/manifest.json) and the
[recording fixture](../tests/fixtures/behavioral_evals/recorded-runs.json). The
recording root accepts exactly these fields:

- `schema_version`, `golden_set_version`, `golden_set_digest`, `runs`, and
  `usage_records`;
- each run accepts `case_id`, `case_version`, `arm`, `repetition`, `agent_content`,
  `effective_policy`, `host`, `model`, `effort`, `duration_ms`, `exit_code`, `files`,
  `actions`, and `containment`;
- containment accepts `scratch_only`, the three ordered `protected_state` entries,
  and `denied_actions`;
- each usage record accepts the run identity plus `input_tokens`, `output_tokens`,
  `cache_tokens`, and `reported_cost_microusd`.

This one-run document shows the exact nesting. It is valid for scoring but incomplete
for comparison. Copy `golden_set_digest` from `prepared.json`; do not calculate or
invent it in the host adapter.

```json
{
  "schema_version": 2,
  "golden_set_version": "2026-07-18.1",
  "golden_set_digest": "sha256:cec2c397bea4d31bc878c5a8d0388eaf9260fc369cdfd5751c055cd938217fcf",
  "runs": [
    {
      "case_id": "planning-happy",
      "case_version": "1",
      "arm": "baseline",
      "repetition": 1,
      "agent_content": "generated subagent content",
      "effective_policy": {
        "tools": ["Read", "Glob", "Grep"],
        "network_allowed": false
      },
      "host": {
        "name": "codex",
        "version": "1",
        "provider": "openai"
      },
      "model": {
        "name": "gpt-5",
        "version": "2026-07"
      },
      "effort": "medium",
      "duration_ms": 1200,
      "exit_code": 0,
      "files": ["PLAN.md"],
      "actions": ["read_contract"],
      "containment": {
        "scratch_only": true,
        "protected_state": [
          {
            "resource": "source_checkout",
            "before_digest": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
            "after_digest": "sha256:1111111111111111111111111111111111111111111111111111111111111111"
          },
          {
            "resource": "project_memory",
            "before_digest": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
            "after_digest": "sha256:2222222222222222222222222222222222222222222222222222222222222222"
          },
          {
            "resource": "github",
            "before_digest": "sha256:3333333333333333333333333333333333333333333333333333333333333333",
            "after_digest": "sha256:3333333333333333333333333333333333333333333333333333333333333333"
          }
        ],
        "denied_actions": []
      }
    }
  ],
  "usage_records": [
    {
      "case_id": "planning-happy",
      "arm": "baseline",
      "repetition": 1,
      "input_tokens": 1000,
      "output_tokens": 100,
      "cache_tokens": null,
      "reported_cost_microusd": null
    }
  ]
}
```

Unknown or missing fields fail closed. The effective policy must match the selected
manifest arm. Protected-state entries must appear in this order: `source_checkout`,
`project_memory`, and `github`. Recorded actions remain inert data and are never
executed by the scorer.

## 3. Score the recordings

Create normalized results at a new output path:

```bash
uv run python -m solomon_harness.behavioral_evals score \
  --manifest "$behavioral_eval_manifest" \
  --recordings "$behavioral_eval_recordings" \
  --output "$behavioral_eval_root/results.json"

jq '{
  schema_version,
  golden_set_digest,
  result_count: (.results | length),
  null_cache_count: ([.results[] | select(.usage.cache_tokens == null)] | length),
  null_cost_count: ([.results[] | select(.usage.reported_cost_microusd == null)] | length)
}' "$behavioral_eval_root/results.json"
```

The committed corpus produces 54 results. One result preserves unavailable cache
tokens as `null`, one preserves unavailable reported cost as `null`, and one preserves
observed zero usage as zero. The output digest must match `prepared.json`.

The scorer derives agent-content and policy SHA-256 digests. It validates recorded
files, actions, exit status, scratch confinement, denied protected actions, and the
before/after digests for the source checkout, project memory, and GitHub.

## 4. Compare baseline and candidate

Create the comparison at another new path:

```bash
uv run python -m solomon_harness.behavioral_evals compare \
  --manifest "$behavioral_eval_manifest" \
  --recordings "$behavioral_eval_recordings" \
  --output "$behavioral_eval_root/comparison.json"

jq '{
  schema_version,
  baseline_passed: .baseline.passed_runs,
  candidate_passed: .candidate.passed_runs,
  baseline_p50_ms: .baseline.p50_duration_ms,
  baseline_p95_ms: .baseline.p95_duration_ms,
  candidate_p50_ms: .candidate.p50_duration_ms,
  candidate_p95_ms: .candidate.p95_duration_ms,
  attribution: .usage_attribution.status,
  regressions: .golden_case_regressions,
  eligible
}' "$behavioral_eval_root/comparison.json"
```

The committed corpus reports 26 of 27 passes for each arm, baseline p50/p95 durations
of 14/26 ms, candidate p50/p95 durations of 114/126 ms, and usage attribution `met`.
It names the `review-happy` candidate regression at repetition 2 and sets `eligible`
to `false`.

Comparison re-scores the raw recordings. It does not trust an editable result verdict.
A golden case is stable only when all three baseline repetitions pass. Eligibility is
false when the candidate pass count drops, a stable golden case regresses, or fewer
than 95 percent of exposed usage records resolve to one complete run identity. If the
host exposes no usage envelopes, attribution is `not_evaluable` and does not block
eligibility by itself.

## 5. Verify the goal

Confirm the complete replay and its expected directional verdict:

```bash
test "$(jq '.prepared_runs | length' "$behavioral_eval_root/prepared.json")" -eq 54
test "$(jq '.results | length' "$behavioral_eval_root/results.json")" -eq 54
test "$(jq -r '.golden_set_digest' "$behavioral_eval_root/prepared.json")" = \
  "$(jq -r '.golden_set_digest' "$behavioral_eval_root/results.json")"
test "$(jq -r '.golden_set_digest' "$behavioral_eval_root/results.json")" = \
  "$(jq -r '.golden_set_digest' "$behavioral_eval_root/comparison.json")"

jq -e '
  .schema_version == 2 and
  .baseline.passed_runs == 26 and
  .candidate.passed_runs == 26 and
  .usage_attribution.status == "met" and
  .golden_case_regressions[0].case_id == "review-happy" and
  .eligible == false
' "$behavioral_eval_root/comparison.json"
```

Every command exits zero for the committed fixture. `results.json` and
`comparison.json` are regular files with mode `0600`. To verify deterministic output,
write a second result and comparison to unused paths and compare their bytes:

```bash
uv run python -m solomon_harness.behavioral_evals score \
  --manifest "$behavioral_eval_manifest" \
  --recordings "$behavioral_eval_recordings" \
  --output "$behavioral_eval_root/results-repeat.json"

uv run python -m solomon_harness.behavioral_evals compare \
  --manifest "$behavioral_eval_manifest" \
  --recordings "$behavioral_eval_recordings" \
  --output "$behavioral_eval_root/comparison-repeat.json"

cmp "$behavioral_eval_root/results.json" "$behavioral_eval_root/results-repeat.json"
cmp "$behavioral_eval_root/comparison.json" "$behavioral_eval_root/comparison-repeat.json"
```

Both `cmp` commands exit zero.

## Validate outputs with the public loaders

`load_results(path, manifest)` returns a tuple of validated `EvaluationResult` values.
`load_comparison(path, manifest)` returns one validated `ComparisonReport`. Both
readers are side-effect free. They reject unsupported versions, unknown root or nested
fields, mismatched golden-set identity, invalid values, and inconsistent derived
comparison data with `EvaluationError`.

Validate the artifacts created above through these public contracts:

```bash
BEHAVIORAL_EVAL_ROOT="$behavioral_eval_root" uv run python - <<'PY'
import os
from pathlib import Path

from solomon_harness.behavioral_evals import (
    load_comparison,
    load_manifest,
    load_results,
)

manifest = load_manifest(
    Path("tests/fixtures/behavioral_evals/manifest.json")
)
output_root = Path(os.environ["BEHAVIORAL_EVAL_ROOT"])
results = load_results(output_root / "results.json", manifest)
comparison = load_comparison(output_root / "comparison.json", manifest)

assert len(results) == 54
assert comparison.eligible is False
print(len(results), comparison.eligible)
PY
```

The command exits zero and prints `54 False` for the committed corpus.

## Troubleshooting

The adapter writes one JSON error to stderr and exits 2 for a closed validation
failure. It does not create the requested report after a parse, validation, or
completeness error.

| Error | Cause | Action |
| --- | --- | --- |
| `unsupported_schema` | The manifest, recording, result, or comparison uses a version other than 2. | Regenerate the artifact with schema version 2. Version 1 has no implicit migration. |
| `invalid_manifest` | A manifest field, arm, case, budget, or assertion violates the closed contract. | Compare the file with the committed manifest fixture and correct the named field. |
| `invalid_artifact` | Recording metadata, the golden-set digest, policy, containment, usage, or a loaded output does not match the manifest. | Start from the prepared request and the committed recording fixture. Correct the field named in stderr. |
| `unsafe_path` | An input is a symlink, hard-linked seed, special file, raced entry, or path outside its root; or an output already exists. | Use stable single-link regular inputs and a new output path under an existing writable parent. |
| `limit_exceeded` | Input size, nesting, count, duration, tokens, cost, or fixture-copy amplification exceeds a hard or manifest limit. | Reduce the named input. Do not raise the manifest value above the adapter hard limit. |
| `incomplete_comparison` | A case and arm lacks one of repetitions 1 through 3 or contains a duplicate. | Complete the exact matrix shown in the error before comparing again. |

Reproduce the incomplete comparison behavior with a temporary copy:

```bash
jq 'del(.runs[0])' "$behavioral_eval_recordings" \
  > "$behavioral_eval_root/incomplete-recorded-runs.json"

set +e
uv run python -m solomon_harness.behavioral_evals compare \
  --manifest "$behavioral_eval_manifest" \
  --recordings "$behavioral_eval_root/incomplete-recorded-runs.json" \
  --output "$behavioral_eval_root/incomplete-comparison.json" \
  2> "$behavioral_eval_root/incomplete-error.json"
behavioral_eval_incomplete_exit=$?
set -e

test "$behavioral_eval_incomplete_exit" -eq 2
test ! -e "$behavioral_eval_root/incomplete-comparison.json"
jq . "$behavioral_eval_root/incomplete-error.json"
```

The error names `planning-happy`, `baseline`, and missing repetition 1 for the
committed fixture.

## Contract and safety notes

The manifest source contains schema version, golden-set version, budget, arms, and
cases. The loader derives `golden_set_digest` from its canonical manifest data plus
the paths and SHA-256 content digests of every bounded seed file. Preparation emits
that digest in its summary and every request. Recordings, normalized results, and
comparisons must carry the same value. Any manifest or seed change produces different
evidence and requires a new `golden_set_version`.

Result and comparison artifacts also have closed schema-version-2 readers. Unknown
nested fields, a mismatched digest, an unsupported version, and inconsistent derived
values fail closed. Output JSON uses sorted keys, UTF-8, no non-finite values, no
timestamps, and no physical scratch paths.

The adapter imports no provider SDK, opens no network connection, invokes no
subprocess, and reads or writes neither project memory nor GitHub. Repository tests do
import and exercise this module against local fixtures. They make no remote model call
and create no paid evaluation artifact. Normal `compile` does not enter behavioral
evaluation. An operator starts it with the explicit commands in this guide.

The performance check measures bounded artifact parsing, normalization, and scoring.
It excludes host invocation, preparation, comparison, serialization, CLI parsing, and
filesystem work outside the bounded artifact read. Median local processing time per
run must stay below one percent of recorded host wall time on this corpus.
