## Robust, defensive code


- Validate inputs at the boundary against a strict schema before the domain sees them. Never trust external clients, network payloads, or stored fields.
- Guard against division-by-zero and float overflow before any ratio, normalization, or accumulation. Return or raise a defined error instead of producing `inf`/`nan` silently.
- Validate array and tensor shapes before matrix or batched operations when touching numeric or ML code, so a shape mismatch fails with a clear message, not a deep stack trace.
- Catch specific exceptions, never bare `except:`. Do not swallow errors; either handle them meaningfully or let them propagate. Fail fast and loud over corrupting state quietly.
- Use parameterized queries; never build SQL by string concatenation with input.
- Keep secrets in environment variables or a secret manager. Never hardcode or commit credentials. Strip stack traces and internal details from messages returned to external callers.
