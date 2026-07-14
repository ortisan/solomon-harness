---
name: "Bug Report"
about: Report a bug, including reproduction steps, expected/actual behavior, diagnostic logs, and impact analysis.
title: "[Bug]: "
labels: ["bug"]
assignees: []
---

## Description
<!-- A clear and concise description of what the bug is. -->

## Steps to Reproduce
<!-- Steps to reproduce the behavior: -->
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

## Expected vs Actual
### Expected Behavior
<!-- A clear and concise description of what you expected to happen. -->

### Actual Behavior
<!-- A clear and concise description of what actually happened. -->

## Diagnostic Log/Error
<!-- If applicable, add console logs, terminal output, stack traces, or screenshots to help debug. -->
```
```

## Suspected Location
<!-- The file:line(s) most likely at fault, from a quick read of the code, and where the fix will land. Write TBD only when triage genuinely cannot narrow it. -->
- `path/to/file.py:LINE` — <why this is the suspected cause>

## Verification
<!-- The exact command(s) that reproduce the defect now and prove the fix later. -->
```bash
# e.g. uv run pytest tests/test_<area>.py -q
```

## Security/Performance Impact
<!-- Does this issue expose any vulnerabilities, leak resources, or degrade latency/throughput? -->

## Acceptance Criteria
<!-- Observable conditions the fix must meet, as Given/When/Then: the repro scenario now passes and no adjacent behavior regresses. -->
- [ ] Given/When/Then for the corrected behavior

## Definition of Ready
<!-- Refinement gate before the fix starts: the repro is deterministic, severity/priority assigned, suspected area scoped. -->
- [ ] Reproduction is deterministic
- [ ] Severity and priority assigned
- [ ] Suspected area scoped

## Definition of Done
<!-- Close gate enforced at review and release: red-then-green regression test, fix merged with CI green, no new failures. -->
- [ ] Failing regression test added (red) then passing (green)
- [ ] Fix merged with CI green
- [ ] No new failures introduced
