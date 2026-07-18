# Spec 240: host-agnostic tooling layer under .agents/solomon

- Issue: #240 · Status: implemented
- Date: 2026-07-15 · Author: product_owner, software_architect, loop_engineer

## Context

The install audit found that a consumer repository receives complete harness trees,
host-local state, and Python project metadata at its root. The maintainer requires one
bounded tooling home and equal functionality in Claude, AGY, and Codex.

## Problem

Harness implementation, runtime state, and consumer product files currently share the
same namespace. This obscures ownership, makes upgrades destructive, permits local files
from the source checkout to leak into installs, and leaves host behavior inconsistent.

## Requirements

1. Every canonical harness file installed into a repository lives under
   `.agents/solomon`; mutable state lives under `.agents/solomon/state`.
2. Files outside `.agents` are limited to project-owned scaffolds and the smallest native
   discovery adapters required by Claude, AGY, Codex, GitHub, and Git.
3. Claude, AGY, and Codex expose the same specialist, workflow, MCP, lifecycle-hook,
   loop-guard, and headless-stage capabilities from one neutral source.
4. Install, compile, upgrade, and uninstall are deterministic and ownership-safe.
5. Existing tenant configuration and memory state migrate without loss, with one release
   of legacy read fallback.
6. The packaged payload is built from an explicit allowlist and excludes source worktrees,
   local settings, locks, secrets, databases, caches, and symlink escapes.
7. The installed project's own `docs`, `.github`, host configuration, and instructions
   are never deleted by upgrade or uninstall.
8. The cross-worktree driver lock and budget remain anchored in Git's common directory;
   this shared safety state is not a repository payload and is not moved per worktree.

## Implementation Pointers

- `solomon_harness/bootstrap.py:_install_harness_files` currently uses `copytree` over
  repository directories. Replace it with `install_layout.install_project` and return
  early from the external-project bootstrap after safe project configuration.
- `scripts/generate-integrations.py:generate` and
  `solomon_harness/workflows.py:_read_command_file` currently make `.claude/commands`
  authoritative. Route both through the neutral workflow location and the shared host
  adapter contract.
- `solomon_harness/workflows.py:run_stage` accepts only `claude` and `agy`. Add Codex with
  `codex exec -` and keep Claude-only allowed-tool flags isolated to the Claude adapter.
- `solomon_harness/tools/database_client.py:_load_config` and the config readers in
  memory, policy, notification, and health modules hardcode `.agent/config.json`. Read
  `.agents/solomon/config/project.json` first and keep the legacy path as fallback.
- Install `solomon_harness/`, `scripts/`, `pyproject.toml`, and `uv.lock` directly under
  `.agents/solomon`, so every hook can execute with `uv run --project .agents/solomon`.
- Build a deterministic manifest with repository-relative paths and SHA-256 hashes. Use
  it as the only authority for overwrite, stale-file removal, and uninstall.
- Package the same allowlisted source payload into `solomon_harness/_payload` during the
  wheel build; source and wheel installation must call the same installer.

## Acceptance Criteria

```gherkin
Scenario: Fresh installation has an exact boundary
  Given an empty consumer repository
  When solomon-harness init completes
  Then canonical harness content exists only below .agents/solomon
  And only native thin adapters and project-owned scaffolds exist outside .agents
  And no source-local, secret, lock, database, cache, worktree, or harness project file leaks

Scenario: All three hosts have behavioral parity
  Given a completed installation
  When Claude, AGY, and Codex discover the project
  Then each exposes the same workflows and specialists
  And each invokes the same MCP server, lifecycle resume, and loop guard semantics
  And each can run every delivery stage headlessly through its native CLI

Scenario: Repeated operations are deterministic
  Given an installed project with unrelated host configuration
  When init and compile each run twice
  Then the second run changes no managed bytes or modification times
  And unrelated configuration remains unchanged

Scenario: A legacy install migrates safely
  Given a legacy root-layout install with tenant configuration and memory state
  When init migrates it
  Then configuration and state exist below .agents/solomon with unchanged data
  And only recognized, unmodified legacy Solomon files are removed
  And modified or unrelated files are preserved and reported

Scenario: Uninstall obeys ownership
  Given an installed project with one modified managed adapter and unrelated host files
  When solomon-harness uninstall runs
  Then only unchanged manifest-owned files and Solomon-owned configuration entries are removed
  And the modified adapter, unrelated files, config, and state remain

Scenario: Source and wheel installs match
  Given the source checkout and a wheel built from the same commit
  When each installs into an equivalent empty repository
  Then their managed manifests and file hashes are identical
```

## Verification

Run `uv run pytest -q`, `uv run ruff check solomon_harness tests scripts setup.py`,
`uv run mypy solomon_harness`, and
`uv run python scripts/spec-lint.py docs/specs/240-host-agnostic-tooling-layer.md`.
The packaging test builds and installs a wheel in a temporary directory and compares the
manifest to an editable/source-mode install. Host smoke tests parse every generated JSON
and TOML file and inspect the installed CLIs' discovery surfaces without model calls.

## Design Constraints

Use a hexagonal core with host renderers as adapters. Host files may contain metadata,
paths, and native configuration but no canonical workflow logic. Prefer generated text
stubs over symlinks for Windows and archive compatibility. Merge namespaced configuration
and fail closed on path confinement, malformed managed state, or modified owned files.
Never bypass Codex hook trust or the existing human gates for merge, release, and Done.
Fresh installs use AGY's `.agents` surfaces and never create `.gemini`.

## Out of Scope

Changing the product-specific delivery lifecycle, removing project-owned ADR/spec
scaffolding, publishing to PyPI, automatically trusting host hooks, merging a pull request,
or cutting a release.

## Traceability

- Issue: #240
- ADR: docs/adrs/0036-host-neutral-installed-harness.md
- PR: #288

## Implementation Evidence

- Full suite: 2,095 passed, 1 skipped, with 81.30% branch coverage against an
  80% repository gate. The host-neutral core reports 98% focused branch coverage
  against its 90% gate.
- Static gates: Ruff, mypy across 142 source files, ADR/spec/workflow/agent/template/
  skill validation, `uv lock --check`, `bash -n`, and `git diff --check` passed.
  The incremental SAST gate found no new Ruff security findings across 10,401
  changed production lines.
- Repeated source compilation: zero changed files, zero conflicts, 114 managed
  adapter paths.
- Real consumer install audit: 646 manifest entries (522 core, 114 adapter, and
  10 project-owned scaffolds), 28 specialists, 11 workflows, and zero ownership
  conflicts.
- Native consumer smoke: Claude 2.1.210, AGY 1.1.2, and Codex 0.144.4 expose
  28 specialists and 11 workflows; all three register the same MCP runtime and
  two lifecycle/guard hooks, subject to their native approval or trust prompts.
- UI compatibility gate: lint completed with zero errors, the production build
  completed, and all 51 UI tests passed.
- Known host limitation: Codex 0.144.4 omits project hooks in linked Git
  worktrees while loading MCP from the same trusted config. Normal repositories
  load both hooks. No global-hook or trust-bypass workaround is installed.
