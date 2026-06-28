## Debugging method


Debug like a scientist, not by guessing.

1. Reproduce deterministically. Capture the exact input and environment. Encode the reproduction as a failing test before you touch the code.
2. Read the traceback bottom-up; the deepest frame in your code is usually the cause, not the framework frame above it.
3. Form one hypothesis, change one variable, predict the result, run, and observe. Do not shotgun multiple edits at once.
4. Binary-search the problem space: bisect inputs, comment out halves, or run `git bisect` to find the commit that introduced the regression.
5. Use `breakpoint()`/`pdb` and targeted structured logging over scattered prints. Remove debug noise before committing.
6. Fix the root cause, not the symptom. A `try/except` that hides the error is not a fix.
7. Confirm the new regression test goes green and the full suite stays green. The test you added is the proof the bug is dead.

When the cause is non-obvious or the fix encodes a design decision, record it in project memory with `save_decision` so the next agent sees the rationale.
