"""BusEventManager Protocol — the contract every event bus adapter must satisfy.

Defines the event bus interface consumed by all infrastructure managers
for publish-subscribe messaging. Supports exact-match event type routing,
async handler dispatch, and agent discovery via JSON Schema.

Security: Handlers receive EventEnvelope with trace metadata. NEVER
    include credentials or PII in event payloads without encryption.
Observability: Publish/subscribe events emit counters under cenf.bus.*.
@ai-directive: publish() is fire-and-forget from the publisher's perspective.
    Subscriptions are exact-match only (no wildcards for MVP).

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BusEventManager(Protocol):
    """Dual-purpose event bus contract: embeddable library + standalone service.

    All infrastructure managers that need publish-subscribe messaging consume
    this interface. Concrete adapters provide in-process message passing
    (MemoryBusAdapter for dev/testing) or Redis Pub/Sub (RedisBusAdapter
    for production). A standalone aiohttp server exposes the same contract
    over HTTP/WebSocket.

    Rules:
        - publish() is fire-and-forget — returns event_id immediately.
        - subscribe() returns a unique subscription_id for later unsubscription.
        - unsubscribe() is idempotent — safe to call on unknown IDs.
        - list_subscriptions() returns subscription metadata for observability.
        - get_json_schema() is static — no instance required.

    @ai-directive: When adding a new adapter, implement ALL methods.
        The MemoryBusAdapter is the reference implementation.
    """

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Publish an event to all subscribers of event_type.

        Fire-and-forget — returns the unique event_id immediately. Handlers
        are dispatched asynchronously (best-effort, no guaranteed delivery
        in the MVP memory adapter).

        Args:
            event_type: Event type string (e.g. ``"user.created"``).
            payload: JSON-serializable event payload.
            metadata: Optional metadata dict (trace_id, tenant_id, etc.).

        Returns:
            str: The unique event ID (UUID4).

        Raises:
            ValidationError: If payload is not JSON-serializable.
        """
        ...

    async def subscribe(
        self,
        event_type: str,
        handler: Any,
        subscriber_id: str,
    ) -> str:
        """Subscribe a handler to an event type.

        The handler is an async callable that receives an ``EventEnvelope``.
        Returns a unique subscription_id for later unsubscription.

        Args:
            event_type: Event type to subscribe to (exact match).
            handler: Async callable ``async def handler(envelope: EventEnvelope) -> None``.
            subscriber_id: Identifier for the subscribing component.

        Returns:
            str: Unique subscription ID.
        """
        ...

    async def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscription by its ID.

        Idempotent — calling on an unknown ID is a no-op.

        Args:
            subscription_id: The subscription ID returned by subscribe().
        """
        ...

    async def list_subscriptions(self) -> list[dict[str, Any]]:
        """Return metadata for all active subscriptions.

        Returns:
            list[dict[str, Any]]: Each entry has at minimum:
                ``subscription_id``, ``event_type``, ``subscriber_id``.
        """
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery (AX).

        Returns:
            dict[str, Any]: A valid JSON Schema object describing the
                BusConfig model.
        """
        ...
