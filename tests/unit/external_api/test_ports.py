"""Unit tests for ExternalAPIManager Protocol and Pydantic models.

Tests cover:
- ExternalAPIManager Protocol contract (request, get, post, get_circuit_state)
- Protocol is runtime-checkable
- ApiResponse Pydantic model validation
- CircuitState enum values
- RetryPolicy Pydantic model validation and defaults
- RequestConfig Pydantic model validation

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.external_api.models import (
    ApiResponse,
    CircuitState,
    RequestConfig,
    RetryPolicy,
)
from core_infrastructure.external_api.ports import ExternalAPIManager


class TestExternalAPIManagerProtocol:
    """Verify ExternalAPIManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """ExternalAPIManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(ExternalAPIManager, "_is_runtime_protocol") or hasattr(
            ExternalAPIManager, "__protocol_attrs__"
        )

    def test_has_request_method(self) -> None:
        """Protocol requires async request(method, url, headers, body, timeout, retry_policy)."""
        assert hasattr(ExternalAPIManager, "request")

    def test_has_get_method(self) -> None:
        """Protocol requires async get(url, headers, timeout)."""
        assert hasattr(ExternalAPIManager, "get")

    def test_has_post_method(self) -> None:
        """Protocol requires async post(url, body, headers, timeout)."""
        assert hasattr(ExternalAPIManager, "post")

    def test_has_get_circuit_state_method(self) -> None:
        """Protocol requires get_circuit_state(host) -> CircuitState."""
        assert hasattr(ExternalAPIManager, "get_circuit_state")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all ExternalAPIManager methods satisfies the protocol."""

        class ValidAPI:
            async def request(self, method, url, headers=None, body=None, timeout=None, retry_policy=None): ...
            async def get(self, url, headers=None, timeout=None): ...
            async def post(self, url, body=None, headers=None, timeout=None): ...
            def get_circuit_state(self, host): ...

        assert isinstance(ValidAPI(), ExternalAPIManager)

    def test_class_missing_request_fails_protocol(self) -> None:
        """A class without request() does NOT satisfy ExternalAPIManager."""

        class Incomplete:
            async def get(self, url, headers=None, timeout=None): ...

        assert not isinstance(Incomplete(), ExternalAPIManager)


class TestCircuitStateEnum:
    """Verify CircuitState enum values."""

    def test_closed_state(self) -> None:
        """Circuit breaker starts CLOSED (normal operation)."""
        assert CircuitState.CLOSED.value == "CLOSED"

    def test_open_state(self) -> None:
        """Circuit breaker OPEN — requests are rejected."""
        assert CircuitState.OPEN.value == "OPEN"

    def test_half_open_state(self) -> None:
        """Circuit breaker HALF_OPEN — probing for recovery."""
        assert CircuitState.HALF_OPEN.value == "HALF_OPEN"


class TestApiResponseModel:
    """Verify ApiResponse Pydantic model validation."""

    def test_api_response_creation(self) -> None:
        """ApiResponse creates with required fields."""
        resp = ApiResponse(status_code=200, headers={"Content-Type": "application/json"}, body={"ok": True}, elapsed_ms=45.2)
        assert resp.status_code == 200
        assert resp.headers == {"Content-Type": "application/json"}
        assert resp.body == {"ok": True}
        assert resp.elapsed_ms == 45.2

    def test_api_response_default_headers(self) -> None:
        """ApiResponse defaults headers to empty dict."""
        resp = ApiResponse(status_code=200, body={}, elapsed_ms=10.0)
        assert resp.headers == {}

    def test_api_response_elapsed_non_negative(self) -> None:
        """elapsed_ms must be >= 0."""
        with pytest.raises(PydanticValidationError):
            ApiResponse(status_code=200, body={}, elapsed_ms=-1.0)


class TestRetryPolicyModel:
    """Verify RetryPolicy Pydantic model validation and defaults."""

    def test_default_policy(self) -> None:
        """RetryPolicy creates with sensible defaults."""
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.backoff_base == 2.0
        assert policy.backoff_factor == 1.0
        assert policy.jitter is True
        assert policy.retryable_statuses == [429, 502, 503, 504]

    def test_custom_policy(self) -> None:
        """RetryPolicy accepts custom values."""
        policy = RetryPolicy(max_retries=5, backoff_base=3.0, backoff_factor=0.5, jitter=False, retryable_statuses=[429, 503])
        assert policy.max_retries == 5
        assert policy.backoff_base == 3.0
        assert policy.backoff_factor == 0.5
        assert policy.jitter is False
        assert policy.retryable_statuses == [429, 503]

    def test_negative_max_retries_fails(self) -> None:
        """max_retries must be >= 0."""
        with pytest.raises(PydanticValidationError):
            RetryPolicy(max_retries=-1)


class TestRequestConfigModel:
    """Verify RequestConfig Pydantic model validation."""

    def test_request_config_creation(self) -> None:
        """RequestConfig bundles HTTP request parameters."""
        config = RequestConfig(
            method="GET",
            url="https://api.example.com/data",
            headers={"Authorization": "Bearer token"},
            body=None,
            timeout=10.0,
            retry_policy=RetryPolicy(max_retries=2),
        )
        assert config.method == "GET"
        assert config.url == "https://api.example.com/data"
        assert config.timeout == 10.0
        assert config.retry_policy.max_retries == 2

    def test_request_config_defaults(self) -> None:
        """RequestConfig provides sensible defaults."""
        config = RequestConfig(method="POST", url="https://api.example.com/data")
        assert config.headers == {}
        assert config.body is None
        assert config.timeout == 30.0
        assert config.retry_policy.max_retries == 3
