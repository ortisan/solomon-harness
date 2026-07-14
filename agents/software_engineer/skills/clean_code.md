---
name: clean-code
description: Governs writing clean, readable Python through intent-revealing names, single-responsibility functions capped at two nesting levels, comments that explain why rather than what, and the boy-scout rule of leaving each touched file cleaner. Use when writing or reviewing production code for naming, function size, nesting, magic numbers, or comment quality.
---

# Clean Code In Python

Clean code is code a reviewer can read top to bottom and trust without running it: every name states intent, every function does one thing at one level of abstraction, and every comment explains a decision the code cannot. The stance is that readability is a feature with a cost paid by the next engineer, so we optimize the cost of reading over the cost of writing.

## Naming carries the intent

A name is the cheapest documentation you will ever write and the most expensive to get wrong. Names carry intent: no single-letter names outside short comprehensions or math, no abbreviations that need a glossary, and booleans read as predicates (`is_active`, `has_pending`). Spend the characters; an editor autocompletes them and a reader never has to.

Reject names that describe the type instead of the role (`data`, `info`, `obj`, `tmp`, `do_it`). Name by what the value means in the domain, and keep the name honest when the code changes. A misleading name is worse than no name.

```python
# Before: types and noise, no intent.
def proc(d, l):
    r = []
    for x in d:
        if x[2] > l:
            r.append(x)
    return r

# After: the name is the explanation.
def orders_above_limit(orders: list[Order], limit_usd: Decimal) -> list[Order]:
    return [order for order in orders if order.total_usd > limit_usd]
```

No magic numbers or strings. Promote them to named constants or enums so the meaning lives in one place and a grep finds every use. `if status == 3` forces the reader to hunt; `if status is OrderStatus.SHIPPED` does not.

```python
class OrderStatus(IntEnum):
    PENDING = 1
    PAID = 2
    SHIPPED = 3

MAX_RETRY_ATTEMPTS = 3  # named, greppable, changed in one place
```

## Functions: one thing, one level, short

Functions do one thing at one level of abstraction. Keep them short; if a function needs section comments to mark its phases, those phases are separate functions waiting to be extracted. The body should read as a sequence of steps at the same altitude, with the lower-level mechanics named and pushed down.

Cap nesting at two levels. Use guard clauses and early returns instead of `else` pyramids: validate and bail at the top, then let the happy path run flat and unindented. Keep cyclomatic complexity at or below 10 per function; check with `ruff` (rule `C901`) or `radon cc` and split anything higher rather than arguing about it.

```python
# Before: mixed abstraction levels, nested, hard to test.
def checkout(cart, user):
    if cart.items:
        if user.is_verified:
            total = 0
            for item in cart.items:
                total += item.price * item.qty
            if total > 0:
                charge(user.card, total)
                return total
    return None

# After: guard clauses, one job, one altitude.
def checkout(cart: Cart, user: User) -> Decimal:
    if not cart.items:
        raise EmptyCartError(cart.id)
    if not user.is_verified:
        raise UnverifiedUserError(user.id)

    total = cart_total(cart)
    charge(user.card, total)
    return total

def cart_total(cart: Cart) -> Decimal:
    return sum((item.price * item.qty for item in cart.items), Decimal(0))
```

Type-annotate every public function signature (PEP 484) and run `mypy --strict`; do not let `Any` leak across module boundaries, because an untyped boundary turns every caller into a guesser. Prefer pure functions and immutable data: push side effects (IO, network, clock) to the edges so the core stays deterministic and testable without mocks. A function that reads the clock or hits the network in the middle of a calculation cannot be tested in isolation.

## Comments explain why, and the boy-scout rule

Self-documenting code comes first; comments explain why, not what. A comment that restates the code rots the moment the code changes and lies thereafter. Reserve comments for the decision a reader cannot reconstruct: the reason for an unusual constant, the spec clause that forces an edge case, the bug a workaround prevents.

```python
# Bad: narrates the obvious, will drift from the code.
i += 1  # increment i

# Good: records a decision the code cannot show.
# Stripe rounds half-to-even; match it so our totals reconcile with their webhook.
amount = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
```

Delete dead code and commented-out blocks rather than shipping them; version control is the archive, and a commented-out branch is a question every future reader must answer. Preserve existing docstrings and comments unrelated to your change.

The boy-scout rule: leave each file you touch cleaner than you found it. Rename one misleading variable, extract one overgrown function, tighten one type on your way through. This keeps quality compounding instead of decaying, and it keeps the diff honest because each cleanup rides with code that already needed touching.

Control duplication with the rule of three. Apply it before abstracting: duplicating twice is fine, extract on the third occurrence so you abstract the real pattern rather than a guessed one. Premature abstraction couples unrelated call sites through a shared shape they did not actually share, and unwinding it later is more expensive than the duplication ever was.

## Common pitfalls

- Names that describe the type (`data`, `obj`, `tmp`) instead of the role, forcing the reader to trace usage to recover intent.
- Magic numbers and string literals inline, because the meaning lives nowhere and a change must be found by eye in every file.
- Boolean flag parameters (`render(user, True)`) that hide two behaviors behind one signature; split into two named functions so the call site reads.
- `else` pyramids and nesting past two levels, because each level multiplies the paths a reader must hold in mind and inflates cyclomatic complexity past the C901 ceiling.
- Comments that restate the code, which drift on the next edit and then actively mislead.
- Commented-out code shipped "just in case", treating the diff as a notepad instead of trusting version control.
- Abstracting on the first duplication, coupling call sites through a pattern that was a coincidence, not a rule.
- `Any` leaking across a module boundary, defeating `mypy --strict` for every downstream caller.
- Side effects (clock, network, IO) buried mid-calculation, making the function untestable without heavy mocking.

## Definition of done

- [ ] Every name states a domain role; no single-letter names outside comprehensions/math, no glossary abbreviations, booleans read as predicates.
- [ ] No magic numbers or strings; constants and enums are named and used.
- [ ] Functions do one thing at one abstraction level, nesting capped at two via guard clauses, cyclomatic complexity at or below 10 verified by `ruff` C901 or `radon cc`.
- [ ] Every public signature is annotated and `mypy --strict` passes with no `Any` crossing a module boundary.
- [ ] Comments explain why, not what; no commented-out code; unrelated docstrings and comments preserved.
- [ ] Duplication resolved by the rule of three, not abstracted on first sight.
- [ ] Side effects pushed to the edges; the core logic is pure and testable without mocks.
- [ ] At least one boy-scout improvement made to each file touched, riding with a change that already needed it.
