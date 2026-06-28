## Common pitfalls


- Treating the UI/API gateway as the only authorization point while service-to-service and data-layer calls trust each other implicitly.
- Suppressing SAST findings with a bare `# nosec` and no justification.
- Pinning direct dependencies but ignoring transitive ones, or pinning versions without hashes.
- Logging request bodies, tokens, or PII at INFO/DEBUG and shipping them off-box.
- Catching a vulnerability and patching the version without a regression test, so it silently returns.
- Deleting a leaked secret from the latest commit but not rotating it.
- Validating input shape but not its semantics (size, range, encoding), leaving DoS and injection open.
