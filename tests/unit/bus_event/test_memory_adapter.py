"""Unit tests for MemoryBusAdapter — in-process asyncio-based event bus.

Tests cover:
- Protocol compliance (satisfies BusEventManager)
- publish() returns event_id and delivers events to subscribers
- subscribe() returns subscription_id and callback is invoked
- unsubscribe() stops delivery
- list_subscriptions() returns active subscriptions
- Multiple subscribers for same event_type all receive events
- Different event_types are isolated
- Async handler dispatch (callbacks run asynchronously)
- Handler error isolation (one failing handler doesn't affect others)
- Fire-and-forget semantics (publisher doesn't wait for handlers)

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from core_infrastructure.bus_event.adapters.memory_bus_adapter import (
    MemoryBusAdapter,
)
from core_infrastructure.bus_event.models import BusConfig
from core_infrastructure.bus_event.ports import BusEventManager


@pytest.fixture
def bus_config() -> BusConfig:
    """Create a default BusConfig for testing."""
    return BusConfig(max_queue_size=100, default_handler_timeout=5.0)


@pytest.fixture
def adapter(bus_config: BusConfig) -> MemoryBusAdapter:
    """Create a MemoryBusAdapter with default config."""
    return MemoryBusAdapter(config=bus_config)


class TestMemoryBusAdapterProtocol:
    """Verify MemoryBusAdapter satisfies BusEventManager Protocol."""

    def test_satisfies_bus_event_manager_protocol(self, adapter: MemoryBusAdapter) -> None:
        """MemoryBusAdapter passes isinstance check."""
        assert isinstance(adapter, BusEventManager)

    def test_has_publish_method(self, adapter: MemoryBusAdapter) -> None:
        """Adapter exposes publish() method."""
        assert hasattr(adapter, "publish")
        assert callable(adapter.publish)

    def test_has_subscribe_method(self, adapter: MemoryBusAdapter) -> None:
        """Adapter exposes subscribe() method."""
        assert hasattr(adapter, "subscribe")
        assert callable(adapter.subscribe)


class TestPublish:
    """Verify publish() behavior."""

    @pytest.mark.asyncio
    async def test_publish_returns_event_id(self, adapter: MemoryBusAdapter) -> None:
        """publish() returns a non-empty event_id string."""
        event_id = await adapter.publish("test.event", {"msg": "hello"})
        assert isinstance(event_id, str)
        assert len(event_id) > 0

    @pytest.mark.asyncio
    async def test_publish_delivers_to_single_subscriber(self, adapter: MemoryBusAdapter) -> None:
        """publish() delivers the event to a subscribed handler."""
        received: list[dict[str, Any]] = []

        async def handler(envelope: Any) -> None:
            received.append(envelope.payload)

        await adapter.subscribe("user.created", handler, "test-subscriber")
        await adapter.publish("user.created", {"user_id": "usr-1"})

        # Allow async dispatch to complete
        await asyncio.sleep(0.1)

        assert len(received) == 1
        assert received[0] == {"user_id": "usr-1"}

    @pytest.mark.asyncio
    async def test_publish_delivers_to_multiple_subscribers(self, adapter: MemoryBusAdapter) -> None:
        """publish() delivers the same event to all subscribers of event_type."""
        received_a: list[dict[str, Any]] = []
        received_b: list[dict[str, Any]] = []

        async def handler_a(envelope: Any) -> None:
            received_a.append(envelope.payload)

        async def handler_b(envelope: Any) -> None:
            received_b.append(envelope.payload)

        await adapter.subscribe("order.created", handler_a, "sub-a")
        await adapter.subscribe("order.created", handler_b, "sub-b")
        await adapter.publish("order.created", {"order_id": "ord-1"})

        await asyncio.sleep(0.1)

        assert len(received_a) == 1
        assert len(received_b) == 1
        assert received_a[0] == {"order_id": "ord-1"}
        assert received_b[0] == {"order_id": "ord-1"}

    @pytest.mark.asyncio
    async def test_different_event_types_isolated(self, adapter: MemoryBusAdapter) -> None:
        """Subscribers only receive events for their subscribed event_type."""
        received: list[dict[str, Any]] = []

        async def handler(envelope: Any) -> None:
            received.append(envelope.payload)

        await adapter.subscribe("user.created", handler, "sub-1")
        await adapter.publish("user.deleted", {"user_id": "usr-2"})

        await asyncio.sleep(0.1)

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_publish_with_metadata(self, adapter: MemoryBusAdapter) -> None:
        """publish() passes metadata through the EventEnvelope."""
        received_metadata: list[dict[str, Any] | None] = []

        async def handler(envelope: Any) -> None:
            received_metadata.append(envelope.metadata)

        await adapter.subscribe("sys.event", handler, "sub-1")
        await adapter.publish(
            "sys.event",
            {"data": "test"},
            metadata={"trace_id": "abc-123", "tenant": "cntrs"},
        )

        await asyncio.sleep(0.1)

        assert len(received_metadata) == 1
        assert received_metadata[0] == {"trace_id": "abc-123", "tenant": "cntrs"}


class TestSubscribe:
    """Verify subscribe() behavior."""

    @pytest.mark.asyncio
    async def test_subscribe_returns_subscription_id(self, adapter: MemoryBusAdapter) -> None:
        """subscribe() returns a unique subscription_id string."""

        async def handler(envelope: Any) -> None:
            pass

        sub_id = await adapter.subscribe("test.event", handler, "sub-1")
        assert isinstance(sub_id, str)
        assert len(sub_id) > 0

    @pytest.mark.asyncio
    async def test_subscribe_multiple_returns_unique_ids(self, adapter: MemoryBusAdapter) -> None:
        """subscribe() returns unique IDs for different subscriptions."""

        async def handler_a(envelope: Any) -> None:
            pass

        async def handler_b(envelope: Any) -> None:
            pass

        id1 = await adapter.subscribe("test.event", handler_a, "sub-a")
        id2 = await adapter.subscribe("test.event", handler_b, "sub-b")

        assert id1 != id2


class TestUnsubscribe:
    """Verify unsubscribe() behavior."""

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_delivery(self, adapter: MemoryBusAdapter) -> None:
        """After unsubscribe(), the handler no longer receives events."""
        received: list[dict[str, Any]] = []

        async def handler(envelope: Any) -> None:
            received.append(envelope.payload)

        sub_id = await adapter.subscribe("test.event", handler, "sub-1")

        # First publish — should be received
        await adapter.publish("test.event", {"msg": "first"})
        await asyncio.sleep(0.1)
        assert len(received) == 1

        # Unsubscribe
        await adapter.unsubscribe(sub_id)

        # Second publish — should NOT be received
        await adapter.publish("test.event", {"msg": "second"})
        await asyncio.sleep(0.1)

        assert len(received) == 1  # Still only the first one

    @pytest.mark.asyncio
    async def test_unsubscribe_unknown_id_is_noop(self, adapter: MemoryBusAdapter) -> None:
        """unsubscribe() on an unknown ID does not raise."""
        await adapter.unsubscribe("nonexistent-id")  # Should not raise


class TestListSubscriptions:
    """Verify list_subscriptions() behavior."""

    @pytest.mark.asyncio
    async def test_list_subscriptions_empty_initially(self, adapter: MemoryBusAdapter) -> None:
        """list_subscriptions() returns empty list with no subscriptions."""
        subs = await adapter.list_subscriptions()
        assert subs == []

    @pytest.mark.asyncio
    async def test_list_subscriptions_returns_active_after_subscribe(self, adapter: MemoryBusAdapter) -> None:
        """list_subscriptions() returns entries for active subscriptions."""

        async def handler(envelope: Any) -> None:
            pass

        sub_id = await adapter.subscribe("user.created", handler, "sub-1")
        subs = await adapter.list_subscriptions()

        assert len(subs) == 1
        assert subs[0]["subscription_id"] == sub_id
        assert subs[0]["event_type"] == "user.created"
        assert subs[0]["subscriber_id"] == "sub-1"

    @pytest.mark.asyncio
    async def test_list_subscriptions_does_not_include_unsubscribed(self, adapter: MemoryBusAdapter) -> None:
        """list_subscriptions() excludes unsubscribed handlers."""

        async def handler(envelope: Any) -> None:
            pass

        sub_id = await adapter.subscribe("test.event", handler, "sub-1")
        await adapter.unsubscribe(sub_id)

        subs = await adapter.list_subscriptions()
        assert len(subs) == 0


class TestHandlerErrorIsolation:
    """Verify handler errors don't affect the bus or other handlers."""

    @pytest.mark.asyncio
    async def test_failing_handler_does_not_block_others(self, adapter: MemoryBusAdapter) -> None:
        """One handler raising doesn't prevent other handlers from receiving."""

        received_ok: list[dict[str, Any]] = []

        async def failing_handler(envelope: Any) -> None:
            raise RuntimeError("Handler crashed!")

        async def ok_handler(envelope: Any) -> None:
            received_ok.append(envelope.payload)

        await adapter.subscribe("test.event", failing_handler, "bad-sub")
        await adapter.subscribe("test.event", ok_handler, "good-sub")

        # This should not raise
        await adapter.publish("test.event", {"msg": "hello"})
        await asyncio.sleep(0.1)

        assert len(received_ok) == 1
        assert received_ok[0] == {"msg": "hello"}

    @pytest.mark.asyncio
    async def test_publish_does_not_raise_on_handler_error(self, adapter: MemoryBusAdapter) -> None:
        """publish() does not propagate handler exceptions to the publisher."""

        async def crashing_handler(envelope: Any) -> None:
            raise RuntimeError("Boom!")

        await adapter.subscribe("test.event", crashing_handler, "bad-sub")

        # This should NOT raise
        event_id = await adapter.publish("test.event", {"msg": "test"})
        await asyncio.sleep(0.1)

        assert len(event_id) > 0  # publish() succeeded regardless

    @pytest.mark.asyncio
    async def test_slow_handler_does_not_block_publisher(self, adapter: MemoryBusAdapter) -> None:
        """publish() returns before slow handlers complete."""

        slow_done = False

        async def slow_handler(envelope: Any) -> None:
            nonlocal slow_done
            await asyncio.sleep(0.5)
            slow_done = True

        await adapter.subscribe("test.event", slow_handler, "slow-sub")

        event_id = await adapter.publish("test.event", {"msg": "fast"})
        # publish() should return immediately, before handler finishes
        assert len(event_id) > 0
        assert not slow_done  # Handler hasn't finished yet

        await asyncio.sleep(0.6)
        assert slow_done  # Handler eventually completes


class TestGetJsonSchema:
    """Verify get_json_schema() static method."""

    def test_get_json_schema_returns_dict(self, adapter: MemoryBusAdapter) -> None:
        """get_json_schema() returns a valid dict."""
        schema = adapter.get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0
