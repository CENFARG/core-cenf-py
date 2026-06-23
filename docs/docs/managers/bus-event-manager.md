---
sidebar_position: 21
---

# BusEventManager (M21)

Decoupled publish-subscribe messaging for in-process and distributed communication. Provides fire-and-forget event publishing with exact-match routing, async handler dispatch with error isolation, and multi-adapter support from in-process asyncio.Queue through Redis Pub/Sub to NATS JetStream with CloudEvents 1.0. **Use BusEventManager para comunicación desacoplada entre componentes.**

## Protocol

`BusEventManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.bus_event.ports`.

Dual-purpose contract: embeddable library + standalone service via `bus_event/server.py` (aiohttp HTTP/WebSocket). All infrastructure managers that need publish-subscribe messaging consume this interface.

---

### `async publish(event_type, payload, metadata=None) → str`

Publish an event to all subscribers of `event_type`.

Fire-and-forget — returns the unique `event_id` immediately. Handlers are dispatched asynchronously (best-effort in the memory adapter).

```python
async def publish(
    self,
    event_type: str,
    payload: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> str: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `event_type` | `str` | Event type string (e.g., `"user.created"`) |
| `payload` | `dict[str, Any]` | JSON-serializable event payload |
| `metadata` | `dict[str, Any] \| None` | Optional metadata (trace_id, tenant_id, etc.) |

**Returns:** Unique event ID (UUID4 string).

**Raises:** `ValidationError` if payload is not JSON-serializable.

---

### `async subscribe(event_type, handler, subscriber_id) → str`

Subscribe a handler to an event type. The handler is an async callable that receives an `EventEnvelope`. Returns a unique `subscription_id` for later unsubscription.

```python
async def subscribe(
    self,
    event_type: str,
    handler: Any,
    subscriber_id: str,
) -> str: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `event_type` | `str` | Event type to subscribe to (exact match only — no wildcards) |
| `handler` | `Any` | Async callable: `async def handler(envelope: EventEnvelope) -> None` |
| `subscriber_id` | `str` | Identifier for the subscribing component |

**Returns:** Unique subscription ID.

---

### `async unsubscribe(subscription_id) → None`

Remove a subscription by its ID. **Idempotent** — calling on an unknown ID is a no-op.

```python
async def unsubscribe(self, subscription_id: str) -> None: ...
```

---

### `async list_subscriptions() → list[dict[str, Any]]`

Return metadata for all active subscriptions.

```python
async def list_subscriptions(self) -> list[dict[str, Any]]: ...
```

Each entry contains: `subscription_id`, `event_type`, `subscriber_id`.

---

### `get_json_schema() → dict[str, Any]` *(static)*

Return JSON Schema for agent discovery (AX). Returns the JSON Schema of `BusConfig`.

---

## Models

**File:** `core_infrastructure.bus_event.models`

### `EventEnvelope`

Canonical event message routed through the bus. Every event published or subscribed carries an `EventEnvelope`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `event_id` | `str` (1–64) | required | Unique event identifier (UUID4) |
| `event_type` | `str` (1–256) | required | Event type string for routing (e.g., `"user.created"`) |
| `payload` | `dict[str, Any]` | `{}` | JSON-serializable event payload |
| `metadata` | `dict[str, Any] \| None` | `None` | Optional metadata (trace_id, tenant_id, etc.) |

Has `to_cloudevent(source)` method for CloudEvents 1.0 conversion.

### `BusConfig`

