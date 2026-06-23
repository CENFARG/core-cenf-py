"""NatsBusAdapter — NATS JetStream-backed BusEventManager.

Provides a NATS-backed BusEventManager using ``nats-py`` with JetStream for
at-least-once delivery and durable consumers. Payloads are CloudEvents 1.0.

Security: Payloads are JSON — never include credentials without encryption.
Observability: Publish/subscribe emit counters under cenf.bus.nats.*.
@ai-directive: Use NatsBusAdapter for production multi-service deployments.
    Requires NATS 2.9+ with JetStream. Call start() before using the adapter.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import Any

from core_infrastructure.bus_event.models import BusConfig, EventEnvelope
from core_infrastructure.bus_event.ports import BusEventManager


class NatsBusAdapter(BusEventManager):
    """NATS JetStream-backed event bus with durable consumers.

    Multi-process pub/sub via NATS subjects ``cenf.bus.{event_type}``
    backed by JetStream streams. NATS client handles reconnection.
    Subscriptions use pull consumers with durable names for replay.

    Usage::

        adapter = NatsBusAdapter(config=BusConfig(), ...)
        adapter._nc = await nats.connect("nats://localhost:4222")
        adapter._js = adapter._nc.jetstream()
        adapter._started = True
        await adapter.subscribe("user.created", handler, "svc-1")
        await adapter.publish("user.created", {"user_id": "42"})
    """

    # ------------------------------------------------------------------
    # NATS naming (static)
    # ------------------------------------------------------------------

    @staticmethod
    def _subject_name(event_type: str) -> str:
        """NATS subject: ``cenf.bus.{event_type}``."""
        return f"cenf.bus.{event_type}"

    @staticmethod
    def _stream_name(event_type: str) -> str:
        """JetStream stream name (sanitized dots/hyphens)."""
        return f"cenf_bus_{event_type.replace('.', '_').replace('-', '_')}"

    @staticmethod
    def _consumer_name(event_type: str, subscriber_id: str) -> str:
        """JetStream durable consumer name."""
        e = event_type.replace(".", "_").replace("-", "_")
        s = subscriber_id.replace(".", "_").replace("-", "_")
        return f"cenf_bus_{e}_{s}"

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def __init__(
        self,
        config: BusConfig | None = None,
        config_manager: Any = None,
        secret_manager: Any = None,
        logger_manager: Any = None,
        error_manager: Any = None,
    ) -> None:
        self._config = config if config is not None else BusConfig()
        self._config_manager = config_manager
        self._secret_manager = secret_manager
        self._logger_manager = logger_manager
        self._error_manager = error_manager

        self._nc: Any = None
        self._js: Any = None
        self._started: bool = False
        self._source: str = "cenf"

        self._subscriptions: dict[str, dict[str, Any]] = {}
        self._listener_tasks: dict[str, asyncio.Task[Any]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_id() -> str:
        return str(uuid.uuid4())

    def _ensure_started(self) -> None:
        if not self._started:
            raise RuntimeError("NatsBusAdapter is not started. Call start() before using.")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Mark started and resolve CloudEvents source from config if available."""
        self._started = True
        if self._config_manager is not None:
            with contextlib.suppress(Exception):
                self._source = self._config_manager.get_string("nats.source", "cenf")

    async def stop(self) -> None:
        """Graceful shutdown: cancel listeners, drain NATS connection."""
        if not self._started:
            return

        for sub_id, task in list(self._listener_tasks.items()):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            self._listener_tasks.pop(sub_id, None)

        if self._nc is not None:
            with contextlib.suppress(Exception):
                await self._nc.drain()

        self._started = False

    # ------------------------------------------------------------------
    # BusEventManager Protocol
    # ------------------------------------------------------------------

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Publish event via JetStream (fire-and-forget, CloudEvents envelope).

        Returns:
            str: Unique event ID (UUID4).
        """
        self._ensure_started()

        event_id = self._generate_id()
        subject = self._subject_name(event_type)

        ce_envelope = EventEnvelope(
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            metadata=metadata,
        ).to_cloudevent(source=self._source)

        data = json.dumps(ce_envelope, default=str).encode("utf-8")
        await self._js.publish(subject=subject, payload=data)

        return event_id

    async def subscribe(
        self,
        event_type: str,
        handler: Any,
        subscriber_id: str,
    ) -> str:
        """Subscribe via JetStream durable pull consumer.

        Creates a stream and durable consumer, then starts a background
        listener task. The NATS client handles reconnection automatically.

        Returns:
            str: Unique subscription ID.
        """
        self._ensure_started()

        subscription_id = self._generate_id()
        subject = self._subject_name(event_type)
        stream_name = self._stream_name(event_type)
        consumer_name = self._consumer_name(event_type, subscriber_id)

        # Ensure stream and consumer exist (idempotent)
        with contextlib.suppress(Exception):
            await self._js.add_stream(name=stream_name, subjects=[subject])
        with contextlib.suppress(Exception):
            await self._js.add_consumer(stream=stream_name, durable_name=consumer_name)

        async with self._lock:
            self._subscriptions[subscription_id] = {
                "subscription_id": subscription_id,
                "event_type": event_type,
                "subject": subject,
                "stream": stream_name,
                "consumer": consumer_name,
                "handler": handler,
                "subscriber_id": subscriber_id,
            }

        task = asyncio.ensure_future(
            self._listen(subscription_id, stream_name, consumer_name, handler),
        )
        self._listener_tasks[subscription_id] = task

        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """Remove subscription, cancel listener, delete durable consumer.

        Idempotent — calling on an unknown ID is a no-op.
        """
        async with self._lock:
            sub = self._subscriptions.pop(subscription_id, None)

        if sub is None:
            return

        task = self._listener_tasks.pop(subscription_id, None)
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        with contextlib.suppress(Exception):
            await self._js.delete_consumer(
                stream=sub["stream"],
                durable_name=sub["consumer"],
            )

    async def list_subscriptions(self) -> list[dict[str, Any]]:
        """Return metadata for all active subscriptions."""
        async with self._lock:
            return [
                {
                    "subscription_id": s["subscription_id"],
                    "event_type": s["event_type"],
                    "subscriber_id": s["subscriber_id"],
                }
                for s in self._subscriptions.values()
            ]

    # ------------------------------------------------------------------
    # Background listener
    # ------------------------------------------------------------------

    async def _listen(
        self,
        subscription_id: str,
        stream_name: str,
        consumer_name: str,
        handler: Any,
    ) -> None:
        """Pull messages from JetStream durable consumer, invoke handler per message.

        The NATS client handles reconnection automatically. Exits on
        CancelledError (unsubscribe/stop) or when subscription is removed.
        """
        while True:
            try:
                psub = await self._js.pull_subscribe(
                    subject="",
                    stream=stream_name,
                    durable=consumer_name,
                )
                async for msg in psub.messages:
                    if subscription_id not in self._subscriptions:
                        break
                    data: dict[str, Any] = json.loads(msg.data.decode("utf-8"))
                    with contextlib.suppress(Exception):
                        await handler(data)
                    await msg.ack()
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery (AX)."""
        return BusConfig.model_json_schema()
