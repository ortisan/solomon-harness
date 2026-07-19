# Behavioral subagent evaluations

The behavioral evaluation adapter compares two generated-subagent configurations
against the same versioned task set. It is opt-in and offline. The active host owns
model invocation, credentials, cancellation, and containment; the repository only
prepares bounded fixtures and processes recorded evidence.

This pilot is directional. Three repetitions can reveal a large, repeatable failure,
but they do not establish statistical significance or production performance. A
comparison never changes routing, generated-agent policy, model selection, merge,
release, or issue status.

## Workflow

Prepare one fresh scratch directory for every case, arm, and repetition:

```bash
uv run python -m solomon_harness.behavioral_evals prepare \
  --manifest tests/fixtures/behavioral_evals/manifest.json \
  --scratch-root /absolute/operator-selected/scratch
```

The command prints the prepared run identities and physical paths. Those paths are
operational data and are not part of canonical evaluation evidence. The host should
run baseline and candidate in paired, interleaved blocks, use a new model session for
every repetition, and change only the treatment under evaluation. Do not reuse a
scratch directory or conversation context.

The host then writes one closed `recorded-runs.json` artifact containing its run
evidence and separately exposed usage records. Score and compare it locally:

```bash
uv run python -m solomon_harness.behavioral_evals score \
  --manifest tests/fixtures/behavioral_evals/manifest.json \
  --recordings /absolute/operator-selected/recorded-runs.json \
  --output /absolute/operator-selected/results.json

uv run python -m solomon_harness.behavioral_evals compare \
  --manifest tests/fixtures/behavioral_evals/manifest.json \
  --recordings /absolute/operator-selected/recorded-runs.json \
  --output /absolute/operator-selected/comparison.json
```

Output files are created exclusively with mode `0600`. Existing files, symlinks, and
non-regular targets are preserved and rejected. Parsing, scoring, and comparison
finish before the output path is opened, so invalid or incomplete evidence creates no
report.

## Evidence contract

A qualifying manifest has schema version 1, the exact `baseline` and `candidate`
arms, at least nine cases, and exactly three repetitions. The initial nine-case set
therefore contains 54 run identities; the general formula is `6 × case count`.

Each run reports:

- golden-set and case versions, arm, and repetition;
- generated-agent content and effective policy;
- host, provider, model, model version, and effort;
- duration in integer milliseconds and exit status;
- observed files and inert action identifiers;
- scratch-only containment plus before/after digests for the source checkout,
  project memory, and GitHub state.

The scorer derives content and policy SHA-256 digests. Recorded actions are never
dispatched or interpreted as paths. A denied protected mutation attempt is still a
failed isolation assertion. Containment and host/model identity are self-reported
evidence, not cryptographic attestation.

Usage is a separate envelope keyed by run identity. Input, output, and cache values
are integer tokens; reported cost is integer microdollars, or millionths of one US
dollar. Unsupported fields are JSON `null`. An observed zero remains zero. A unique
all-null envelope is attributable because attribution measures identity correlation,
not metric availability.

Schemas are closed: unknown fields, unsupported versions, unsafe paths, duplicate
JSON keys, non-finite numbers, excessive nesting or integer size, special files,
symlinks, and values above the declared hard limits fail closed. Any field or semantic
change requires a new schema version. Golden-set content changes require a new
`golden_set_version`.

## Comparison rules

Comparison re-scores the raw recordings in-process. It does not trust an editable
result verdict. Before calculating statistics it proves the exact Cartesian matrix;
missing, duplicate, or unexpected repetitions return `incomplete_comparison` and no
`eligible` field or report artifact.

Pass rate is represented by the exact `passed_runs` and `total_runs` counts. p50 is
the median of every arm run, including failures. p95 uses nearest rank with
`rank = ceil(0.95 × n)`, calculated using integer arithmetic. With 27 observations,
p50 is the 14th sorted value and p95 is the 26th.

A golden case is stable only when all three baseline repetitions pass. Every failed
candidate repetition for such a case is reported separately with its failed
assertion. Eligibility is false when any of these conditions holds, in this order:

1. candidate passed-run count is below baseline;
2. at least one stable golden-case regression exists;
3. fewer than 95 percent of host-exposed usage records resolve uniquely to a complete
   run identity.

When the host exposes no usage envelopes, attribution is `not_evaluable` rather than
zero and does not by itself block eligibility. With 54 exposed records, 52 attributed
records meet the threshold and 51 do not. Duplicate envelopes for one identity are
ambiguous, so every duplicate for that identity is unattributed.

The report is canonical JSON: sorted object keys, UTF-8, no non-finite values, and no
timestamps or physical scratch paths. Identical accepted manifest and recording
evidence produces byte-identical result and comparison artifacts.

## Performance interpretation

The corpus fitness check measures local parsing, normalization, and scoring time
outside the production artifact. Preparation, filesystem I/O outside the bounded
artifact read, CLI parsing, comparison, serialization, and host invocation are
excluded. The median local processing time per run must remain below one percent of
the recorded host wall time. Timing measurements are test evidence only and are not
serialized into canonical output.

The adapter imports no provider SDK, opens no network connection, invokes no
subprocess, and reads or writes neither project memory nor GitHub. Normal `compile`
and the repository test suite do not invoke this module or create paid evaluation
artifacts.
