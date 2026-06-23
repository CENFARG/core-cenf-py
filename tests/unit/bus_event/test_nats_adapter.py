"""Unit tests for NatsBusAdapter — NATS JetStream-backed event bus.

Tests cover:
- Protocol compliance (satisfies BusEventManager)
- Subject naming pattern cenf.bus.{event_type}
- publish() publishes to NATS JetStream subject
- subscribe() creates JetStream durable consumer
- unsubscribe() removes consumer and cleans up
- Reconnection handling (auto-reconnect via NATS client)
- list_subscriptions() returns JetStream-backed subscriptions
- CloudEvents envelope format (to_cloudevent() on EventEnvelope)

Uses unittest.mock to mock nats.aio.client and nats.js.api.JetStreamContext
to avoid requiring a real NATS server.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core_infrastructure.bus_event.models import BusConfig, EventEnvelope
from core_infrastructure.bus_event.ports import BusEventManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bus_config() -> BusConfig:
    """Create a default BusConfig for testing."""
    return BusConfig(max_queue_size=100, default_handler_timeout=5.0)


@pytest.fixture
def mock_nats_client() -> AsyncMock:
    """Create a mock NATS client with JetStream support."""
    import asyncio

    client = AsyncMock()

    # JetStream mock
    mock_js = AsyncMock()
    mock_js.publish = AsyncMock(return_value=MagicMock(seq=1))
    # pull_subscribe raises CancelledError so background listeners exit cleanly
    mock_js.pull_subscribe = AsyncMock(side_effect=asyncio.CancelledError)
    # add_stream and add_consumer are idempotent no-ops in tests
    mock_js.add_stream = AsyncMock()
    mock_js.add_consumer = AsyncMock()
    mock_js.delete_consumer = AsyncMock()
    client.jetstream = AsyncMock(return_value=mock_js)

    # Subscribe mock (unused in JetStream path but needed for completeness)
    mock_sub = AsyncMock()
    client.subscribe = AsyncMock(return_value=mock_sub)

    # Drain mock
    client.drain = AsyncMock()

    return client


@pytest.fixture
def mock_js_context(mock_nats_client: AsyncMock) -> AsyncMock:
    """Get the mock JetStream context from the NATS client."""
    return mock_nats_client.jetstream.return_value


@pytest.fixture
def adapter(bus_config: BusConfig, mock_nats_client: AsyncMock) -> Any:
    """Create a NatsBusAdapter with mocked NATS client.

    We import NatsBusAdapter here so the module is only loaded during tests.
    """
    from core_infrastructure.bus_event.adapters.nats_bus_adapter import (
        NatsBusAdapter,
    )

    adapter = NatsBusAdapter(
        config=bus_config,
        config_manager=MagicMock(),
        secret_manager=MagicMock(),
        logger_manager=MagicMock(),
        error_manager=MagicMock(),
    )
    adapter._nc = mock_nats_client
    adapter._js = mock_nats_client.jetstream.return_value
    adapter._started = True
    return adapter


# ---------------------------------------------------------------------------
# Subject naming
# ---------------------------------------------------------------------------


class TestSubjectNaming:
    """Verify NATS subject naming convention."""

    def test_subject_name_format(self) -> None:
        """Subject name follows the cenf.bus.{event_type} pattern."""
        from core_infrastructure.bus_event.adapters.nats_bus_adapter import (
            NatsBusAdapter,
        )

        subject = NatsBusAdapter._subject_name("user.created")
        assert subject == "cenf.bus.user.created"

    def test_subject_name_with_special_chars(self) -> None:
        """Subject name handles event types with dots and hyphens."""
        from core_infrastructure.bus_event.adapters.nats_bus_adapter import (
            NatsBusAdapter,
        )

        subject = NatsBusAdapter._subject_name("order.item-shipped")
        assert subject == "cenf.bus.order.item-shipped"

    def test_stream_name_format(self) -> None:
        """Stream name is derived from event type."""
        from core_infrastructure.bus_event.adapters.nats_bus_adapter import (
            NatsBusAdapter,
        )

        stream = NatsBusAdapter._stream_name("user.created")
        assert stream.startswith("cenf_bus_")
        assert "user" in stream
        assert "created" in stream

    def test_consumer_name_format(self) -> None:
        """Consumer (durable) name includes subscriber_id."""
        from core_infrastructure.bus_event.adapters.nats_bus_adapter import (
            NatsBusAdapter,
        )

        consumer = NatsBusAdapter._consumer_name("user.created", "svc-1")
        assert consumer.startswith("cenf_bus_")
        assert "user" in consumer
        # Hyphens are sanitized to underscores in durable names
        assert "svc_1" in consumer


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestNatsBusAdapterProtocol:
    """Verify NatsBusAdapter satisfies BusEventManager Protocol."""

    def test_satisfies_bus_event_manager_protocol(self, adapter: Any) -> None:
        """NatsBusAdapter passes isinstance check."""
        assert isinstance(adapter, BusEventManager)

    def test_has_publish_method(self, adapter: Any) -> None:
        """Adapter exposes publish() method."""
        assert hasattr(adapter, "publish")
        assert callable(adapter.publish)

    def test_has_subscribe_method(self, adapter: Any) -> None:
        """Adapter exposes subscribe() method."""
        assert hasattr(adapter, "subscribe")
        assert callable(adapter.subscribe)

    def test_has_unsubscribe_method(self, adapter: Any) -> None:
        """Adapter exposes unsubscribe() method."""
        assert hasattr(adapter, "unsubscribe")
        assert callable(adapter.unsubscribe)

    def test_has_list_subscriptions_method(self, adapter: Any) -> None:
        """Adapter exposes list_subscriptions() method."""
        assert hasattr(adapter, "list_subscriptions")
        assert callable(adapter.list_subscriptions)

    def test_has_get_json_schema_static_method(self, adapter: Any) -> None:
        """Adapter exposes get_json_schema() static method."""
        assert hasattr(type(adapter), "get_json_schema")
        schema = type(adapter).get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


class TestPublish:
    """Verify publish() uses NATS JetStream."""

    @pytest.mark.asyncio
    async def test_publish_returns_event_id(self, adapter: Any) -> None:
        """publish() returns a non-empty event_id string."""
        event_id = await adapter.publish("test.event", {"msg": "hello"})
        assert isinstance(event_id, str)
        assert len(event_id) > 0

    @pytest.mark.asyncio
    async def test_publish_calls_jetstream_publish(self, adapter: Any, mock_js_context: AsyncMock) -> None:
        """publish() calls JetStream publish with correct subject and CloudEvents payload."""
        event_id = await adapter.publish("user.created", {"user_id": "usr-1"})

        mock_js_context.publish.assert_called_once()
        call_kwargs = mock_js_context.publish.call_args.kwargs

        assert call_kwargs["subject"] == "cenf.bus.user.created"

        # Payload should be CloudEvents envelope as JSON bytes
        payload = call_kwargs["payload"]
        assert isinstance(payload, bytes)

        import json

        message = json.loads(payload.decode("utf-8"))
        # CloudEvents fields (not raw EventEnvelope fields)
        assert message["type"] == "user.created"
        assert message["data"] == {"user_id": "usr-1"}
        assert message["id"] == event_id
        assert message["specversion"] == "1.0"
        assert message["datacontenttype"] == "application/json"

    @pytest.mark.asyncio
    async def test_publish_with_metadata(self, adapter: Any, mock_js_context: AsyncMock) -> None:
        """publish() includes metadata as CloudEvents cenfmetadata extension."""
        await adapter.publish(
            "sys.event",
            {"data": "test"},
            metadata={"trace_id": "abc-123"},
        )

        call_kwargs = mock_js_context.publish.call_args.kwargs
        payload = call_kwargs["payload"]

        import json

        message = json.loads(payload.decode("utf-8"))
        assert message["cenfmetadata"] == {"trace_id": "abc-123"}

    @pytest.mark.asyncio
    async def test_publish_not_started_raises(self, bus_config: BusConfig) -> None:
        """publish() raises RuntimeError if adapter is not started."""
        from core_infrastructure.bus_event.adapters.nats_bus_adapter import (
            NatsBusAdapter,
        )

        adapter = NatsBusAdapter(
            config=bus_config,
            config_manager=MagicMock(),
            secret_manager=MagicMock(),
            logger_manager=MagicMock(),
            error_manager=MagicMock(),
        )
        adapter._started = False
        with pytest.raises(RuntimeError, match="not started"):
            await adapter.publish("test.event", {})


# ---------------------------------------------------------------------------
# Subscribe
# ---------------------------------------------------------------------------


class TestSubscribe:
    """Verify subscribe() creates JetStream durable consumer."""

    @pytest.mark.asyncio
    async def test_subscribe_returns_subscription_id(self, adapter: Any) -> None:
        """subscribe() returns a unique subscription_id."""

        async def handler(envelope: Any) -> None:
            pass

        sub_id = await adapter.subscribe("test.event", handler, "sub-1")
        assert isinstance(sub_id, str)
        assert len(sub_id) > 0

    @pytest.mark.asyncio
    async def test_subscribe_creates_durable_consumer(self, adapter: Any) -> None:
        """subscribe() creates a JetStream pull subscription with durable name."""

        async def handler(envelope: Any) -> None:
            pass

        sub_id = await adapter.subscribe("user.created", handler, "sub-1")

        # Check internal tracking
        assert sub_id in adapter._subscriptions
        assert adapter._subscriptions[sub_id]["event_type"] == "user.created"
        assert adapter._subscriptions[sub_id]["subscriber_id"] == "sub-1"
        assert adapter._subscriptions[sub_id]["handler"] is handler

    @pytest.mark.asyncio
    async def test_subscribe_not_started_raises(self, bus_config: BusConfig) -> None:
        """subscribe() raises RuntimeError if adapter is not started."""
        from core_infrastructure.bus_event.adapters.nats_bus_adapter import (
            NatsBusAdapter,
        )

        adapter = NatsBusAdapter(
            config=bus_config,
            config_manager=MagicMock(),
            secret_manager=MagicMock(),
            logger_manager=MagicMock(),
            error_manager=MagicMock(),
        )
        adapter._started = False
        with pytest.raises(RuntimeError, match="not started"):
            await adapter.subscribe("test.event", lambda e: None, "sub-1")


# ---------------------------------------------------------------------------
# Unsubscribe
# ---------------------------------------------------------------------------


class TestUnsubscribe:
    """Verify unsubscribe() cleans up consumers."""

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_subscription(self, adapter: Any) -> None:
        """unsubscribe() removes the subscription from tracking."""

        async def handler(envelope: Any) -> None:
            pass

        sub_id = await adapter.subscribe("test.event", handler, "sub-1")
        await adapter.unsubscribe(sub_id)

        # Subscription should be removed
        assert sub_id not in adapter._subscriptions

    @pytest.mark.asyncio
    async def test_unsubscribe_unknown_id_is_noop(self, adapter: Any) -> None:
        """unsubscribe() on unknown ID does not raise."""
        await adapter.unsubscribe("nonexistent-id")  # Should not raise

    @pytest.mark.asyncio
    async def test_unsubscribe_cancels_listener_task(self, adapter: Any) -> None:
        """unsubscribe() cancels the background listener task."""

        async def handler(envelope: Any) -> None:
            pass

        sub_id = await adapter.subscribe("test.event", handler, "sub-1")

        # Listener task should exist
        assert sub_id in adapter._listener_tasks
        task = adapter._listener_tasks[sub_id]
        assert not task.done()  # Task should be running

        await adapter.unsubscribe(sub_id)

        # Task should be cancelled/removed
        assert sub_id not in adapter._listener_tasks


# ---------------------------------------------------------------------------
# List subscriptions
# ---------------------------------------------------------------------------


class TestListSubscriptions:
    """Verify list_subscriptions() with NATS backend."""

    @pytest.mark.asyncio
    async def test_list_subscriptions_empty_initially(self, adapter: Any) -> None:
        """list_subscriptions() returns empty list with no subscriptions."""
        subs = await adapter.list_subscriptions()
        assert subs == []

    @pytest.mark.asyncio
    async def test_list_subscriptions_returns_active(self, adapter: Any) -> None:
        """list_subscriptions() returns active subscriptions."""

        async def handler(envelope: Any) -> None:
            pass

        sub_id = await adapter.subscribe("user.created", handler, "sub-1")
        subs = await adapter.list_subscriptions()

        assert len(subs) == 1
        assert subs[0]["subscription_id"] == sub_id
        assert subs[0]["event_type"] == "user.created"
        assert subs[0]["subscriber_id"] == "sub-1"


# ---------------------------------------------------------------------------
# Reconnection
# ---------------------------------------------------------------------------


class TestReconnection:
    """Verify auto-reconnection handling."""

    @pytest.mark.asyncio
    async def test_subscribe_records_subject_for_reconnection(self, adapter: Any) -> None:
        """subscribe() records subject for reconnection tracking."""

        async def handler(envelope: Any) -> None:
            pass

        sub_id = await adapter.subscribe("user.created", handler, "sub-1")

        # Check internal tracking includes subject and consumer info
        assert sub_id in adapter._subscriptions
        assert adapter._subscriptions[sub_id]["subject"] == "cenf.bus.user.created"
        assert adapter._subscriptions[sub_id]["handler"] is handler

    @pytest.mark.asyncio
    async def test_drain_on_stop(self, adapter: Any, mock_nats_client: AsyncMock) -> None:
        """stop() drains NATS connections gracefully."""

        async def handler(envelope: Any) -> None:
            pass

        await adapter.subscribe("test.event", handler, "sub-1")

        await adapter.stop()

        mock_nats_client.drain.assert_called_once()


# ---------------------------------------------------------------------------
# CloudEvents envelope
# ---------------------------------------------------------------------------


class TestCloudEventsEnvelope:
    """Verify CloudEvents envelope format on EventEnvelope."""

    def test_to_cloudevent_produces_valid_envelope(self) -> None:
        """to_cloudevent() returns dict with all required CE attributes."""

        envelope = EventEnvelope(
            event_id="evt-001",
            event_type="user.created",
            payload={"user_id": "usr-1"},
            metadata={"trace_id": "trc-123"},
        )

        ce = envelope.to_cloudevent(source="cenf-service")

        assert ce["specversion"] == "1.0"
        assert ce["type"] == "user.created"
        assert ce["source"] == "cenf-service"
        assert ce["id"] == "evt-001"
        assert ce["datacontenttype"] == "application/json"
        assert ce["data"] == {"user_id": "usr-1"}
        assert "time" in ce

    def test_to_cloudevent_time_is_utc(self) -> None:
        """to_cloudevent() 'time' field is in UTC."""
        envelope = EventEnvelope(
            event_id="evt-002",
            event_type="order.created",
            payload={},
        )
        ce = envelope.to_cloudevent(source="test-svc")
        time_str = ce["time"]
        # Verify it ends with 'Z' (UTC zone designator) and is valid ISO8601
        assert time_str.endswith("Z") or "+00:00" in time_str

    def test_to_cloudevent_uses_provided_source(self) -> None:
        """to_cloudevent() uses the provided source argument."""
        envelope = EventEnvelope(
            event_id="evt-003",
            event_type="payment.succeeded",
            payload={},
        )
        ce = envelope.to_cloudevent(source="billing-svc")
        assert ce["source"] == "billing-svc"

    def test_cloud_event_pydantic_model_validates(self) -> None:
        """CloudEvent Pydantic model validates required fields."""
        from core_infrastructure.bus_event.models import CloudEvent

        ce = CloudEvent(
            specversion="1.0",
            type="user.created",
            source="cenf-service",
            id="evt-001",
            time=datetime.datetime.now(datetime.UTC).isoformat(),
            datacontenttype="application/json",
            data={"user_id": "usr-1"},
        )

        assert ce.specversion == "1.0"
        assert ce.type == "user.created"
        assert ce.source == "cenf-service"
        assert ce.id == "evt-001"
        assert ce.datacontenttype == "application/json"
        assert ce.data == {"user_id": "usr-1"}

    def test_cloud_event_missing_required_raises(self) -> None:
        """CloudEvent raises ValidationError when required fields are missing."""
        from pydantic import ValidationError

        from core_infrastructure.bus_event.models import CloudEvent

        with pytest.raises(ValidationError):
            CloudEvent(
                specversion="1.0",
                # missing 'type'
                source="cenf-service",
                id="evt-001",
            )


# ---------------------------------------------------------------------------
# get_json_schema
# ---------------------------------------------------------------------------


class TestGetJsonSchema:
    """Verify get_json_schema() static method."""

    def test_get_json_schema_returns_dict(self, adapter: Any) -> None:
        """get_json_schema() returns a valid dict."""
        schema = type(adapter).get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0
