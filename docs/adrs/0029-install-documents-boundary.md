# ADR-0029: installed projects receive no harness documents

- Status: accepted
- Date: 2026-07-14
- Deciders: maintainer, software_architect
- Issue: #234 (surfaced during its review; target layout tracked as #240)

## Context and problem statement

`solomon-harness init` copied the harness's entire `docs/` tree — its 27+
decision records, its specs, its wiki pages — and its root `README.md` into
every installed project. A child project therefore woke up carrying another
product's architectural history as if it were its own, defeating the purpose
of per-project `docs/adrs/` and `docs/specs/` trees (ADR-0028) and leaking
harness-internal documents into every customer repository.

## Decision drivers

- A child project's records must be its own: empty trees at install, filled
  only by that project's decisions and specs.
- The harness's documents describe the harness — shipping them mislabels
  their authority and pollutes every install.
- The commands read operating conventions (`docs/solomon-workflow.md`) at run
  time, so wherever those live must eventually be host-agnostic and bundled
  with the tooling, not with the child's documents.

## Considered options

- Copy `docs/` wholesale (the shipped behavior). Rejected: it is the defect —
  harness records, specs, wiki, and README masquerade as the child's.
- A whitelist of operating documents (`solomon-workflow.md`,
  `release-policy.md`, `loop-engineering.md`, `docs/templates/`) plus empty
  record trees. Rejected by the maintainer: even operating documents are the
  harness's, and `docs/` of a child project is the child's document space.
- Scaffolding only: the child's `docs/` receives exactly its own empty
  `adrs/` and `specs/` trees (each convention's 0000 template and README),
  and every other document stays home. Chosen.

## Decision outcome

Chosen option "scaffolding only". `_install_docs_skeleton` seeds
`docs/adrs/` and `docs/specs/` with each tree's template and README and
copies nothing else; the harness root `README.md` no longer travels; the
covering test asserts the exact listing of the installed `docs/` payload.

### Consequences

- Positive: a child's `docs/` is entirely its own from the first commit; no
  harness document ever masquerades as project history.
- Negative (interim, accepted by the maintainer): the `/solomon-*` command
  prompts reference `docs/solomon-workflow.md`, which a fresh install no
  longer carries — until #240 re-homes the operating conventions into the
  host-agnostic tooling layer (`.agents/solomon`) and repoints the prompts,
  installed projects run on the command text alone.
- Follow-ups: #240 (the `.agents/solomon` layout: conventions re-homed,
  issue/PR templates delivered to the child's `.github/`, hosts pointed at
  `.agents/` via thin generated adapters).

## More information

Enforcement: `solomon_harness/bootstrap.py` (`_install_docs_skeleton`,
`DOCS_RECORD_TREES`) and `tests/test_bootstrap.py::TestInstallDocsBoundary`.
Companion record: ADR-0028 (the `docs/adrs` home and the spec-driven
convention). This decision is also recorded in the project memory via
`save_decision`.
