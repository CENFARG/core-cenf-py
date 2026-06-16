"""ObservabilitySettings — Pydantic model for ObservabilityManager configuration.

Validates the OpenTelemetry SDK settings: service name, exporter configuration,
sampling strategy, and batching parameters.

Security: exporter_endpoint MUST NOT contain credentials — use environment
    variables or SecretManager for auth tokens.
Observability: The model schema is auto-discoverable via
    ObservabilityManager.get_json_schema().
@ai-directive: This model is the single validation gate for all observability
    configuration injected via ConfigManager.get_section("observability").

Author: CENF AI Team
Version: 0.1.0
"""

from typing import Literal

from pydantic import BaseModel, Field


class ObservabilitySettings(BaseModel):
    """Configuration model for ObservabilityManager adapter selection.

    When ``exporter_endpoint`` is ``None``, the adapter operates in
    local/dev mode with a console exporter (no remote collector).
    For production, set ``exporter_endpoint`` to the OTLP collector URL.

    Attributes:
        service_name: Unique service name in telemetry backend.
        exporter_endpoint: OTLP collector URL. None = local console mode.
        exporter_protocol: Transport protocol for the exporter.
        sampling_rate: Fraction of traces to sample (0.0 = none, 1.0 = all).
        batch_size: Maximum spans per export batch.
        flush_interval_seconds: Interval between periodic metric exports.
    """

    service_name: str = Field(
        min_length=1,
        max_length=128,
        default="cenf-core",
        description="Unique service name for telemetry identification.",
    )
    exporter_endpoint: str | None = Field(
        default=None,
        description="OTLP collector endpoint URL. None = console exporter (dev mode).",
    )
    exporter_protocol: Literal["grpc", "http"] = Field(
        default="grpc",
        description="Transport protocol for OTLP exporter.",
    )
    sampling_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Trace sampling rate (0.0 = no traces, 1.0 = all traces).",
    )
    batch_size: int = Field(
        default=512,
        ge=1,
        le=8192,
        description="Maximum number of spans per export batch.",
    )
    flush_interval_seconds: int = Field(
        default=5,
        ge=1,
        le=60,
        description="Interval in seconds between periodic metric exports.",
    )
