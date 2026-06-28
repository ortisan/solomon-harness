# Hexagonal Architecture (Ports and Adapters)

This skill governs how to keep business logic independent of frameworks, databases, and transport. The stance: the domain depends on nothing; everything depends on the domain. A port is an interface owned by the core; an adapter is a replaceable implementation of that interface living at the edge. If swapping Postgres for DynamoDB, or REST for gRPC, forces a change inside the domain, the dependency arrow is pointing the wrong way and the design is wrong.

## The three layers and the dependency rule

Alistair Cockburn's hexagonal architecture (also called ports and adapters) draws one boundary: inside the hexagon is application-specific code, outside is everything technology-specific. In practice split it into three concentric layers, with imports allowed only inward.

- **Domain** holds entities, value objects, and pure business rules. It imports zero frameworks, no ORM, no HTTP client, no `boto3`, no `requests`, no SQL driver. A domain module should be importable in a bare Python process with only the standard library. This is what makes the rules testable in microseconds and portable across delivery mechanisms.
- **Application** orchestrates use cases. It defines the ports (the interfaces it needs the outside world to satisfy) and contains the services that call domain objects and those ports. It still imports no concrete infrastructure, only the port abstractions it declares.
- **Infrastructure** holds adapters: the concrete implementations. Driving (primary, left-side) adapters call into the application — REST controllers, CLI handlers, queue consumers. Driven (secondary, right-side) adapters implement the application's outgoing ports — repositories backed by a database, gateways to a payment API, file clients.

Driving ports describe how the outside invokes the domain; driven ports describe what the domain needs from infrastructure. The critical move is **dependency inversion at the boundary**: the application declares the outgoing port, and the infrastructure adapter depends on (implements) that port. The arrow points from infrastructure to application, never the reverse. Wiring happens once, at the composition root (the `main`, the FastAPI startup, the CLI entrypoint), where concrete adapters are constructed and injected.

Ports speak the domain's language. A `OrderRepository` port returns `Order` aggregates, not ORM rows or JSON dicts. A row-shaped or transport-shaped signature leaking through a port is the classic abstraction leak that couples the core to the edge it was supposed to hide.

## A worked example: port, in-memory adapter, real adapter

A use case needs to persist and load orders. The application declares the port as a `typing.Protocol` (structural typing means an adapter does not need to import or subclass the port — it just has to match the shape, keeping the dependency arrow clean).

```python
# domain/order.py — pure domain, stdlib only
from dataclasses import dataclass, field
from decimal import Decimal

@dataclass
class Order:
    id: str
    customer_id: str
    total: Decimal
    lines: list[str] = field(default_factory=list)

    def add_line(self, sku: str, price: Decimal) -> None:
        if price < 0:
            raise ValueError("price cannot be negative")
        self.lines.append(sku)
        self.total += price
```

```python
# application/ports.py — the outgoing port the use case requires
from typing import Protocol
from domain.order import Order

class OrderRepository(Protocol):
    def save(self, order: Order) -> None: ...
    def get(self, order_id: str) -> Order | None: ...
```

```python
# application/place_order.py — the use case depends on the PORT, not a driver
from decimal import Decimal
from domain.order import Order
from application.ports import OrderRepository

class PlaceOrder:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders  # injected; the service never names a concrete class

    def execute(self, order_id: str, customer_id: str, sku: str, price: Decimal) -> Order:
        order = Order(id=order_id, customer_id=customer_id, total=Decimal("0"))
        order.add_line(sku, price)
        self._orders.save(order)
        return order
```

```python
# infrastructure/in_memory_orders.py — fast test adapter
from domain.order import Order

class InMemoryOrderRepository:
    def __init__(self) -> None:
        self._store: dict[str, Order] = {}

    def save(self, order: Order) -> None:
        self._store[order.id] = order

    def get(self, order_id: str) -> Order | None:
        return self._store.get(order_id)
```

