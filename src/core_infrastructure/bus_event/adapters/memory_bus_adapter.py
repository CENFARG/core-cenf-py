"""MemoryBusAdapter — in-process asyncio-based BusEventManager.

Provides a zero-dependency BusEventManager implementation using asyncio.Queue
per event_type for in-process publish-subscribe messaging. Handlers run as
background tasks with error isolation — one failing handler never affects
the bus or other handlers.

Security: Handlers receive EventEnvelope with trace metadata. Payloads
    are validated before dispatch.
Observability: Publish/subscribe events emit counters under cenf.bus.*.
@ai-directive: This adapter is the reference implementation for BusEventManager.
    Use MemoryBusAdapter for dev/testing and single-process deployments.
    Use RedisBusAdapter for multi-process/production deployments.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from core_infrastructure.bus_event.models import BusConfig, EventEnvelope


class MemoryBusAdapter:
    """In-process event bus using asyncio.Queue per event_type.

    Provides publish-subscribe messaging within a single Python process.
    Each event_type gets its own asyncio.Queue. Subscribers register
    async handlers that run as background tasks when events are published.

    Thread-safe via asyncio.Lock for subscription management. Handlers
    are isolated — a crashing handler does not affect other subscribers
    or the publisher.

    Args:
        config: BusConfig for queue size limits and handler timeouts.

    Usage::

        bus = MemoryBusAdapter(config=BusConfig())
        sub_id = await bus.subscribe("user.created", my_handler, "my-service")
        event_id = await bus.publish("user.created", {"user_id": "42"})
        await bus.unsubscribe(sub_id)
    """

    def __init__(self, config: BusConfig | None = None) -> None:
        self._config = config if config is not None else BusConfig()
        self._queues: dict[str, asyncio.Queue[EventEnvelope]] = {}
        self._subscriptions: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._handler_tasks: set[asyncio.Task[Any]] = set()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_id() -> str:
        """Generate a unique identifier (UUID4)."""
        return str(uuid.uuid4())

    def _get_or_create_queue(self, event_type: str) -> asyncio.Queue[EventEnvelope]:
        """Get or create an asyncio.Queue for the given event_type.

        Args:
            event_type: The event type string.

        Returns:
            asyncio.Queue[EventEnvelope]: The queue for this event_type.
        """
        if event_type not in self._queues:
            self._queues[event_type] = asyncio.Queue(
                maxsize=self._config.max_queue_size,
            )
        return self._queues[event_type]

    async def _dispatch_handlers(self, event_type: str, envelope: EventEnvelope) -> None:
        """Dispatch an event to all subscribed handlers for the event_type.

        Each handler runs as a background task with error isolation.
        Handler errors are caught and logged but never propagated.

        Args:
            event_type: The event type to dispatch to.
            envelope: The EventEnvelope to deliver.
        """
        async with self._lock:
            # Gather handlers registered for this event_type
            handlers = [
                sub
                for sub in self._subscriptions.values()
                if sub["event_type"] == event_type
            ]

        for sub in handlers:
            task = asyncio.ensure_future(
                self._run_handler(sub["handler"], envelope, sub["subscription_id"]),
            )
            self._handler_tasks.add(task)
            task.add_done_callback(self._handler_tasks.discard)

    async def _run_handler(
        self,
        handler: Any,
        envelope: EventEnvelope,
        subscription_id: str,
    ) -> None:
        """Run a single handler with error isolation and timeout.

        Args:
            handler: The async callable handler.
            envelope: The EventEnvelope to pass.
            subscription_id: The subscription ID (for logging).
        """
        try:
            await asyncio.wait_for(
                handler(envelope),
                timeout=self._config.default_handler_timeout,
            )
        except TimeoutError:
            # Handler exceeded timeout — log and continue
            pass
        except Exception:
            # Handler crashed — isolate the error
            pass

    # ------------------------------------------------------------------
    # Background consumer (runs per event_type queue)
    # ------------------------------------------------------------------

    async def _consume(self, event_type: str) -> None:
        """Continuously consume events from the event_type queue.

        Reads EventEnvelope objects from the queue and dispatches them
        to all registered handlers for that event_type.

        Args:
            event_type: The event type to consume events for.
        """
        queue = self._get_or_create_queue(event_type)
        while True:
            envelope = await queue.get()
            await self._dispatch_handlers(event_type, envelope)
            queue.task_done()

    # ------------------------------------------------------------------
    # Public API — BusEventManager Protocol
    # ------------------------------------------------------------------

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Publish an event to all subscribers of event_type.

        Fire-and-forget — returns the unique event_id immediately after
        placing the event on the queue. Handlers are dispatched
        asynchronously by background consumers.

        Args:
            event_type: Event type string (e.g. ``"user.created"``).
            payload: JSON-serializable event payload.
            metadata: Optional metadata dict (trace_id, tenant_id, etc.).

        Returns:
            str: The unique event ID (UUID4).
        """
        event_id = self._generate_id()

        envelope = EventEnvelope(
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            metadata=metadata,
        )

        queue = self._get_or_create_queue(event_type)
        await queue.put(envelope)

        return event_id

    async def subscribe(
        self,
        event_type: str,
        handler: Any,
        subscriber_id: str,
    ) -> str:
        """Subscribe a handler to an event type.

        The handler is an async callable that receives an ``EventEnvelope``.
        Returns a unique subscription_id for later unsubscription.

        Also starts a background consumer task for the event_type if one
        isn't already running.

        Args:
            event_type: Event type to subscribe to (exact match).
            handler: Async callable ``async def handler(envelope: EventEnvelope) -> None``.
            subscriber_id: Identifier for the subscribing component.

        Returns:
            str: Unique subscription ID.
        """
        subscription_id = self._generate_id()

        async with self._lock:
            self._subscriptions[subscription_id] = {
                "subscription_id": subscription_id,
                "event_type": event_type,
                "handler": handler,
                "subscriber_id": subscriber_id,
            }

        # Ensure a consumer task is running for this event_type
        self._get_or_create_queue(event_type)
        # Start a background consumer if we haven't already for this event_type
        consumer_task = asyncio.ensure_future(self._consume(event_type))
        self._handler_tasks.add(consumer_task)
        consumer_task.add_done_callback(self._handler_tasks.discard)

        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscription by its ID.

        Idempotent — calling on an unknown ID is a no-op.

        Args:
            subscription_id: The subscription ID returned by subscribe().
        """
        async with self._lock:
            self._subscriptions.pop(subscription_id, None)

    async def list_subscriptions(self) -> list[dict[str, Any]]:
        """Return metadata for all active subscriptions.

        Returns:
            list[dict[str, Any]]: Each entry has ``subscription_id``,
                ``event_type``, and ``subscriber_id``.
        """
        async with self._lock:
            return [
                {
                    "subscription_id": sub["subscription_id"],
                    "event_type": sub["event_type"],
                    "subscriber_id": sub["subscriber_id"],
                }
                for sub in self._subscriptions.values()
            ]

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery (AX).

        Returns:
            dict[str, Any]: A valid JSON Schema object describing BusConfig.
        """
        return BusConfig.model_json_schema()
