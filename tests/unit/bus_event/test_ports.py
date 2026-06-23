"""Unit tests for BusEventManager Protocol and Pydantic models.

Tests cover:
- BusEventManager Protocol contract (publish, subscribe, unsubscribe, list_subscriptions, get_json_schema)
- Protocol is runtime-checkable
- EventEnvelope Pydantic model validation
- BusConfig Pydantic model validation

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.bus_event.models import BusConfig, EventEnvelope
from core_infrastructure.bus_event.ports import BusEventManager


class TestBusEventManagerProtocol:
    """Verify BusEventManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """BusEventManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(BusEventManager, "_is_runtime_protocol") or hasattr(
            BusEventManager, "__protocol_attrs__"
        )

    def test_has_publish_method(self) -> None:
        """Protocol requires async publish(event_type, payload, metadata)."""
        assert hasattr(BusEventManager, "publish")

    def test_has_subscribe_method(self) -> None:
        """Protocol requires async subscribe(event_type, handler, subscriber_id)."""
        assert hasattr(BusEventManager, "subscribe")

    def test_has_unsubscribe_method(self) -> None:
        """Protocol requires async unsubscribe(subscription_id)."""
        assert hasattr(BusEventManager, "unsubscribe")

    def test_has_list_subscriptions_method(self) -> None:
        """Protocol requires async list_subscriptions() -> list[dict]."""
        assert hasattr(BusEventManager, "list_subscriptions")

    def test_has_get_json_schema_static_method(self) -> None:
        """Protocol requires static get_json_schema() -> dict."""
        assert hasattr(BusEventManager, "get_json_schema")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all BusEventManager methods satisfies the protocol."""

        class ValidBusEvent:
            async def publish(self, event_type, payload, metadata=None): ...  # type: ignore[empty-body]
            async def subscribe(self, event_type, handler, subscriber_id): ...  # type: ignore[empty-body]
            async def unsubscribe(self, subscription_id): ...  # type: ignore[empty-body]
            async def list_subscriptions(self): ...  # type: ignore[empty-body]

            @staticmethod
            def get_json_schema(): ...  # type: ignore[empty-body]

        assert isinstance(ValidBusEvent(), BusEventManager)

    def test_class_missing_publish_fails_protocol(self) -> None:
        """A class without publish() does NOT satisfy BusEventManager."""

        class Incomplete:
            async def subscribe(self, event_type, handler, subscriber_id): ...  # type: ignore[empty-body]

        assert not isinstance(Incomplete(), BusEventManager)


class TestEventEnvelopeModel:
    """Verify EventEnvelope Pydantic model validation."""

    def test_event_envelope_creation_with_required_fields(self) -> None:
        """EventEnvelope creates with event_id, event_type, payload."""
        envelope = EventEnvelope(
            event_id="evt-001",
            event_type="user.created",
            payload={"user_id": "usr-42", "email": "a@b.com"},
        )
        assert envelope.event_id == "evt-001"
        assert envelope.event_type == "user.created"
        assert envelope.payload == {"user_id": "usr-42", "email": "a@b.com"}
        assert envelope.metadata is None

    def test_event_envelope_with_metadata(self) -> None:
        """EventEnvelope accepts optional metadata dict."""
        envelope = EventEnvelope(
            event_id="evt-002",
            event_type="order.shipped",
            payload={"order_id": "ord-99"},
            metadata={"trace_id": "abc123", "tenant": "cntrs"},
        )
        assert envelope.metadata == {"trace_id": "abc123", "tenant": "cntrs"}

    def test_event_id_is_required(self) -> None:
        """EventEnvelope.event_id must not be empty."""
        with pytest.raises(PydanticValidationError):
            EventEnvelope(event_id="", event_type="test.event", payload={})

    def test_event_type_is_required(self) -> None:
        """EventEnvelope.event_type must not be empty."""
        with pytest.raises(PydanticValidationError):
            EventEnvelope(event_id="evt-003", event_type="", payload={})

    def test_payload_accepts_complex_nested(self) -> None:
        """EventEnvelope.payload accepts nested dicts/lists."""
        envelope = EventEnvelope(
            event_id="evt-004",
            event_type="data.updated",
            payload={
                "changes": {"field_a": "new_val", "field_b": 42},
                "tags": ["important", "critical"],
                "nested": {"deep": {"value": True}},
            },
        )
        assert envelope.payload["changes"]["field_b"] == 42
        assert envelope.payload["tags"] == ["important", "critical"]


class TestBusConfigModel:
    """Verify BusConfig Pydantic model validation."""

    def test_default_config(self) -> None:
        """BusConfig creates with sensible defaults."""
        config = BusConfig()
        assert config.max_queue_size == 1000
        assert config.default_handler_timeout == 30.0

    def test_custom_config(self) -> None:
        """BusConfig accepts custom values."""
        config = BusConfig(max_queue_size=500, default_handler_timeout=10.0)
        assert config.max_queue_size == 500
        assert config.default_handler_timeout == 10.0

    def test_negative_max_queue_size_fails(self) -> None:
        """max_queue_size must be >= 1."""
        with pytest.raises(PydanticValidationError):
            BusConfig(max_queue_size=0)

    def test_negative_handler_timeout_fails(self) -> None:
        """default_handler_timeout must be > 0."""
        with pytest.raises(PydanticValidationError):
            BusConfig(default_handler_timeout=0.0)
