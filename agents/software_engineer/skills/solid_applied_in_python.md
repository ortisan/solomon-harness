---
name: solid-applied-in-python
description: Governs applying Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, and Dependency Inversion in Python using typing.Protocol, small interfaces, and constructor injection instead of inheritance-heavy machinery. Use when designing a class hierarchy, reviewing a growing if/elif dispatch, or deciding how a dependency should be injected.
---

# SOLID Applied In Python

SOLID is five constraints that keep a codebase open to change without rewrites; in Python they are expressed with `typing.Protocol`, abstract base classes, and constructor injection rather than the heavy interface machinery of nominally-typed languages. The stance: depend on small abstractions you own, inject them, and let new behavior arrive as new classes instead of edits to old ones.

## Single Responsibility and Open/Closed

Single Responsibility: a module or class has one reason to change. If you describe it with "and" — "parses the file and writes to the database and emails the user" — split it, because each clause is a separate axis of change that will pull the class in a different direction. The test is social as much as technical: who files the bug that forces an edit? If three different stakeholders can, the class has three responsibilities.

```python
# Before: one class changes for three reasons.
class Report:
    def build(self, rows): ...        # changes when the report format changes
    def save(self, path): ...         # changes when storage changes
    def email(self, address): ...     # changes when delivery changes

# After: one reason to change each.
class ReportBuilder: ...
class ReportStore: ...
class ReportMailer: ...
```

Open/Closed: extend behavior by injecting strategies or new adapters, not by editing a growing `if/elif` switch. Add a case by adding a class, not by patching the old one. A type-dispatch chain that grows a branch per feature is the canonical violation: every new case reopens, retests, and risks the same function.

```python
from typing import Protocol
from decimal import Decimal

class DiscountPolicy(Protocol):
    def apply(self, subtotal: Decimal) -> Decimal: ...

class NoDiscount:
    def apply(self, subtotal: Decimal) -> Decimal:
        return subtotal

class PercentOff:
    def __init__(self, fraction: Decimal) -> None:
        self._fraction = fraction
    def apply(self, subtotal: Decimal) -> Decimal:
        return subtotal * (Decimal(1) - self._fraction)

# A new promotion is a new class; price() never reopens.
def price(subtotal: Decimal, policy: DiscountPolicy) -> Decimal:
    return policy.apply(subtotal)
```

## Liskov Substitution and Interface Segregation

Liskov Substitution: subtypes must honor the base contract — accept the same inputs, impose no stricter preconditions, return through the same postconditions, and raise no surprising exceptions. If a subclass throws `NotImplementedError` for an inherited method, the hierarchy is wrong: the subtype is not substitutable and every caller now needs a type check, which defeats polymorphism. The classic trap is modeling "is-a" by vocabulary instead of by behavior.

```python
# Before: Square "is a" Rectangle by words, not behavior — it breaks callers.
class Rectangle:
    def set_width(self, w: int) -> None: self._w = w
    def set_height(self, h: int) -> None: self._h = h

class Square(Rectangle):
    def set_width(self, w: int) -> None:   # mutating one side changes both:
        self._w = self._h = w              # a caller's set_width then set_height
    def set_height(self, h: int) -> None:  # invariant (area == w*h) now lies.
        self._w = self._h = h

# After: model the shared behavior, not the textbook taxonomy.
class Shape(Protocol):
    def area(self) -> int: ...
```

Interface Segregation: define small `typing.Protocol` interfaces per use case so a consumer never depends on methods it does not call. A fat interface forces fake implementations to stub methods they will never use and drags every consumer through changes to methods irrelevant to them. Split by what the caller needs, not by what the implementer happens to offer.

```python
from typing import Protocol

# Before: one fat port; a read-only report must still implement save().
class Repository(Protocol):
    def get(self, id: int) -> Order: ...
    def save(self, order: Order) -> None: ...
    def delete(self, id: int) -> None: ...

# After: segregated; a reader depends only on what it uses.
class OrderReader(Protocol):
    def get(self, id: int) -> Order: ...

class OrderWriter(Protocol):
    def save(self, order: Order) -> None: ...

def render_invoice(reader: OrderReader, id: int) -> str: ...
```

`Protocol` gives structural typing: an adapter satisfies the port by shape, with no `import` of the protocol and no base-class coupling, which keeps the dependency arrow pointing the right way.

## Dependency Inversion through injection

Dependency Inversion: high-level policy depends on abstractions, and the abstractions are injected through constructors — never instantiated inside the policy. This maps directly onto the hexagonal model: the domain defines the port (a `Protocol`), and the concrete adapter is wired in at the edge. Code that does `self.db = PostgresClient()` in its constructor has hard-wired itself to one implementation and to the network, and cannot be unit-tested without that network.

```python
from typing import Protocol

# Port: owned by the high-level policy, expressed as an abstraction.
class NotificationGateway(Protocol):
    def send(self, to: str, body: str) -> None: ...

# High-level policy depends on the port, not on any concrete sender.
class AlertService:
    def __init__(self, gateway: NotificationGateway) -> None:
        self._gateway = gateway

    def raise_alert(self, to: str, message: str) -> None:
        self._gateway.send(to, f"ALERT: {message}")

# Adapters are concrete and swapped at the composition root.
class EmailGateway:
    def send(self, to: str, body: str) -> None: ...

class FakeGateway:  # the test double is trivial because the seam exists.
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
    def send(self, to: str, body: str) -> None:
        self.sent.append((to, body))

# Composition root wires the real adapter; tests wire the fake.
service = AlertService(gateway=EmailGateway())
```

The payoff is testability and substitutability for free: the same `AlertService` runs against `EmailGateway` in production and `FakeGateway` in a unit test, with no patching, because the dependency was a constructor argument rather than a buried `import`.

## Common pitfalls

- A class described with "and" in its summary, signaling multiple reasons to change crammed into one unit (SRP).
- A growing `if/elif` type switch edited for every new case, instead of a new strategy class registered against a `Protocol` (OCP).
- Subclasses that raise `NotImplementedError` or tighten preconditions, breaking callers that hold the base type (LSP).
- Modeling "is-a" by vocabulary (Square extends Rectangle) when the behaviors and invariants diverge (LSP).
- Fat interfaces that force fakes and consumers to carry methods they never call, coupling everyone to unrelated changes (ISP).
- Concrete dependencies constructed inside a class (`self.db = PostgresClient()`), hard-wiring policy to one adapter and to IO, making unit tests impossible without patching (DIP).
- Abstractions imported from the adapter side, pointing the dependency arrow the wrong way; the domain must own the port.
- Over-applying SOLID to small, stable code, producing layers of indirection that obscure intent — apply the principle when a real axis of change exists.

## Definition of done

- [ ] Every class has one reason to change; any "and" in its description is resolved by splitting (SRP).
- [ ] New behavior arrives as a new class against an injected `Protocol`/ABC, with no edit to an existing dispatch switch (OCP).
- [ ] Subtypes are substitutable: same inputs, no stricter preconditions, no `NotImplementedError`, no surprising exceptions (LSP).
- [ ] Interfaces are small and use-case specific; no consumer depends on methods it does not call (ISP).
- [ ] High-level policy depends only on abstractions it owns, injected via constructors; concretes are wired at the composition root (DIP).
- [ ] Unit tests use lightweight fakes through the ports, requiring no monkeypatching of internals.
- [ ] `mypy --strict` confirms adapters satisfy their `Protocol` ports structurally.
