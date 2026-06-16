"""OTelAdapter — OpenTelemetry SDK-based ObservabilityManager adapter.

Implements the ObservabilityManager Protocol using the OpenTelemetry SDK.
Configures TracerProvider, MeterProvider, and W3CTraceContextPropagator.
Supports two modes:
  - Dev mode (exporter_endpoint=None): ConsoleSpanExporter for local dev.
  - Prod mode: OTLP exporter to remote collector.

Security: Trace attributes MUST NOT contain PII, credentials, or session tokens.
Observability: All spans and metrics are namespaced under ``cenf.*``.
    Trace context is synced to ``common.context`` contextvars.

@ai-directive: NEVER throw on OTel failure — degrade gracefully. OTel
    initialization errors are logged and execution continues.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from core_infrastructure.common import context as ctx
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.observability.models import ObservabilitySettings

_logger = logging.getLogger(__name__)


class _NullSpan:
    """A no-op span returned when OTel is not initialized.

    Usable as a context manager — does nothing on enter/exit.
    """

    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class OTelAdapter:
    """OpenTelemetry-based ObservabilityManager.

    Initializes the OTel SDK on construction. Supports dev mode
    (console exporter) and prod mode (OTLP exporter).

    Args:
        config: ConfigManager instance providing observability settings.

    Usage::

        config = PydanticConfigAdapter(config_path="config.yaml")
        obs = OTelAdapter(config=config)
        obs.increment_counter("cenf.requests", value=1.0)
        with obs.start_span("my-operation") as span:
            pass
    """

    def __init__(self, config: ConfigManager) -> None:
        self._config = config
        self._settings = self._load_settings()
        self._tracer: Any = None
        self._meter: Any = None
        self._tracer_provider: Any = None
        self._meter_provider: Any = None
        self._init_otel()

    # ------------------------------------------------------------------
    # Public API — ObservabilityManager Protocol
    # ------------------------------------------------------------------

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Increment a named counter by the given value.

        Falls back to no-op if OTel meter is not initialized.

        Args:
            name: Metric name (e.g., ``"cenf.requests"``).
            value: Increment amount (default 1.0).
            attributes: Optional label dict.
        """
        try:
            if self._meter is not None:
                counter = self._meter.create_counter(name)
                counter.add(value, attributes or {})
        except Exception:
            pass

    def record_histogram(
        self,
        name: str,
        value: float,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Record a value on a named histogram.

        Falls back to no-op if OTel meter is not initialized.

        Args:
            name: Metric name.
            value: Observed value.
            attributes: Optional label dict.
        """
        try:
            if self._meter is not None:
                histogram = self._meter.create_histogram(name)
                histogram.record(value, attributes or {})
        except Exception:
            pass

    def start_span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> Any:
        """Start a new tracing span.

        If OTel tracer is not initialized, returns a null span that
        does nothing.

        Args:
            name: Span name.
            attributes: Optional span attributes.

        Returns:
            An OTel span object or _NullSpan if tracer is unavailable.

        Observability: Sets trace_id and span_id in contextvars for
            downstream LoggerManager injection.
        """
        try:
            if self._tracer is not None:
                span = self._tracer.start_span(name, attributes=attributes or {})
                # Sync trace context to contextvars
                span_ctx = span.get_span_context()
                if span_ctx.is_valid:
                    trace_id_hex = format(span_ctx.trace_id, "032x")
                    span_id_hex = format(span_ctx.span_id, "016x")
                    ctx.set_trace_id(trace_id_hex)
                    ctx.set_span_id(span_id_hex)
                return span
        except Exception:
            pass
        # Fallback: generate a local trace ID in contextvars
        local_tid = uuid.uuid4().hex
        ctx.set_trace_id(local_tid)
        return _NullSpan()

    def get_current_span(self) -> Any:
        """Return the currently active OTel span or None.

        Returns:
            The current span from OTel context, or None.
        """
        try:
            from opentelemetry import trace as otel_trace
            span = otel_trace.get_current_span()
            span_ctx = span.get_span_context()
            if span_ctx.is_valid:
                return span
        except Exception:
            pass
        return None

    def get_trace_id(self) -> str:
        """Return the current trace_id from OTel trace context.

        Returns:
            str: Trace ID hex string or ``""``.
        """
        try:
            from opentelemetry import trace as otel_trace
            span = otel_trace.get_current_span()
            span_ctx = span.get_span_context()
            if span_ctx.is_valid:
                return format(span_ctx.trace_id, "032x")
        except Exception:
            pass
        # Fallback to contextvars
        return ctx.get_trace_id()

    async def flush(self) -> None:
        """Force-flush all pending spans and metrics.

        Calls force_flush on both the tracer and meter providers.
        """
        try:
            if self._tracer_provider is not None:
                self._tracer_provider.force_flush()
        except Exception:
            pass
        try:
            if self._meter_provider is not None:
                self._meter_provider.force_flush()
        except Exception:
            pass

    def get_json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing ObservabilitySettings.

        Returns:
            dict[str, Any]: A valid JSON Schema object.
        """
        return ObservabilitySettings.model_json_schema()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_settings(self) -> ObservabilitySettings:
        """Load and validate ObservabilitySettings from ConfigManager.

        Returns:
            ObservabilitySettings: Validated observability configuration.
        """
        section = self._config.get_section("observability")
        return ObservabilitySettings.model_validate(section)

    def _init_otel(self) -> None:
        """Initialize the OpenTelemetry SDK providers.

        Sets up TracerProvider and MeterProvider. In dev mode
        (no exporter_endpoint), uses ConsoleSpanExporter for spans
        and no metric export. In prod mode, uses OTLP exporters.
        """
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import (
                PeriodicExportingMetricReader,
            )
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import (
                BatchSpanProcessor,
                ConsoleSpanExporter,
            )
        except ImportError:
            _logger.warning("OpenTelemetry SDK not installed — telemetry disabled.")
            return

        try:
            # TracerProvider setup
            tracer_provider: Any = TracerProvider()
            if self._settings.exporter_endpoint:
                # Prod mode: OTLP exporter
                try:
                    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                        OTLPSpanExporter,
                    )
                    exporter: Any = OTLPSpanExporter(
                        endpoint=self._settings.exporter_endpoint,
                    )
                except ImportError:
                    _logger.warning("OTLP exporter not available — using console fallback.")
                    exporter = ConsoleSpanExporter()
            else:
                # Dev mode: console exporter
                exporter = ConsoleSpanExporter()

            tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(tracer_provider)
            self._tracer_provider = tracer_provider
            self._tracer = trace.get_tracer(self._settings.service_name)

            # MeterProvider setup
            metric_readers = []
            if self._settings.exporter_endpoint:
                try:
                    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                        OTLPMetricExporter,
                    )
                    metric_reader = PeriodicExportingMetricReader(
                        OTLPMetricExporter(endpoint=self._settings.exporter_endpoint),
                        export_interval_millis=self._settings.flush_interval_seconds * 1000,
                    )
                    metric_readers.append(metric_reader)
                except ImportError:
                    _logger.warning("OTLP metric exporter not available.")

            from opentelemetry import metrics as otel_metrics
            meter_provider: Any = MeterProvider(metric_readers=metric_readers)
            otel_metrics.set_meter_provider(meter_provider)
            self._meter_provider = meter_provider
            self._meter = otel_metrics.get_meter(self._settings.service_name)

        except Exception:
            _logger.exception("Failed to initialize OpenTelemetry SDK.")
            # Graceful degradation: tracer and meter remain None