```python
# infrastructure/sql_orders.py — production adapter, only this file knows SQL
from decimal import Decimal
from domain.order import Order

class SqlOrderRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def save(self, order: Order) -> None:
        self._conn.execute(
            "INSERT INTO orders (id, customer_id, total) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET total = excluded.total",
            (order.id, order.customer_id, str(order.total)),
        )
        self._conn.commit()

    def get(self, order_id: str) -> Order | None:
        row = self._conn.execute(
            "SELECT id, customer_id, total FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        if row is None:
            return None
        return Order(id=row[0], customer_id=row[1], total=Decimal(row[2]))
```

Both adapters satisfy `OrderRepository` structurally. The composition root chooses one:

```python
# main.py — the only place that knows concrete types
import sqlite3
from application.place_order import PlaceOrder
from infrastructure.sql_orders import SqlOrderRepository

service = PlaceOrder(SqlOrderRepository(sqlite3.connect("orders.db")))
```

## How the boundary enables testing

Because `PlaceOrder` depends on the port, the test injects `InMemoryOrderRepository` and exercises the full use case with no database, no I/O, and no mocking framework. The in-memory adapter is a real implementation of the same contract, so it is a fake, not a mock — there are no brittle call-count assertions, just observable state.

```python
from decimal import Decimal
from application.place_order import PlaceOrder
from infrastructure.in_memory_orders import InMemoryOrderRepository

def test_place_order_persists_total() -> None:
    repo = InMemoryOrderRepository()
    service = PlaceOrder(repo)

    order = service.execute("o1", "c1", "sku-9", Decimal("12.50"))

    assert repo.get("o1") is order
    assert order.total == Decimal("12.50")
```

To guarantee the fake and the real adapter stay interchangeable, write one contract test (a `pytest` parametrized suite or a shared abstract test case) that runs the same assertions against both `InMemoryOrderRepository` and `SqlOrderRepository`. If the SQL adapter drifts from the contract the in-memory tests assume, that shared suite fails — this is what keeps the fake honest. Swapping a database, or REST for gRPC, then requires only a new adapter plus its pass through the contract suite; the domain and use-case tests never change.

## Common pitfalls

- Importing an ORM model, `requests`, or a cloud SDK inside a domain or application module. It re-couples the core to infrastructure, so the rules can no longer be tested or reused without spinning up that dependency.
- A port signature that returns rows, JSON, or `Response` objects instead of domain types. The transport shape leaks across the boundary, and every caller now depends on the storage detail the port was meant to hide.
- Putting business logic inside an adapter (validation in the controller, calculations in the repository). The rule becomes untestable without the framework and silently diverges between adapters.
- Constructing concrete adapters deep inside services with `SqlOrderRepository()` rather than injecting them. It defeats dependency inversion: the service now names infrastructure and cannot be tested with a fake.
- One "port" per database table or per HTTP endpoint. Ports model what the use case needs, not the persistence schema; table-shaped ports are just the database leaking through a renamed layer.
- Mocking the port with `unittest.mock` instead of writing a real in-memory adapter. Mock-based tests assert on calls, not behavior, and pass even when the production adapter is broken.
- No contract test shared between the fake and the real adapter, so the in-memory version drifts and green unit tests hide a broken production path.

## Definition of done

- [ ] Domain and application modules import no framework, ORM, driver, or network client; they run under the standard library alone.
- [ ] Every outgoing dependency is an explicit port (`Protocol` or ABC) declared by the application, speaking in domain types.
- [ ] Driving adapters call the application; driven adapters implement the ports; the dependency arrow points inward everywhere.
- [ ] Concrete adapters are constructed and injected only at the composition root; no service names a concrete infrastructure class.
- [ ] At least one fake (in-memory) adapter exists for each driven port and is used in use-case tests.
- [ ] A shared contract test runs the same assertions against the fake and the real adapter so they cannot drift.
- [ ] Swapping an adapter (new database, new transport) requires no edit inside the domain or application layers.
