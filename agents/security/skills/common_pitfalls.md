# Security Common Pitfalls

Recurring security defects a reviewer rejects on sight, from shallow authorization to unpinned dependencies and unrotated secrets. Each bullet states the failure mode and why it leaves the vulnerability open.

## Common pitfalls


- Treating the UI/API gateway as the only authorization point while service-to-service and data-layer calls trust each other implicitly.
- Suppressing SAST findings with a bare `# nosec` and no justification.
- Pinning direct dependencies but ignoring transitive ones, or pinning versions without hashes.
- Logging request bodies, tokens, or PII at INFO/DEBUG and shipping them off-box.
- Catching a vulnerability and patching the version without a regression test, so it silently returns.
- Deleting a leaked secret from the latest commit but not rotating it.
- Validating input shape but not its semantics (size, range, encoding), leaving DoS and injection open.

## Definition of done

- [ ] Authorization is enforced at every layer the change touches — service-to-service and data-layer calls included, not only the UI/API gateway.
- [ ] Every SAST suppression names the specific rule id and carries a written justification; no bare `# nosec` remains in the diff.
- [ ] Direct and transitive dependencies are pinned, with hashes, and the vulnerability scan covers both.
- [ ] No log statement introduced by the change emits tokens, request bodies, or PII at a level that ships off-box.
- [ ] Each patched vulnerability has a regression test that failed before the fix, so it cannot silently return.
- [ ] Any leaked secret was rotated at the provider, not merely deleted from the latest commit.
- [ ] Input validation covers semantics — size, range, encoding — not just shape, closing the DoS and injection paths.
