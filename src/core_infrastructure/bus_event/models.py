"""CENF BusEventManager models — EventEnvelope, BusConfig.

Defines the Pydantic models for the event bus domain: EventEnvelope for
routing events through the bus, and BusConfig for adapter configuration.

Security: EventEnvelope.payload is validated as JSON-serializable. No
    credentials or PII should be placed in payload without encryption.
Observability: Every event carries an event_id for trace correlation.
@ai-directive: EventEnvelope is the canonical message format — all adapters
    and the standalone server use this model for serialization.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    """Canonical event message routed through the bus.

    Every event published or subscribed carries an EventEnvelope with
    event identification, payload, and optional metadata for trace
    correlation and tenant isolation.

    Attributes:
        event_id: Unique event identifier (UUID4 string).
        event_type: Event type string used for routing (e.g. ``"user.created"``).
        payload: JSON-serializable event payload.
        metadata: Optional metadata dict for trace_id, tenant_id, etc.
    """

    event_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique event identifier (UUID4).",
    )
    event_type: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Event type string for routing (e.g. 'user.created').",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON-serializable event payload.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata (trace_id, tenant_id, etc.).",
    )


class BusConfig(BaseModel):
    """Configuration for BusEventManager adapters.

    Controls queue size limits and handler dispatch timeouts
    for the event bus.

    Attributes:
        max_queue_size: Maximum number of pending events per event_type
            before publish blocks (1-10000).
        default_handler_timeout: Maximum seconds a handler can run before
            being cancelled (> 0).
    """

    max_queue_size: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Maximum pending events per event_type before publish blocks.",
    )
    default_handler_timeout: float = Field(
        default=30.0,
        gt=0.0,
        description="Maximum seconds a handler can run before being cancelled.",
    )
