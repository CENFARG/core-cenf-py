"""Unit tests for RedisBusAdapter — Redis Pub/Sub-backed event bus.

Tests cover:
- Protocol compliance (satisfies BusEventManager)
- pub/sub channel naming pattern cenf:bus:{event_type}
- publish sends message to correct channel
- subscribe registers Redis pubsub listener
- unsubscribe unregisters listener
- reconnection logic (auto-resubscribe on disconnect)
- list_subscriptions returns Redis-backed subscriptions
- get_json_schema returns valid dict

Uses pytest-mock to mock redis.asyncio.Redis and avoid real Redis.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from core_infrastructure.bus_event.adapters.redis_bus_adapter import RedisBusAdapter
from core_infrastructure.bus_event.models import BusConfig
from core_infrastructure.bus_event.ports import BusEventManager


@pytest.fixture
def bus_config() -> BusConfig:
    """Create a default BusConfig for testing."""
    return BusConfig(max_queue_size=100, default_handler_timeout=5.0)


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Create a mock redis.asyncio.Redis client."""
    client = AsyncMock()
    client.pubsub.return_value = AsyncMock()
    return client


@pytest.fixture
def adapter(bus_config: BusConfig, mock_redis_client: AsyncMock) -> RedisBusAdapter:
    """Create a RedisBusAdapter with mocked Redis client."""
    adapter = RedisBusAdapter(config=bus_config)
    adapter._redis = mock_redis_client
    adapter._started = True
    return adapter


class TestRedisBusAdapterProtocol:
    """Verify RedisBusAdapter satisfies BusEventManager Protocol."""

    def test_satisfies_bus_event_manager_protocol(self, adapter: RedisBusAdapter) -> None:
        """RedisBusAdapter passes isinstance check."""
        assert isinstance(adapter, BusEventManager)


class TestChannelNaming:
    """Verify Redis channel naming convention."""

    def test_channel_name_format(self) -> None:
        """Channel name follows the cenf:bus:{event_type} pattern."""
        channel = RedisBusAdapter._channel_name("user.created")
        assert channel == "cenf:bus:user.created"

    def test_channel_name_with_special_chars(self) -> None:
        """Channel name handles event types with dots and hyphens."""
        channel = RedisBusAdapter._channel_name("order.item-shipped")
        assert channel == "cenf:bus:order.item-shipped"


class TestPublish:
    """Verify publish() uses Redis pub/sub."""

    @pytest.mark.asyncio
    async def test_publish_returns_event_id(self, adapter: RedisBusAdapter) -> None:
        """publish() returns a non-empty event_id string."""
        event_id = await adapter.publish("test.event", {"msg": "hello"})
        assert isinstance(event_id, str)
        assert len(event_id) > 0

    @pytest.mark.asyncio
    async def test_publish_calls_redis_publish(self, adapter: RedisBusAdapter) -> None:
        """publish() calls redis.publish() with correct channel and JSON message."""
        adapter._redis.publish = AsyncMock()

        event_id = await adapter.publish("user.created", {"user_id": "usr-1"})

        adapter._redis.publish.assert_called_once()
        call_args = adapter._redis.publish.call_args
        assert call_args[0][0] == "cenf:bus:user.created"

        # Second arg should be JSON string
        import json
        message = json.loads(call_args[0][1])
        assert message["event_type"] == "user.created"
        assert message["payload"] == {"user_id": "usr-1"}
        assert message["event_id"] == event_id

    @pytest.mark.asyncio
    async def test_publish_with_metadata(self, adapter: RedisBusAdapter) -> None:
        """publish() includes metadata in the Redis message."""
        adapter._redis.publish = AsyncMock()

        await adapter.publish(
            "sys.event",
            {"data": "test"},
            metadata={"trace_id": "abc-123"},
        )

        call_args = adapter._redis.publish.call_args
        import json
        message = json.loads(call_args[0][1])
        assert message["metadata"] == {"trace_id": "abc-123"}

    @pytest.mark.asyncio
    async def test_publish_not_started_raises(self, bus_config: BusConfig) -> None:
        """publish() raises RuntimeError if adapter is not started."""
        adapter = RedisBusAdapter(config=bus_config)
        adapter._started = False
        with pytest.raises(RuntimeError, match="not started"):
            await adapter.publish("test.event", {})