Configuration for BusEventManager adapters. Controls queue size limits and handler dispatch timeouts.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_queue_size` | `int` (1–10000) | `1000` | Maximum pending events per event_type before publish blocks |
| `default_handler_timeout` | `float` (> 0.0) | `30.0` | Maximum seconds a handler can run before being cancelled |

### `CloudEvent`

CloudEvents 1.0 specification model for NATS JetStream and CE-capable transports.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `specversion` | `str` | required | CloudEvents spec version (`"1.0"`) |
| `type` | `str` (1–256) | required | Event type string |
| `source` | `str` | required | Event source identifier |
| `id` | `str` (1–64) | required | Unique event identifier |
| `time` | `str \| None` | `None` | RFC 3339 UTC timestamp |
| `datacontenttype` | `str` | `"application/json"` | Content type of `data` |
| `data` | `dict[str, Any]` | `{}` | Event payload |

---

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `MemoryBusAdapter` | `asyncio.Queue` per event_type | Dev/testing — in-process messaging, zero dependencies, reference implementation |
| `RedisBusAdapter` | `redis.asyncio` Pub/Sub | Production — multi-process messaging via `cenf:bus:{event_type}` channels, auto-reconnection |
| `NatsBusAdapter` | NATS JetStream + CloudEvents 1.0 | Production — multi-service distributed messaging with durable consumers |

**Dispatch model:** `MemoryBusAdapter` dispatches handlers as background `asyncio.Task`s with error isolation — a crashing handler never affects other subscribers or the publisher. `RedisBusAdapter` uses `SUBSCRIBE` + callback pattern with auto-resubscription on disconnect. `NatsBusAdapter` uses JetStream durable consumers with `pull_subscribe` for at-least-once delivery and CloudEvents 1.0 envelope format.

---

## Usage Example

```python
from core_infrastructure.bus_event.adapters.memory_bus_adapter import (
    MemoryBusAdapter,
)
from core_infrastructure.bus_event.models import BusConfig, EventEnvelope

# Dev/testing: MemoryBusAdapter
bus = MemoryBusAdapter(config=BusConfig())

# Define an async handler
async def on_user_created(envelope: EventEnvelope) -> None:
    user_id = envelope.payload.get("user_id")
    print(f"User created: {user_id} (event: {envelope.event_id})")

# Subscribe to an event type
sub_id = await bus.subscribe(
    event_type="user.created",
    handler=on_user_created,
    subscriber_id="notification-svc",
)

# Publish an event (fire-and-forget)
event_id = await bus.publish(
    event_type="user.created",
    payload={"user_id": "42", "email": "user@example.com"},
    metadata={"trace_id": "abc123", "tenant_id": "cntrs"},
)
print(f"Published event: {event_id}")

# List active subscriptions
subs = await bus.list_subscriptions()
# → [{"subscription_id": "...", "event_type": "user.created", "subscriber_id": "notification-svc"}]

# Unsubscribe
await bus.unsubscribe(sub_id)
```

**Production — RedisBusAdapter:**
```python
from core_infrastructure.bus_event.adapters.redis_bus_adapter import (
    RedisBusAdapter,
)

bus = RedisBusAdapter(config=BusConfig(), redis_url="redis://localhost:6379")
await bus.start()
sub_id = await bus.subscribe("user.created", on_user_created, "notification-svc")
event_id = await bus.publish("user.created", {"user_id": "42"})
await bus.unsubscribe(sub_id)
await bus.stop()
```

**Production — NatsBusAdapter (CloudEvents 1.0):**
```python
from core_infrastructure.bus_event.adapters.nats_bus_adapter import (
    NatsBusAdapter,
)

bus = NatsBusAdapter(
    config=BusConfig(),
    nats_url="nats://localhost:4222",
    source="notification-svc",
)
await bus.start()
sub_id = await bus.subscribe("user.created", on_user_created, "notification-svc")
event_id = await bus.publish("user.created", {"user_id": "42"})
await bus.unsubscribe(sub_id)
await bus.stop()
```

---

## @ai-directive

> **Usar BusEventManager para comunicación desacoplada entre componentes.** `publish()` is fire-and-forget from the publisher's perspective. Subscriptions are exact-match only (no wildcards for MVP). When adding a new adapter, implement ALL methods — `MemoryBusAdapter` is the reference implementation. Handlers run with error isolation: a crashing handler never affects other subscribers or the publisher. Event payloads MUST be JSON-serializable. `EventEnvelope.metadata` is optional but recommended for trace correlation (`trace_id`, `tenant_id`).

## Related

- [TaskQueueManager](task-queue-manager.md) — for guaranteed-delivery async jobs (vs. fire-and-forget events)
- [ObservabilityManager](observability-manager.md) — `cenf.bus.*` counters emitted on publish/subscribe
- [ConfigManager](config-manager.md) — supplies `bus.max_queue_size` and `bus.default_handler_timeout`
