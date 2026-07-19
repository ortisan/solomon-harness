# ADR-0036: install a host-neutral harness with generated host adapters

- Status: accepted
- Date: 2026-07-15
- Deciders: maintainer, software_architect, loop_engineer, security, qa
- Issue: #240
- Amended: 2026-07-16 by ADR-0043, which defines consumer-owned agent
  extensions below the installed canonical catalog.

## Context and problem statement

The installer copies live repository trees and Claude/Gemini artifacts into consumer
roots. There is no ownership record, Codex is absent, AGY uses a legacy Gemini layout,
and runtime configuration/state occupies generic root paths. A consumer cannot distinguish
its product from the harness or safely upgrade and uninstall the latter.

## Decision drivers

- One bounded and auditable repository-local tooling home.
- Equal behavior in Claude, current AGY, and Codex without making one host canonical.
- Deterministic source and wheel installation with no local-state leakage.
- Safe upgrade, migration, rollback, and uninstall in repositories that already contain
  host configuration and files with generic names.
- Compatibility with fixed host discovery paths and Windows filesystems.

## Considered options

- Keep bulk copies and add more exclusions. Rejected because exclusion lists cannot prove
  ownership or prevent future local-state classes from leaking.
- Make a Claude plugin canonical and translate it to AGY and Codex. Rejected because host
  semantics drift and Claude vocabulary would remain the architecture boundary.
- Use symlinks from every host path into one tree. Rejected as the primary contract because
  Windows privileges, archives, worktrees, and host scanners handle symlinks differently.
- Install one neutral core with independently rendered native adapters and an ownership
  manifest. Chosen.

## Decision outcome

Chosen option "neutral core plus independent native adapters". Repository-local canonical
content, configuration, runtime, and state live below `.agents/solomon`. The package,
scripts, `pyproject.toml`, and lock file sit directly in that directory so runtime commands
use one stable `uv --project` root. A deterministic
manifest records every managed path and hash. Claude, AGY, and Codex render from the same
specialist/workflow catalog and are accepted only through one parametrized capability
contract. Files in fixed discovery locations contain only metadata, native configuration,
and pointers to the core.

The installer builds from an explicit positive allowlist. Source checkout mode and wheel
mode use the same payload builder. Upgrades and uninstall may modify only files or
namespaced configuration entries recorded as Solomon-owned. Legacy layout migration uses
expand-migrate-contract and retains read fallback for one release.

### Consequences

- Positive: consumer roots remain product-owned; host drift becomes a failing test; source
  worktrees and personal settings cannot enter the payload through a broad copy.
- Positive: every managed file has an owner and digest, enabling safe idempotency, upgrade,
  rollback, stale cleanup, and uninstall.
- Positive: AGY uses its current `.agents` discovery surfaces and Codex becomes a first-class
  engine, specialist host, MCP client, and hook host.
- Negative: fixed discovery protocols still require a few files outside `.agents`; those
  bridges must remain small and must be merged carefully.
- Negative: three renderers and compatibility migration add test surface and must evolve
  when host schemas change.
- Constraint: the cross-worktree loop lock and budget remain in Git's common directory;
  they are shared operational safety state, not installed repository payload.
- Follow-ups: remove the legacy path fallback after one released compatibility window and
  evaluate optional global plugins independently from the repository-local default.

## More information

This decision completes the layout follow-up recorded by ADR-0029 and supersedes issue
#240's original two-host assumption. Specification:
`docs/specs/240-host-agnostic-tooling-layer.md`. The PR will carry this ADR and the decision
will be written to project memory before review.
