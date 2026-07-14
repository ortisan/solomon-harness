---
name: robust-defensive-code
description: Governs defending code at trust boundaries through parse-don't-validate typed inputs, guard clauses, total functions, explicit handling of None, empty, zero, and non-finite values, and narrow exception handling that never swallows an error. Use when validating external input, writing a numeric or boundary-crossing function, or reviewing code for sentinel returns and bare except blocks.
---

# Robust, Defensive Code

This skill governs where and how to defend code against bad input and undefined states. The stance: validate hard at trust boundaries, then trust your own validated types inside; defend the edges, not every line. Defensive coding is about making invalid states unrepresentable and failing fast and loud when they slip through, never about scattering null checks through a codebase that already proved its invariants.

## Trust boundaries versus internal paranoia

A trust boundary is any point where data crosses from a place you do not control into a place you do: an HTTP handler, a queue consumer, a CLI argument parser, a deserialized cache entry, a row read back from a table another service writes. At that boundary, assume the input is hostile or malformed and validate it completely before the domain sees it. Once data has passed the boundary and been parsed into a validated type, code deeper in the call stack should rely on that type, not re-check it. Re-validating a value you already proved correct is noise: it dilutes the real checks, suggests to the reader that the invariant is uncertain, and hides the one place that actually owns the contract.

The technique that makes this work is "parse, don't validate": convert raw input into a type whose existence is proof of validity, so downstream functions cannot receive a bad value because the bad value never type-checks. A function that takes a `PositiveInt` or a validated `Email` never needs to ask whether the number is positive or the address is shaped right.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Quantity:
    """A trade quantity in [1, 10_000]. Existence proves validity."""
    value: int

    @classmethod
    def parse(cls, raw: object) -> "Quantity":
        if not isinstance(raw, int) or isinstance(raw, bool):
            raise ValueError("quantity must be an integer")
        if not 1 <= raw <= 10_000:
            raise ValueError("quantity out of range [1, 10000]")
        return cls(raw)

def submit_order(qty: Quantity) -> None:
    # No re-check here. The type is the guarantee.
    book.place(qty.value)
```

At the real boundary, validate against a strict schema (pydantic v2 `model_validate`, a JSON Schema validator, dataclass parsers like the above). Reject unknown fields rather than ignoring them, bound every string length and number range, and pin types so `"5"` does not silently become `5`.

## Guard clauses, fail-fast, and total functions

Use guard clauses to reject impossible states at the top of a function and return early, keeping the happy path flat and unindented. Karpathy-simple code is flat code; deep nesting is usually missing guards.

```python
def average_fill_price(fills: list[Fill]) -> float:
    if not fills:                       # guard: empty is meaningless, not zero
        raise ValueError("no fills to average")
    total_qty = sum(f.qty for f in fills)
    if total_qty == 0:                  # guard division-by-zero before the ratio
        raise ValueError("total quantity is zero")
    return sum(f.qty * f.price for f in fills) / total_qty
```

Fail fast and loud beats limping on with corrupted state. A function that returns `0.0` for "no data" lies to its caller; a raised `ValueError` stops the damage at the source. Aim for total functions, defined for every input of their declared type. When a function is genuinely partial (it has inputs with no sensible answer), make the partiality explicit in the signature: return `Optional`, return a `Result`-style union, or raise a named exception. Never paper over partiality with a sentinel like `-1` or `""` that the next caller forgets to check.

Handle the three classic edge inputs explicitly: `None` (distinguish "absent" from "empty" from "zero"), empty collections (an empty list is not an error in `sum` but is in `mean`), and numeric overflow or non-finite values. Guard division-by-zero and float overflow before any ratio, normalization, or accumulation, and reject `inf`/`nan` at the boundary rather than letting them propagate into a model.

```python
import math

def normalize(weights: list[float]) -> list[float]:
    if not weights:
        raise ValueError("cannot normalize an empty vector")
    if any(not math.isfinite(w) for w in weights):
        raise ValueError("weights contain inf or nan")
    total = math.fsum(weights)          # fsum limits float error accumulation
    if math.isclose(total, 0.0):
        raise ValueError("weights sum to zero; normalization undefined")
    return [w / total for w in weights]
```

For numeric and ML code, validate tensor and array shapes before matrix or batched operations, so a mismatch fails with a clear `f"expected (N, {D}), got {x.shape}"` message instead of a deep, opaque stack trace from inside the math library.

## Exceptions: catch narrow, never swallow

Catch the specific exception you can actually handle, never a bare `except:` or blanket `except Exception`. Swallowing errors converts a loud failure into a silent corruption that surfaces hours later somewhere unrelated. Either handle the error meaningfully (retry, fall back, translate to a domain error) or let it propagate. When you translate, preserve the cause with `raise DomainError(...) from err` so the traceback chain survives. Strip stack traces and internal details from messages returned to external callers, but log the full detail server-side.

## Common pitfalls

- Re-validating a value deep inside the call stack that the boundary already validated: it implies the invariant is unowned and hides the one real check. Trust your validated types.
- Returning a sentinel (`-1`, `0.0`, `""`, `None`) for an error condition the caller will forget to check, instead of raising. The next reader treats the sentinel as a real value and corrupts state.
- Bare `except:` or `except Exception: pass`: turns a diagnosable failure into a silent one and masks bugs like `KeyboardInterrupt` and typos in attribute access.
- Computing a ratio, mean, or normalization without first guarding the denominator and the empty case, producing `inf`/`nan` that poisons everything downstream.
- Treating `None`, empty, and zero as interchangeable. "No value supplied", "empty list", and "the number zero" have different correct behaviors and conflating them is a real defect.
- Letting `inf`/`nan` cross a boundary into a model or accumulator; they survive arithmetic and silently invalidate results far from their origin.
- Validating with permissive coercion (accepting `"5"` as `5`, ignoring unknown fields) so malformed input slips through looking valid.

## Definition of done

- [ ] Every external input (HTTP, queue, CLI, deserialized cache, cross-service row) is validated against a strict schema at the boundary before the domain sees it.
- [ ] Validated data is carried as a type whose existence proves validity; downstream code does not re-validate.
- [ ] Functions use guard clauses and early returns; the happy path is flat and unindented.
- [ ] Division-by-zero, empty collections, `None`, and non-finite (`inf`/`nan`) inputs are each handled explicitly with a defined error.
- [ ] Tensor/array shapes are checked before matrix or batched operations, with a message naming expected versus actual shape.
- [ ] No sentinel return values stand in for errors; partial functions declare partiality via `Optional`, a result union, or a named exception.
- [ ] Only specific exceptions are caught; no bare `except`; translated errors preserve the cause with `raise ... from`.
- [ ] Error messages returned to external callers carry no stack traces or internal detail; full detail is logged server-side.
- [ ] Tests cover the negative cases: empty, `None`, out-of-range, zero denominator, non-finite input, and shape mismatch.
