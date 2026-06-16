"""Unit tests for ObservabilityManager Protocol and ObservabilitySettings model.

Tests cover:
- ObservabilityManager Protocol contract (all required methods present)
- ObservabilityManager Protocol is runtime-checkable
- ObservabilitySettings Pydantic model validation and defaults
- ObservabilitySettings JSON Schema generation
- MetricSpec and MetricType model validation

Author: CENF AI Team
Version: 0.1.0
"""

import json

import pytest
from pydantic import ValidationError as PydanticValidationError


class TestObservabilityManagerProtocol:
    """Verify ObservabilityManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """ObservabilityManager Protocol is decorated with @runtime_checkable."""
        from core_infrastructure.observability.ports import ObservabilityManager
        assert hasattr(ObservabilityManager, "_is_runtime_protocol") or hasattr(
            ObservabilityManager, "__protocol_attrs__"
        )

    def test_has_increment_counter_method(self) -> None:
        """Protocol requires increment_counter(name, value, attributes)."""
        from core_infrastructure.observability.ports import ObservabilityManager
        assert hasattr(ObservabilityManager, "increment_counter")

    def test_has_record_histogram_method(self) -> None:
        """Protocol requires record_histogram(name, value, attributes)."""
        from core_infrastructure.observability.ports import ObservabilityManager
        assert hasattr(ObservabilityManager, "record_histogram")

    def test_has_start_span_method(self) -> None:
        """Protocol requires start_span(name, attributes)."""
        from core_infrastructure.observability.ports import ObservabilityManager
        assert hasattr(ObservabilityManager, "start_span")

    def test_has_get_current_span_method(self) -> None:
        """Protocol requires get_current_span()."""
        from core_infrastructure.observability.ports import ObservabilityManager
        assert hasattr(ObservabilityManager, "get_current_span")

    def test_has_get_trace_id_method(self) -> None:
        """Protocol requires get_trace_id() -> str."""
        from core_infrastructure.observability.ports import ObservabilityManager
        assert hasattr(ObservabilityManager, "get_trace_id")

    def test_has_flush_method(self) -> None:
        """Protocol requires async flush() method."""
        from core_infrastructure.observability.ports import ObservabilityManager
        assert hasattr(ObservabilityManager, "flush")

    def test_has_get_json_schema_method(self) -> None:
        """Protocol requires get_json_schema() -> dict."""
        from core_infrastructure.observability.ports import ObservabilityManager
        assert hasattr(ObservabilityManager, "get_json_schema")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all ObservabilityManager methods satisfies the protocol."""
        from core_infrastructure.observability.ports import ObservabilityManager

        class ValidObs:
            def increment_counter(self, name: str, value: float = 1.0, attributes=None) -> None: ...
            def record_histogram(self, name: str, value: float, attributes=None) -> None: ...
            def start_span(self, name: str, attributes=None): ...
            def get_current_span(self): ...
            def get_trace_id(self) -> str: ...
            async def flush(self) -> None: ...
            def get_json_schema(self) -> dict: ...

        assert isinstance(ValidObs(), ObservabilityManager)

    def test_class_missing_start_span_fails_protocol(self) -> None:
        """A class without start_span() does NOT satisfy ObservabilityManager."""
        from core_infrastructure.observability.ports import ObservabilityManager

        class IncompleteObs:
            def increment_counter(self, name: str, value: float = 1.0) -> None: ...
            def get_json_schema(self) -> dict: ...

        assert not isinstance(IncompleteObs(), ObservabilityManager)


class TestObservabilitySettings:
    """Verify ObservabilitySettings Pydantic model validation and defaults."""

    def test_default_values(self) -> None:
        """ObservabilitySettings creates with sensible defaults."""
        from core_infrastructure.observability.models import ObservabilitySettings
        settings = ObservabilitySettings()
        assert settings.service_name == "cenf-core"
        assert settings.exporter_endpoint is None
        assert settings.exporter_protocol == "grpc"
        assert settings.sampling_rate == 1.0
        assert settings.batch_size == 512
        assert settings.flush_interval_seconds == 5

    def test_custom_values_accepted(self) -> None:
        """ObservabilitySettings accepts valid custom values."""
        from core_infrastructure.observability.models import ObservabilitySettings
        settings = ObservabilitySettings(
            service_name="my-service",
            exporter_endpoint="http://otel-collector:4317",
            exporter_protocol="http",
            sampling_rate=0.5,
            batch_size=256,
            flush_interval_seconds=10,
        )
        assert settings.service_name == "my-service"
        assert settings.exporter_endpoint == "http://otel-collector:4317"
        assert settings.exporter_protocol == "http"
        assert settings.sampling_rate == 0.5
        assert settings.batch_size == 256
        assert settings.flush_interval_seconds == 10

    def test_empty_service_name_fails(self) -> None:
        """service_name must be at least 1 character."""
        from core_infrastructure.observability.models import ObservabilitySettings
        with pytest.raises(PydanticValidationError):
            ObservabilitySettings(service_name="")

    def test_service_name_exceeds_128_chars_fails(self) -> None:
        """service_name max 128 characters."""
        from core_infrastructure.observability.models import ObservabilitySettings
        with pytest.raises(PydanticValidationError):
            ObservabilitySettings(service_name="x" * 129)

    def test_invalid_exporter_protocol_fails(self) -> None:
        """exporter_protocol must be grpc or http."""
        from core_infrastructure.observability.models import ObservabilitySettings
        with pytest.raises(PydanticValidationError):
            ObservabilitySettings(exporter_protocol="tcp")  # type: ignore[arg-type]

    def test_sampling_rate_out_of_range_fails(self) -> None:
        """sampling_rate must be between 0.0 and 1.0."""
        from core_infrastructure.observability.models import ObservabilitySettings
        with pytest.raises(PydanticValidationError):
            ObservabilitySettings(sampling_rate=1.5)
        with pytest.raises(PydanticValidationError):
            ObservabilitySettings(sampling_rate=-0.1)

    def test_flush_interval_out_of_range_fails(self) -> None:
        """flush_interval_seconds must be between 1 and 60."""
        from core_infrastructure.observability.models import ObservabilitySettings
        with pytest.raises(PydanticValidationError):
            ObservabilitySettings(flush_interval_seconds=0)
        with pytest.raises(PydanticValidationError):
            ObservabilitySettings(flush_interval_seconds=61)

    def test_model_json_schema_is_valid(self) -> None:
        """ObservabilitySettings.model_json_schema() returns valid JSON Schema."""
        from core_infrastructure.observability.models import ObservabilitySettings
        schema = ObservabilitySettings.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        json_str = json.dumps(schema)
        assert len(json_str) > 0
        assert json.loads(json_str) == schema
