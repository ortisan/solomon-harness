---
name: no-workarounds-and-the-escape-valve
description: Governs fixing the source of a defect instead of silencing the signal that reports it — type-checker suppressions, lint disables, swallowed exceptions, sleep-based timing hacks, monkeypatched internals, defensive fallback chains, and copy-and-tweak duplication — and the four-condition escape valve that permits a contained, tracked, time-boxed workaround when the root cause is genuinely outside the team's control. Use when proposing a fix for a bug, a failing test, a type-checker or linter complaint, or a flaky test, and the candidate fix would suppress, cast, retry, or patch around the signal rather than repair what raised it.
---

# No Workarounds and the Escape Valve

A workaround is any change that makes a problem stop manifesting without addressing why it exists. It makes the symptom disappear while the underlying defect spreads: a deferred failure that compounds until it surfaces somewhere harder to trace. The stance: **fix the source, not the signal.** A fix is done when it would have been unnecessary had the code been correct from the start, and it needs no cast, suppression, delay, or empty `except` to pass.

## The gate — run before proposing any fix

State the problem, then trace it to its root cause using `debugging_method`. Before writing the fix, answer two questions:

1. Does this repair the root cause, or only stop the symptom from showing?
2. Am I silencing a signal — a type error, a lint rule, an exception, a race, a broken API, a forced abstraction — or fixing what raised it?

If the answer to the second question is "silencing," redesign the fix against the root cause. If the root cause is genuinely external and unfixable by the team, take the escape valve below. There is no third option: shipping a silenced signal with no escape-valve justification is not an option, however small the change looks.

## The seven signals, mapped to Python

Each row is mypy, ruff, the runtime, or a reviewer telling you something true about the code. Fix what it points at; do not teach the tool to stop telling you.

| Category | The signal it silences | Python pattern | Fix the source by |
|---|---|---|---|
| **TYPE** | The type checker found the code wrong | `# type: ignore`, `cast(Any, value)` | Making the type truthful: correct the annotation, or validate genuinely unknown data at the boundary with a `TypedDict`/`pydantic` model/`dataclass` and a real parse step |
| **LINT** | Static analysis found a real problem | `# noqa`, blanket `# ruff: noqa` at file top | Fixing what the rule flagged; if the rule is wrong for this repo, disable it once in `pyproject.toml`, never inline per occurrence |
| **SWALLOW** | Something failed and the code pretends it did not | bare `except:`, `except Exception: pass` | Catching the specific exception you can handle, logging or translating it with `raise DomainError(...) from err`, or letting it propagate — see `robust_defensive_code` |
| **TIMING** | Code runs in the wrong order, or a real intermittent failure is being hidden | `time.sleep(n)` before asserting, a bare retry loop with no backoff policy | Waiting on the actual readiness condition (poll a predicate, `await` the real future, use a designed retry from `resilience_patterns_in_code`) rather than the clock — see `flaky_tests` for the deflaking workflow when this shows up in a test |
| **PATCH** | The dependency's public API does not do what the code needs | `monkeypatch.setattr(third_party.module, "_internal_fn", ...)` in production code, reaching into a library's private attributes | Composing around it: a thin adapter or wrapper at one seam, or the library's documented extension point — never reaching past its public surface |
| **SCATTER** | The data is unreliable at its source | `timeout = payload.get("timeout") or cfg.get("timeout") or DEFAULT` repeated at every call site | Validating once at the boundary (a typed request model), then trusting the shape everywhere downstream |
| **CLONE** | An abstraction does not fit, so the code is forced to duplicate instead | copy-pasting `validate_order` into `validate_order_v2` with one field tweaked | Extracting the shared pattern on the third occurrence, or writing purpose-built code — apply the rule of three from `clean_code`, do not abstract on the first or second sighting |

A worked pair for SWALLOW and TIMING, since they show up most often in this codebase's PRs:

```python
try:
    order = repository.load(order_id)
except Exception:
    order = None
```

The `except Exception` here erases whether the failure was a transient connection drop, a missing row, or a bug in `load`. The caller then has to guess what `None` means. The source fix names the real cases:

```python
try:
    order = repository.load(order_id)
except OrderNotFoundError:
    raise
except ConnectionError as err:
    raise RepositoryUnavailableError(order_id) from err
```

For TIMING, a test that polls a fixed delay instead of the real condition:

```python
worker.start()
time.sleep(2)
assert worker.is_ready()
```

replaces the clock with the condition it is actually waiting on:

```python
worker.start()
wait_until(worker.is_ready, timeout=5)
```