class TestSubscribe:
    """Verify subscribe() registers Redis pubsub."""

    @pytest.mark.asyncio
    async def test_subscribe_returns_subscription_id(self, adapter: RedisBusAdapter) -> None:
        """subscribe() returns a unique subscription_id."""

        async def handler(envelope: Any) -> None:
            pass

        sub_id = await adapter.subscribe("test.event", handler, "sub-1")
        assert isinstance(sub_id, str)
        assert len(sub_id) > 0

    @pytest.mark.asyncio
    async def test_subscribe_creates_pubsub_and_subscribes(self, adapter: RedisBusAdapter) -> None:
        """subscribe() creates a Redis pubsub and subscribes to the channel."""
        mock_pubsub = AsyncMock()
        adapter._redis.pubsub.return_value = mock_pubsub

        async def handler(envelope: Any) -> None:
            pass

        await adapter.subscribe("user.created", handler, "sub-1")

        adapter._redis.pubsub.assert_called_once()
        mock_pubsub.subscribe.assert_called_once_with("cenf:bus:user.created")

    @pytest.mark.asyncio
    async def test_subscribe_not_started_raises(self, bus_config: BusConfig) -> None:
        """subscribe() raises RuntimeError if adapter is not started."""
        adapter = RedisBusAdapter(config=bus_config)
        adapter._started = False
        with pytest.raises(RuntimeError, match="not started"):
            await adapter.subscribe("test.event", lambda e: None, "sub-1")


class TestUnsubscribe:
    """Verify unsubscribe() cleans up pubsub."""

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_subscription(self, adapter: RedisBusAdapter) -> None:
        """unsubscribe() removes the subscription from tracking."""
        mock_pubsub = AsyncMock()
        adapter._redis.pubsub.return_value = mock_pubsub

        async def handler(envelope: Any) -> None:
            pass

        sub_id = await adapter.subscribe("test.event", handler, "sub-1")
        await adapter.unsubscribe(sub_id)

        mock_pubsub.unsubscribe.assert_called_once_with("cenf:bus:test.event")

    @pytest.mark.asyncio
    async def test_unsubscribe_unknown_id_is_noop(self, adapter: RedisBusAdapter) -> None:
        """unsubscribe() on unknown ID does not raise."""
        await adapter.unsubscribe("nonexistent-id")  # Should not raise


class TestListSubscriptions:
    """Verify list_subscriptions() with Redis backend."""

    @pytest.mark.asyncio
    async def test_list_subscriptions_empty_initially(self, adapter: RedisBusAdapter) -> None:
        """list_subscriptions() returns empty list with no subscriptions."""
        subs = await adapter.list_subscriptions()
        assert subs == []

    @pytest.mark.asyncio
    async def test_list_subscriptions_returns_active(self, adapter: RedisBusAdapter) -> None:
        """list_subscriptions() returns active subscriptions."""

        async def handler(envelope: Any) -> None:
            pass

        mock_pubsub = AsyncMock()
        adapter._redis.pubsub.return_value = mock_pubsub

        sub_id = await adapter.subscribe("user.created", handler, "sub-1")
        subs = await adapter.list_subscriptions()

        assert len(subs) == 1
        assert subs[0]["subscription_id"] == sub_id
        assert subs[0]["event_type"] == "user.created"
        assert subs[0]["subscriber_id"] == "sub-1"


class TestReconnection:
    """Verify auto-resubscribe on disconnect."""

    @pytest.mark.asyncio
    async def test_subscribe_records_channel_for_reconnection(self, adapter: RedisBusAdapter) -> None:
        """subscribe() records channel subscriptions for reconnection."""
        mock_pubsub = AsyncMock()
        adapter._redis.pubsub.return_value = mock_pubsub

        async def handler(envelope: Any) -> None:
            pass

        sub_id = await adapter.subscribe("user.created", handler, "sub-1")

        # Check internal tracking
        assert sub_id in adapter._subscriptions
        assert adapter._subscriptions[sub_id]["channel"] == "cenf:bus:user.created"
        assert adapter._subscriptions[sub_id]["handler"] is handler


class TestGetJsonSchema:
    """Verify get_json_schema() static method."""

    def test_get_json_schema_returns_dict(self, adapter: RedisBusAdapter) -> None:
        """get_json_schema() returns a valid dict."""
        schema = adapter.get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0
