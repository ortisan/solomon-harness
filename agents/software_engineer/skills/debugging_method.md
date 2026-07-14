---
name: debugging-method
description: Governs the systematic reproduce-isolate-hypothesize-bisect-instrument method for finding and killing a bug, including git bisect usage and turning every fix into a permanent regression test. Use when triaging a runtime error, an intermittent test failure, or a regression that needs a root-cause fix rather than a symptom patch.
---

# Debugging Method

This skill governs how to find and kill a bug systematically rather than by guessing. The stance: debugging is the scientific method applied to code — reproduce, isolate, hypothesize, test one variable, confirm. Every bug ends with a failing test that turns green, which is the proof the bug is dead and the guard against its return.

## The method: reproduce, isolate, hypothesize, bisect, instrument

Work the loop in order. Skipping a step is how a session turns into hours of shotgun edits.

1. **Reproduce deterministically.** Capture the exact input, environment, versions, and seed. A bug you cannot trigger on demand you cannot verify you fixed. Pin nondeterminism: set `PYTHONHASHSEED`, fix random seeds, freeze the clock, control time zones. Encode the reproduction as a failing test *before* touching the code — this is the Red of the TDD cycle and it converts "it sometimes breaks" into a binary signal.
2. **Read the traceback bottom-up.** The deepest frame inside your own code is usually the cause, not the framework frame above it. Read the exception type and message first, then walk up from the innermost frame to the first line you own. A `KeyError` or `AttributeError: 'NoneType' object has no attribute ...` names the exact missing value; do not skim past it.
3. **Isolate.** Shrink the failing case to the smallest input and the smallest code path that still fails. Delete unrelated config, strip the payload to the one field that matters, remove half the data. A minimal reproduction collapses the search space and frequently reveals the cause outright.
4. **Form one hypothesis and change one variable.** State what you believe is wrong, predict what the next run will show if you are right, change exactly one thing, run, and compare against the prediction. Never apply several edits at once: if the symptom changes you will not know which edit moved it.
5. **Bisect the search space.** Binary-search inputs, comment out halves of the pipeline, or use `git bisect` to find the commit that introduced a regression. Each test halves the remaining space, so even a thousand-commit range resolves in about ten runs.
6. **Instrument deliberately.** Reach for `breakpoint()`/`pdb` and targeted structured logging over scattered `print`. Inspect actual values at the boundary between "still correct" and "now wrong." Remove debug noise before committing.
7. **Fix the root cause, not the symptom.** A bare `try/except` that swallows the error, or a `if x is None: return` that papers over why `x` became `None`, is not a fix — it relocates the bug. Find why the bad state arose.
8. **Confirm green, and keep the suite green.** The regression test you added must pass, and the full suite must stay passing. Then the bug cannot silently come back.

When the cause is non-obvious or the fix encodes a design decision, record it in project memory with `save_decision` so the next agent sees the rationale instead of rediscovering it.

## git bisect: finding the commit that broke it

When something worked last week and fails today, `git bisect` finds the exact breaking commit by binary search over history. Mark a known-good and known-bad commit; git checks out the midpoint, you test, you mark it, and it converges.

```bash
git bisect start
git bisect bad                 # current HEAD is broken
git bisect good v1.4.0         # this release was fine
# git checks out the midpoint; run your reproduction:
pytest tests/test_orders.py::test_total -q && git bisect good || git bisect bad
# ... repeat until git names the first bad commit ...
git bisect reset               # always restore HEAD when done
```

Automate it fully when the reproduction is a single command — `git bisect run` does the marking for you and walks the whole range unattended:

```bash
git bisect start HEAD v1.4.0
git bisect run pytest tests/test_orders.py::test_total -q
```

The exit code drives it: `0` means good, non-zero means bad. The output ends with the offending commit's hash, author, and diff — usually the fastest route from "a regression exists somewhere in 200 commits" to the three lines that caused it.

## A worked example: symptom to root cause

**Symptom.** A reporting endpoint intermittently returns a total of `0.00` for orders that clearly have line items. It is not every request.

**Reproduce.** Capture a failing payload from logs and pin it in a test. The intermittence hints at ordering or shared state, so run with `-p no:randomly` off and on to see if test order matters.

```python
def test_report_total_for_known_order() -> None:
    repo = InMemoryOrderRepository()
    repo.save(Order(id="o1", customer_id="c1", total=Decimal("0"),
                    lines=["sku-1", "sku-2"]))
    assert report_total(repo, "o1") == Decimal("30.00")   # fails: returns 0.00
```

**Read and isolate.** No traceback — it is a wrong value, not a crash. Isolate by bisecting the data path with a breakpoint at the boundary:

```python
def report_total(repo, order_id):
    order = repo.get(order_id)
    breakpoint()          # inspect: is `order.lines` populated here?
    return sum(price_of(sku) for sku in order.lines)
```

At the prompt, `order.lines` is `[]` even though the saved order had two lines. So the data is lost between `save` and `get`, not in the summation. Hypothesis: the repository is not storing `lines`.

**Bisect history.** It worked last release, so `git bisect run` over the range names a commit titled "perf: store orders by shallow copy." The diff shows the adapter switched to `copy.copy(order)` — a shallow copy that shares the `lines` list reference, which a later mutation elsewhere clears.

**Root cause, not symptom.** The fix is not to re-sum defensively in `report_total`; that hides the loss. The fix is at the source: deep-copy on store, or better, stop mutating the shared aggregate. Change `copy.copy` to `copy.deepcopy` (or remove the aliasing mutation), rerun the regression test to green, and run the full suite to confirm nothing else relied on the shared reference. Record the aliasing trap with `save_decision`.

## Common pitfalls

- Debugging without a deterministic reproduction, so you can never prove the fix worked — the bug "goes away" and silently returns under load or a different seed.
- Reading the traceback top-down and blaming the framework frame, when the cause is the deepest frame in your own code that the message already points at.
- Changing several things at once: when the symptom shifts you cannot attribute the change, and you may introduce a second bug while masking the first.
- Catching and swallowing the exception (`except Exception: pass`) to make the error disappear. The symptom is gone, the corrupt state remains, and it resurfaces somewhere harder to trace.
- Leaving stray `print` and `breakpoint()` calls in committed code, which leak noise to production logs or hang a non-interactive run.
- Running `git bisect` without a reliable per-commit test, so you mark commits by eye and converge on the wrong one; and forgetting `git bisect reset`, leaving HEAD detached.
- Fixing the symptom downstream (re-deriving a value, clamping a result) instead of the upstream cause, so the same root defect breaks the next caller.
- Closing the bug without adding the regression test, so the next refactor reintroduces it with nothing to catch it.

## Definition of done

- [ ] The bug has a deterministic reproduction captured as a failing (Red) test before any code change.
- [ ] Root cause is identified and named, not just the symptom suppressed.
- [ ] Exactly one logical change addresses the cause; debug instrumentation (`print`, `breakpoint`) is removed.
- [ ] The regression test passes and the full suite stays green.
- [ ] If a regression, the introducing commit was identified (e.g. via `git bisect`) and `git bisect reset` restored HEAD.
- [ ] Non-obvious causes or design decisions from the fix are recorded in project memory with `save_decision`.
