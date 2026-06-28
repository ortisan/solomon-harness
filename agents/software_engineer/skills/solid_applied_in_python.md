## SOLID, applied in Python


- Single Responsibility. A module or class has one reason to change. If you describe it with "and", split it.
- Open/Closed. Extend behavior by injecting strategies or new adapters, not by editing a growing `if/elif` switch. Add a case by adding a class, not by patching the old one.
- Liskov Substitution. Subtypes must honor the base contract: same accepted inputs, no stricter preconditions, no surprising exceptions. If a subclass throws `NotImplementedError` for an inherited method, the hierarchy is wrong.
- Interface Segregation. Define small `typing.Protocol` interfaces per use case. A consumer should not depend on methods it never calls.
- Dependency Inversion. Depend on abstractions, inject them through constructors. This maps directly to the Hexagonal model below.
