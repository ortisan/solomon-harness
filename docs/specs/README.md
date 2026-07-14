# Specs

This directory holds one structured spec document per issue,
`docs/specs/<N>-<slug>.md`, generated from the issue body at creation time so
an issue's intent survives past its GitHub description.

## How they are created

`/solomon-issue` generates the spec automatically, right after `gh issue
create` returns the issue number, via:

```
uv run python -m solomon_harness.spec_doc generate --issue <n> --title "<title>" \
  --body-file <path> [--adr "<ADR text>"]
```

This writes `docs/specs/<n>-<slug>.md` into the working tree and prints a
one-line note that the file was created and is uncommitted. Generation is
write-only: it performs no `git commit` and no `git push`. The spec rides into
the repository through the author's normal flow — typically committed on the
feature branch at `/solomon-start`, alongside the code and any ADR the change
warrants.

## The seven canonical headings

Every spec carries these headings, in this order: Context, Problem,
Requirements, Acceptance Criteria, Design Constraints, Out of Scope,
Traceability. See `0000-spec-template.md` for the guidance in each.

## Generate-once vs. hand-edit-after

The generator maps the issue body onto the seven headings once, at creation
time. It is not regenerated on every issue edit: after generation, the spec is
a normal tracked file, and the author is expected to hand-edit it as the
implementation plan sharpens (for example, filling in a `TBD (refine)`
placeholder left by a section the issue body did not derive content for).

## Validation

`scripts/spec-lint.py` checks that every file in this directory (other than
this README and the template) has a filename starting with its issue number
and carries all seven headings. It runs in CI next to the ADR and workflow
validators.

## Ownership

The spec is owned by whoever is driving the issue at the time — `product_owner`
at creation, `software_architect` if an ADR is added, and the implementing
agent through delivery. It is not a separate approval artifact: the issue and
its linked PR remain the source of truth for status.
