# ADR-0041: register new agents directly in the installed harness

- Status: accepted
- Date: 2026-07-16
- Deciders: maintainer, software_architect, practice_curator, agent_builder, security
- Issue: maintainer request on 2026-07-16
- Amends: ADR-0008 and ADR-0036

## Context and problem statement

The capability broker treated both acquisition kinds as reviewed repository
changes. Even when a gap required only a new local specialist, `create_agent`
entered `apply_proposal`, created a branch and commit in the consumer project,
and opened a pull request. ADR-0036 has since established
`.agents/solomon/agents` as the canonical specialist catalog of an installed
harness. A harness-local scaffold and a pinned external-content adaptation now
have different trust and ownership boundaries and should not share one GitHub
side-effect contract.

The decision must preserve the permanent human gate and fail-closed path
confinement while preventing the consumer project's delivery history from being
used as a registry for locally created harness agents.

## Decision drivers

- Register the new specialist where the active harness discovers specialists.
- Leave the consumer project's branch, commits, refs, and GitHub pull requests
  unchanged for a local scaffold.
- Preserve security review for fetched external content.
- Keep package-owned installed files upgradeable without treating local
  registration as core drift.
- Preserve deterministic Claude, AGY, and Codex discovery and require an
  explicit session restart instead of runtime hot-swap.
- Fail closed when the caller is not a valid installed consumer.

## Considered options

- Keep one reviewed-PR pipeline for both `adapt_skill` and `create_agent`.
  Rejected because it creates the exact consumer-project PR that the local
  registration is intended to avoid and conflates two trust classes.
- Open the creation PR in the Solomon Harness source repository or a central
  agent registry. Rejected because merging a remote definition does not
  register it in the currently installed consumer and introduces release and
  synchronization dependencies.
- Register `create_agent` directly in the repository-local installed harness,
  while retaining the reviewed-PR pipeline for `adapt_skill`. Chosen because
  the installed catalog is the active discovery source and external content
  remains isolated behind review.

## Decision outcome

Chosen option "direct installed registration for `create_agent` and reviewed PR
for `adapt_skill`".

The interactive acquisition gate remains mandatory for both actions.
`create_agent` requires a valid install manifest and writes the scaffold only to
`.agents/solomon/agents/<name>`. The agent builder recompiles the three native
host adapters, then the broker returns `mode: direct_registration`, the confined
`agent_path`, and `restart_required: true`. It does not invoke the proposal
pipeline, create or switch a branch, commit files, call GitHub, or write a
pull-request handoff. A best-effort project-memory decision records the local
registration.

The installed `.agents/solomon/AGENTS.md` remains package-owned and byte-stable.
The new canonical source directory is a consumer-owned extension that is not
claimed by the package manifest; upgrades preserve unowned paths. Generated
host adapters remain manifest-owned as adapters and are reconciled from the
complete catalog. Uninstall therefore preserves the consumer-owned agent source
while removing unchanged Solomon-owned adapters. If a later harness release
introduces the same canonical path, installation preserves the local bytes and
reports a blocking conflict instead of overwriting them.

`adapt_skill` continues through `apply_proposal`, with allowlisted and pinned
provenance, a single-agent draft PR, and security review. Brokered direct agent
creation is refused in a harness source checkout or any workspace with a
missing, malformed, or unsupported install manifest; native harness agents must
still be developed through the normal reviewed lifecycle.

The source write and adapter reconciliation run under the installed-operation
lock with a compare-and-swap rollback snapshot. If a scaffold fails or adapter
compilation reports a conflict, the broker restores the source, every adapter,
and the manifest to their pre-registration state and propagates the failure.
Each owned write is checkpointed at publication time; rollback preserves and
reports any path that an external writer changed afterward. Scaffold files are
completed and flushed in same-directory temporaries, then published create-only
with an exact file and inode proof, so partial I/O never exposes a truncated
agent and a pre-checkpoint replacement is not claimed by the transaction.
Symlinked scaffold files or parents are refused. It never deletes a directory
that existed before the attempt or mutates scaffolding in another consumer-owned
agent. Runtime hot-swap remains out of scope, so workflows stop after successful
registration and tell the user to start a new session.

### Consequences

- Positive: consumer projects no longer receive agent-creation branches,
  commits, or pull requests, and the new agent becomes discoverable by all three
  hosts from the installed canonical catalog.
- Positive: package-owned rules remain upgrade-safe, external skills retain
  security review, and invalid installations fail before a scaffold begins.
- Negative: the local agent source is not propagated through the consumer
  project's reviewed Git history or the package manifest; teams that need a
  shared specialist must distribute it through a separate explicit workflow.
- Negative: the current host session cannot load the new agent, so registration
  interrupts the stage and requires a restart.
- Follow-up: a future shared-agent publishing contract may add an explicit
  export/import flow without changing direct local registration.

## More information

This decision amends ADR-0008's blanket reviewed-PR acquisition rule and
ADR-0036's installed ownership model. Its fitness functions cover the broker
CLI result shape, unchanged Git refs, absence of GitHub calls, package-roster
preservation, adapter ownership, upgrade preservation, rollback, and session
restart reporting. This decision is also recorded in project memory via
`save_decision`.
