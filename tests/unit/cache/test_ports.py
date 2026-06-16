"""Unit tests for CacheManager Protocol and CacheConfig Pydantic model.

Tests cover:
- CacheManager Protocol contract (get, set, delete, exists, clear, get_or_set)
- Protocol is runtime-checkable
- CacheConfig Pydantic model validation and defaults
- StampedeConfig model validation
- CacheEntry model validation

Author: CENF AI Team
Version: 0.1.0
"""

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.cache.models import CacheConfig, CacheEntry, StampedeConfig
from core_infrastructure.cache.ports import CacheManager


class TestCacheManagerProtocol:
    """Verify CacheManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """CacheManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(CacheManager, "_is_runtime_protocol") or hasattr(
            CacheManager, "__protocol_attrs__"
        )

    def test_has_get_method(self) -> None:
        """Protocol requires get(key) -> Any."""
        assert hasattr(CacheManager, "get")

    def test_has_set_method(self) -> None:
        """Protocol requires set(key, value, ttl)."""
        assert hasattr(CacheManager, "set")

    def test_has_delete_method(self) -> None:
        """Protocol requires delete(key)."""
        assert hasattr(CacheManager, "delete")

    def test_has_exists_method(self) -> None:
        """Protocol requires exists(key) -> bool."""
        assert hasattr(CacheManager, "exists")

    def test_has_clear_method(self) -> None:
        """Protocol requires clear()."""
        assert hasattr(CacheManager, "clear")

    def test_has_get_or_set_method(self) -> None:
        """Protocol requires get_or_set(key, factory, ttl) -> Any."""
        assert hasattr(CacheManager, "get_or_set")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all CacheManager methods satisfies the protocol."""

        class ValidCache:
            def get(self, key: str): ...
            def set(self, key: str, value, ttl: int | None = None) -> None: ...
            def delete(self, key: str) -> None: ...
            def exists(self, key: str) -> bool: ...
            def clear(self) -> None: ...
            def get_or_set(self, key: str, factory, ttl: int | None = None): ...

        assert isinstance(ValidCache(), CacheManager)

    def test_class_missing_get_fails_protocol(self) -> None:
        """A class without get() does NOT satisfy CacheManager."""

        class Incomplete:
            def set(self, key: str, value, ttl: int | None = None) -> None: ...

        assert not isinstance(Incomplete(), CacheManager)


class TestCacheConfigModel:
    """Verify CacheConfig Pydantic model validation."""

    def test_default_config(self) -> None:
        """CacheConfig creates with sensible defaults."""
        config = CacheConfig()
        assert config.default_ttl == 300
        assert config.max_size == 10000
        assert config.backend == "memory"

    def test_custom_config(self) -> None:
        """CacheConfig accepts custom values."""
        config = CacheConfig(default_ttl=60, max_size=500, backend="redis")
        assert config.default_ttl == 60
        assert config.max_size == 500
        assert config.backend == "redis"

    def test_invalid_backend_fails(self) -> None:
        """backend must be 'memory' or 'redis'."""
        with pytest.raises(PydanticValidationError):
            CacheConfig(backend="memcached")  # type: ignore[arg-type]

    def test_negative_ttl_fails(self) -> None:
        """default_ttl must be >= 0."""
        with pytest.raises(PydanticValidationError):
            CacheConfig(default_ttl=-1)

    def test_negative_max_size_fails(self) -> None:
        """max_size must be >= 0."""
        with pytest.raises(PydanticValidationError):
            CacheConfig(max_size=-1)


class TestCacheEntryModel:
    """Verify CacheEntry Pydantic model."""

    def test_cache_entry_creation(self) -> None:
        """CacheEntry stores key, value, and timestamp."""
        import time
        ts = time.monotonic()
        entry = CacheEntry(key="test-key", value="test-value", expires_at=ts + 300, created_at=ts)
        assert entry.key == "test-key"
        assert entry.value == "test-value"
        assert entry.expires_at == ts + 300
        assert entry.created_at == ts
        assert entry.is_expired() is False

    def test_is_expired_returns_true_for_past_timestamp(self) -> None:
        """is_expired() returns True when expires_at is in the past."""
        import time
        entry = CacheEntry(key="expired", value="x", expires_at=time.monotonic() - 10)
        assert entry.is_expired() is True


class TestStampedeConfigModel:
    """Verify StampedeConfig Pydantic model."""

    def test_default_config(self) -> None:
        """StampedeConfig creates with XFetch defaults."""
        config = StampedeConfig()
        assert config.beta == 1.0
        assert config.delta == 0.5

    def test_custom_config(self) -> None:
        """StampedeConfig accepts custom beta/delta."""
        config = StampedeConfig(beta=2.0, delta=0.3)
        assert config.beta == 2.0
        assert config.delta == 0.3

    def test_negative_beta_fails(self) -> None:
        """beta must be >= 0."""
        with pytest.raises(PydanticValidationError):
            StampedeConfig(beta=-1.0)

    def test_negative_delta_fails(self) -> None:
        """delta must be >= 0."""
        with pytest.raises(PydanticValidationError):
            StampedeConfig(delta=-0.1)
