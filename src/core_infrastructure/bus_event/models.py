"""CENF BusEventManager models — EventEnvelope, BusConfig, CloudEvent.

Defines the Pydantic models for the event bus domain: EventEnvelope for
routing events through the bus, BusConfig for adapter configuration,
and CloudEvent for CloudEvents 1.0 spec compliance.

Security: EventEnvelope.payload is validated as JSON-serializable. No
    credentials or PII should be placed in payload without encryption.
Observability: Every event carries an event_id for trace correlation.
@ai-directive: EventEnvelope is the canonical message format — all adapters
    and the standalone server use this model for serialization.

Author: CENF AI Team
Version: 0.2.0
"""

from __future__ import annotations

import datetime
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

    def to_cloudevent(self, source: str) -> dict[str, Any]:
        """Convert this EventEnvelope to a CloudEvents 1.0 envelope.

        Produces a CloudEvents-compliant dict suitable for NATS
        or other CE-capable transports. Metadata (trace_id, tenant_id,
        etc.) is included as the ``cenfmetadata`` extension attribute.

        Args:
            source: The event source identifier (e.g. ``"cenf-billing-svc"``).

        Returns:
            dict[str, Any]: CloudEvents 1.0 dict with all required attributes
                plus optional ``cenfmetadata`` extension.
        """
        ce: dict[str, Any] = {
            "specversion": "1.0",
            "type": self.event_type,
            "source": source,
            "id": self.event_id,
            "time": datetime.datetime.now(datetime.UTC).isoformat(),
            "datacontenttype": "application/json",
            "data": self.payload,
        }
        if self.metadata:
            ce["cenfmetadata"] = self.metadata
        return ce


class CloudEvent(BaseModel):
    """CloudEvents 1.0 specification model.

    Used for validating and constructing CloudEvents-compliant messages
    when publishing through NATS JetStream or other CE-capable transports.

    See: https://github.com/cloudevents/spec/blob/v1.0/spec.md

    Attributes:
        specversion: CloudEvents spec version (``"1.0"``).
        type: Event type string.
        source: Event source identifier.
        id: Unique event identifier.
        time: RFC 3339 timestamp (optional).
        datacontenttype: Content type of ``data`` (default: ``"application/json"``).
        data: Event payload.
    """

    specversion: str = Field(
        ...,
        min_length=1,
        description='CloudEvents spec version (e.g. "1.0").',
    )
    type: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Event type string.",
    )
    source: str = Field(
        ...,
        min_length=1,
        description="Event source identifier.",
    )
    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique event identifier.",
    )
    time: str | None = Field(
        default=None,
        description="RFC 3339 timestamp (UTC).",
    )
    datacontenttype: str = Field(
        default="application/json",
        description='Content type of data (e.g. "application/json").',
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Event payload.",
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
