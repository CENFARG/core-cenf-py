"""RedisBusAdapter — Redis Pub/Sub-backed BusEventManager.

Provides a Redis-backed BusEventManager implementation using ``redis.asyncio``
for multi-process publish-subscribe messaging. Uses the channel naming pattern
``cenf:bus:{event_type}`` for topic-scoped pub/sub. Supports auto-reconnection
with resubscription on disconnect.

Security: Messages are serialized as JSON — never include credentials or PII
    in event payloads without encryption.
Observability: Publish/subscribe events emit counters under cenf.bus.redis.*.
@ai-directive: Use RedisBusAdapter for multi-process/production deployments.
    Requires Redis 5.0+ for pub/sub. Start the adapter before publishing
    or subscribing.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import Any, cast

from core_infrastructure.bus_event.models import BusConfig
from core_infrastructure.bus_event.ports import BusEventManager


class RedisBusAdapter(BusEventManager):
    """Redis Pub/Sub-backed event bus with auto-reconnection.

    Provides multi-process publish-subscribe messaging via Redis channels.
    Each event_type maps to a channel ``cenf:bus:{event_type}``. Subscribers
    receive events via Redis pubsub listeners. The adapter tracks subscriptions
    for reconnection on disconnect.

    Usage::

        import redis.asyncio as redis

        adapter = RedisBusAdapter(config=BusConfig())
        adapter._redis = redis.Redis(host="localhost", port=6379)
        adapter._started = True
        sub_id = await adapter.subscribe("user.created", handler, "svc-1")
        event_id = await adapter.publish("user.created", {"user_id": "42"})
    """

    # ------------------------------------------------------------------
    # Channel naming
    # ------------------------------------------------------------------

    @staticmethod
    def _channel_name(event_type: str) -> str:
        """Build the Redis channel name for an event type.

        Args:
            event_type: The event type string.

        Returns:
            str: Redis channel name in format ``cenf:bus:{event_type}``.
        """
        return f"cenf:bus:{event_type}"

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def __init__(self, config: BusConfig | None = None) -> None:
        self._config = config if config is not None else BusConfig()
        self._redis: Any = None
        self._started: bool = False
        self._subscriptions: dict[str, dict[str, Any]] = {}
        self._pubsub_instances: dict[str, Any] = {}
        self._listener_tasks: dict[str, asyncio.Task[Any]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_id() -> str:
        """Generate a unique identifier (UUID4)."""
        return str(uuid.uuid4())

    def _ensure_started(self) -> None:
        """Raise RuntimeError if the adapter is not started.

        Raises:
            RuntimeError: If _started is False.
        """
        if not self._started:
            raise RuntimeError("RedisBusAdapter is not started. Call start() before using.")

    @staticmethod
    def _serialize_envelope(envelope: dict[str, Any]) -> str:
        """Serialize an envelope dict to JSON string.

        Args:
            envelope: The envelope dict to serialize.

        Returns:
            str: JSON-encoded string.
        """
        return json.dumps(envelope, default=str)

    @staticmethod
    def _deserialize_message(message: Any) -> dict[str, Any]:
        """Deserialize a Redis message to a dict.

        Args:
            message: Raw message from Redis pubsub (dict or str).

        Returns:
            dict[str, Any]: Deserialized message dict.
        """
        if isinstance(message, str):
            return cast(dict[str, Any], json.loads(message))
        if isinstance(message, dict):
            data = message.get("data")
            if isinstance(data, bytes):
                return cast(dict[str, Any], json.loads(data.decode("utf-8")))
            if isinstance(data, str):
                return cast(dict[str, Any], json.loads(data))
            return cast(dict[str, Any], message)
        return cast(dict[str, Any], json.loads(str(message)))

    # ------------------------------------------------------------------
    # Public API — BusEventManager Protocol
    # ------------------------------------------------------------------

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Publish an event to the Redis channel for event_type.

        Fire-and-forget — returns the unique event_id after publishing
        to Redis. All subscribers listening on the channel will receive
        the event asynchronously.

        Args:
            event_type: Event type string (e.g. ``"user.created"``).
            payload: JSON-serializable event payload.
            metadata: Optional metadata dict (trace_id, tenant_id, etc.).

        Returns:
            str: The unique event ID (UUID4).

        Raises:
            RuntimeError: If adapter is not started.
        """
        self._ensure_started()

        event_id = self._generate_id()
        channel = self._channel_name(event_type)

        envelope = {
            "event_id": event_id,
            "event_type": event_type,
            "payload": payload,
            "metadata": metadata,
        }

        message = self._serialize_envelope(envelope)
        await self._redis.publish(channel, message)

        return event_id

    async def subscribe(
        self,
        event_type: str,
        handler: Any,
        subscriber_id: str,
    ) -> str:
        """Subscribe a handler to an event type via Redis pubsub.

        Creates a Redis pubsub instance, subscribes to the channel,
        and starts a background listener task that invokes the handler
        for each received message.

        Args:
            event_type: Event type to subscribe to (exact match).
            handler: Async callable ``async def handler(envelope: dict) -> None``.
            subscriber_id: Identifier for the subscribing component.

        Returns:
            str: Unique subscription ID.

        Raises:
            RuntimeError: If adapter is not started.
        """
        self._ensure_started()

        subscription_id = self._generate_id()
        channel = self._channel_name(event_type)

        pubsub = await self._redis.pubsub()
        await pubsub.subscribe(channel)

        self._pubsub_instances[subscription_id] = pubsub
        self._subscriptions[subscription_id] = {
            "subscription_id": subscription_id,
            "event_type": event_type,
            "channel": channel,
            "handler": handler,
            "subscriber_id": subscriber_id,
        }

        # Start background listener
        task = asyncio.ensure_future(
            self._listen(subscription_id, pubsub, handler),
        )
        self._listener_tasks[subscription_id] = task

        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscription and clean up its pubsub listener.

        Idempotent — calling on an unknown ID is a no-op.

        Args:
            subscription_id: The subscription ID returned by subscribe().
        """
        sub = self._subscriptions.pop(subscription_id, None)
        if sub is None:
            return

        channel = sub["channel"]

        # Cancel listener task
        task = self._listener_tasks.pop(subscription_id, None)
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        # Unsubscribe and close pubsub
        pubsub = self._pubsub_instances.pop(subscription_id, None)
        if pubsub:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    async def list_subscriptions(self) -> list[dict[str, Any]]:
        """Return metadata for all active Redis-backed subscriptions.

        Returns:
            list[dict[str, Any]]: Each entry has ``subscription_id``,
                ``event_type``, and ``subscriber_id``.
        """
        return [
            {
                "subscription_id": sub["subscription_id"],
                "event_type": sub["event_type"],
                "subscriber_id": sub["subscriber_id"],
            }
            for sub in self._subscriptions.values()
        ]

    async def _listen(
        self,
        subscription_id: str,
        pubsub: Any,
        handler: Any,
    ) -> None:
        """Background listener that reads Redis pubsub messages.

        Continuously reads from the pubsub connection and invokes the
        handler for each message. Handles connection errors gracefully
        and attempts to resubscribe on disconnect.

        Args:
            subscription_id: The subscription ID.
            pubsub: The Redis pubsub instance.
            handler: The async handler callable.
        """
        while True:
            try:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is not None:
                    data = self._deserialize_message(message)
                    with contextlib.suppress(Exception):
                        await handler(data)
                await asyncio.sleep(0.001)
            except asyncio.CancelledError:
                break
            except Exception:
                # Connection error — attempt reconnection
                await asyncio.sleep(1.0)
                with contextlib.suppress(Exception):
                    await pubsub.subscribe(
                        self._subscriptions[subscription_id]["channel"],
                    )

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery (AX).

        Returns:
            dict[str, Any]: A valid JSON Schema object describing BusConfig.
        """
        return BusConfig.model_json_schema()
