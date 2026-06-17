"""Unit tests for InMemoryDependencyAdapter — dict-based test double.

Tests cover:
- Protocol compliance (satisfies DependencyManager)
- Register and resolve with dict-based catalog
- is_known and list_keys
- No real imports — all resolution is dict-based
- Cache invalidation

Author: CENF AI Team
Version: 0.1.0
"""

import pytest

from core_infrastructure.dependency.adapters.in_memory_dependency_adapter import InMemoryDependencyAdapter
from core_infrastructure.dependency.ports import DependencyManager


@pytest.fixture
def adapter() -> InMemoryDependencyAdapter:
    """Create a fresh InMemoryDependencyAdapter."""
    return InMemoryDependencyAdapter()


class TestInMemoryAdapterProtocol:
    """Verify InMemoryDependencyAdapter satisfies DependencyManager Protocol."""

    def test_satisfies_dependency_manager_protocol(self, adapter: InMemoryDependencyAdapter) -> None:
        """InMemoryDependencyAdapter passes isinstance check against DependencyManager."""
        assert isinstance(adapter, DependencyManager)


class TestInMemoryRegisterAndIsKnown:
    """Verify register() and is_known() in the in-memory adapter."""

    def test_register_and_is_known(self, adapter: InMemoryDependencyAdapter) -> None:
        """register() adds entry and is_known() returns True."""
        adapter.register("models", "test_model", ("my.module", "MyClass"))
        assert adapter.is_known("models", "test_model") is True

    def test_is_known_returns_false_for_unknown(self, adapter: InMemoryDependencyAdapter) -> None:
        """is_known() returns False for unregistered key."""
        assert adapter.is_known("models", "missing") is False

    def test_list_keys_returns_registered_keys(self, adapter: InMemoryDependencyAdapter) -> None:
        """list_keys() returns all keys in a namespace."""
        adapter.register("ns", "k1", ("m1", "C1"))
        adapter.register("ns", "k2", ("m2", "C2"))
        assert set(adapter.list_keys("ns")) == {"k1", "k2"}

    def test_list_keys_empty_namespace(self, adapter: InMemoryDependencyAdapter) -> None:
        """list_keys() returns empty list for unknown namespace."""
        assert adapter.list_keys("unknown") == []


class TestInMemoryResolve:
    """Verify resolve_class() in the in-memory adapter."""

    def test_resolve_class_returns_registered_object(self, adapter: InMemoryDependencyAdapter) -> None:
        """resolve_class returns the target when looked up by module_path and class_name."""
        sentinel = object()
        adapter.register("svc", "my_service", ("my.module", "MyClass", [sentinel]))
        result = adapter.resolve_class("my.module", "MyClass")
        assert isinstance(result, list)
        assert result[0] is sentinel

    def test_resolve_class_returns_direct_object(self, adapter: InMemoryDependencyAdapter) -> None:
        """resolve_class returns a direct object registered in the mapping."""
        sentinel = object()
        mapping = {("direct.module", "DirectClass"): sentinel}
        adapter = InMemoryDependencyAdapter(mapping=mapping)
        result = adapter.resolve_class("direct.module", "DirectClass")
        assert result is sentinel

    def test_resolve_class_returns_none_for_unknown(self, adapter: InMemoryDependencyAdapter) -> None:
        """resolve_class returns None when not found in registry."""
        result = adapter.resolve_class("nonexistent.module", "NoClass")
        assert result is None

    def test_resolve_class_uses_mapping(self, adapter: InMemoryDependencyAdapter) -> None:
        """When a dict mapping is provided, resolve_class uses it."""
        fake_class = type("FakeClass", (), {})
        mapping = {("some.module", "SomeClass"): fake_class}
        adapter = InMemoryDependencyAdapter(mapping=mapping)
        result = adapter.resolve_class("some.module", "SomeClass")
        assert result is fake_class


class TestInMemoryPackagesAndCache:
    """Verify get_required_packages() and invalidate_cache() for in-memory adapter."""

    def test_get_required_packages_aggregates_packages(self, adapter: InMemoryDependencyAdapter) -> None:
        """get_required_packages() collects packages from registered entries."""
        adapter.register("m", "k1", ("m1", "C1", ["pkg_a>=1.0"]))
        adapter.register("m", "k2", ("m2", "C2", ["pkg_b>=0.5"]))
        packages = adapter.get_required_packages()
        assert "pkg_a>=1.0" in packages
        assert "pkg_b>=0.5" in packages

    @pytest.mark.asyncio
    async def test_invalidate_cache_clears_internal_state(self, adapter: InMemoryDependencyAdapter) -> None:
        """invalidate_cache() clears the internal catalog."""
        adapter.register("ns", "key", ("mod", "Class"))
        assert adapter.is_known("ns", "key") is True
        await adapter.invalidate_cache()
        assert adapter.is_known("ns", "key") is False