`wait_until` polls the predicate on a short interval and raises on timeout, so the test is exactly as fast as the system under test and never flakes because CI ran a beat slower than a developer's laptop.

## The escape valve

Not every root cause is yours to fix. A workaround is permitted only when every one of these four conditions holds — not three of four, all four:

1. The root cause lives in external code the team does not control (a third-party library, a vendor API, a platform bug).
2. The proper fix needs an upstream change on a timeline the team cannot pin down.
3. The business cost of not shipping now exceeds the debt this workaround incurs.
4. The workaround is isolated to one seam — it does not leak its shape into unrelated call sites.

When all four hold, contain it instead of leaving it bare:

1. Mark it at the point of use: `# WORKAROUND: <reason> — see #<issue>`.
2. File a tracking issue for its removal (`log_issue`, `type_="tech-debt"`), and record the tradeoff with `save_decision` so the rationale outlives the session.
3. Add a pinning test that locks the current, workaround-shaped behavior, so an accidental refactor that removes the workaround is caught immediately.
4. Add a canary test that fails once the upstream fix lands. In pytest this is `@pytest.mark.xfail(reason="waiting on upstream fix, see #<issue>", strict=True)` written against the *correct* behavior, not the workaround. While the upstream bug persists, the test fails as expected and `xfail` keeps the suite green; the day upstream ships the fix, the same test unexpectedly passes, and `strict=True` turns that unexpected pass (`XPASS`) into a hard failure. The suite itself tells you the workaround is now dead weight.
5. Set a review date no more than 90 days out, tracked on the same issue, so the workaround cannot quietly become permanent.

If any of the four conditions fails, there is no escape valve: fix the root cause.

## Rationalizations and their answers

- "It's an emergency, there's no time for the proper fix" — the workaround costs more time later, in the debugging session it causes and the maintenance burden it leaves; a contained escape valve with a tracking issue and a canary test is barely slower to write than the bare suppression.
- "The type checker is being pedantic here" — mypy found a real mismatch between what the code assumes and what the data can actually be; listen to it before overriding it.
- "I'll open a tech-debt ticket and get to it later" — an untracked or unreferenced ticket is a fiction; the escape valve requires the ticket to carry the marker, the pinning test, and the review date, or it does not count as contained.
- "The test passes, so it's fine to ship" — a passing test written against a workaround verifies the workaround, not the correct behavior; it will not catch the real bug when the workaround's assumptions change.

## Common pitfalls

- Reaching for `# type: ignore` or `cast(Any, ...)` on the first mypy error instead of reading what it actually flagged; the checker is usually right.
- Writing `except Exception: pass` "just to keep the pipeline running" — this is exactly the SWALLOW signal the gate exists to catch, and it hides a bug that resurfaces somewhere unrelated later.
- Adding a `time.sleep` to make a flaky test pass locally, which papers over a real race instead of fixing it; see `flaky_tests` for the quarantine-and-deflake path instead.
- Treating "it's behind a feature flag" as containment — flags rarely expire on their own, and an unflagged escape valve becomes permanent by default.
- Claiming the escape valve with only three of the four conditions, most often skipping "is it genuinely isolated" because the workaround's shape has already leaked into two other modules.
- Filing the tracking issue but skipping the canary test, so nothing in the suite ever tells anyone the upstream fix has landed and the workaround is still there a year later.
- Copy-and-tweaking a function a second time and calling it done, instead of extracting on the third occurrence per the rule of three — two near-duplicates are acceptable, three is a pattern that needs a name.
- Monkeypatching a third-party module's internals directly in production code because the public API is inconvenient, rather than writing a one-seam adapter that isolates the dependency.

## Definition of done

- [ ] Every proposed fix passed the gate: root cause identified via `debugging_method`, and the change repairs it rather than silencing the signal that reported it.
- [ ] No `# type: ignore`, `# noqa`, bare `except`, `time.sleep`-based wait, monkeypatched library internal, `or`-chain fallback, or copy-and-tweak duplicate ships without either a proper fix or a documented escape valve.
- [ ] Any escape valve in the diff satisfies all four conditions, not a subset, and each carries: a `# WORKAROUND: <reason> — see #<issue>` marker, a `log_issue` tracking row, a `save_decision` record, a pinning test, a canary test (`xfail(strict=True)` or equivalent), and a review date within 90 days.
- [ ] SWALLOW-category fixes were cross-checked against `robust_defensive_code`; TIMING-category fixes against `flaky_tests` and `resilience_patterns_in_code`; CLONE-category fixes against the rule of three in `clean_code`.
- [ ] The full test suite, mypy, and ruff all run green on the final diff — a silenced signal that still trips CI is not contained, it is broken.
