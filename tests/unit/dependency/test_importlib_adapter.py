"""Unit tests for ImportlibDependencyAdapter — lazy resolution with allowlist security.

Tests cover:
- Protocol compliance (satisfies DependencyManager)
- register() and is_known()
- resolve_class() — lazy import + caching
- Allowlist validation — blocks non-allowlisted module paths
- get_required_packages() aggregation
- invalidate_cache() clears resolution cache
- list_keys() returns all keys in a namespace

Author: CENF AI Team
Version: 0.1.0
"""

import pytest

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.dependency.adapters.importlib_dependency_adapter import ImportlibDependencyAdapter
from core_infrastructure.dependency.ports import DependencyManager
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import InMemoryObservabilityAdapter


@pytest.fixture
def config() -> InMemoryConfigAdapter:
    """Create an InMemoryConfigAdapter with dependency settings."""
    return InMemoryConfigAdapter(
        initial_data={
            "dependency": {
                "allowlist_mode": "strict",
                "allowlist_paths": [
                    "tests.unit.dependency.fixtures.",
                    "core_infrastructure.",
                ],
                "default_packages": [],
            },
        },
    )


@pytest.fixture
def logger() -> InMemoryLoggerAdapter:
    """Create an InMemoryLoggerAdapter."""
    return InMemoryLoggerAdapter()


@pytest.fixture
def observability() -> InMemoryObservabilityAdapter:
    """Create an InMemoryObservabilityAdapter."""
    return InMemoryObservabilityAdapter()


@pytest.fixture
def error_handler(config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter, observability: InMemoryObservabilityAdapter) -> CapturingErrorAdapter:
    """Create a CapturingErrorAdapter with all dependencies."""
    return CapturingErrorAdapter(config, logger, observability)


@pytest.fixture
def adapter(config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter, error_handler: CapturingErrorAdapter) -> ImportlibDependencyAdapter:
    """Create an ImportlibDependencyAdapter with test config."""
    return ImportlibDependencyAdapter(config, logger, error_handler)


class TestImportlibAdapterProtocol:
    """Verify ImportlibDependencyAdapter satisfies DependencyManager Protocol."""

    def test_satisfies_dependency_manager_protocol(self, adapter: ImportlibDependencyAdapter) -> None:
        """ImportlibDependencyAdapter passes isinstance check against DependencyManager."""
        assert isinstance(adapter, DependencyManager)


class TestRegisterAndIsKnown:
    """Verify register() and is_known() methods."""

    def test_register_and_is_known(self, adapter: ImportlibDependencyAdapter) -> None:
        """register() adds entry and is_known() confirms it."""
        adapter.register("models", "gpt4", ("openai.models", "GPT4Model"))
        assert adapter.is_known("models", "gpt4") is True

    def test_is_known_returns_false_for_unknown(self, adapter: ImportlibDependencyAdapter) -> None:
        """is_known() returns False for unregistered keys."""
        assert adapter.is_known("models", "unknown_model") is False

    def test_is_known_returns_false_for_unknown_namespace(self, adapter: ImportlibDependencyAdapter) -> None:
        """is_known() returns False for unknown namespaces."""
        assert adapter.is_known("nonexistent", "anything") is False

    def test_register_with_direct_object(self, adapter: ImportlibDependencyAdapter) -> None:
        """register() accepts Any target (direct object, not just tuple)."""
        sentinel = object()
        adapter.register("tokens", "default", sentinel)
        assert adapter.is_known("tokens", "default") is True

    def test_list_keys_returns_all_keys_in_namespace(self, adapter: ImportlibDependencyAdapter) -> None:
        """list_keys() returns all registered keys for a namespace."""
        adapter.register("models", "a", ("mod_a", "A"))
        adapter.register("models", "b", ("mod_b", "B"))
        adapter.register("models", "c", ("mod_c", "C"))
        keys = adapter.list_keys("models")
        assert set(keys) == {"a", "b", "c"}

    def test_list_keys_returns_empty_for_unknown_namespace(self, adapter: ImportlibDependencyAdapter) -> None:
        """list_keys() returns empty list for unknown namespace."""
        assert adapter.list_keys("nonexistent") == []


class TestResolveClass:
    """Verify resolve_class() lazy resolution and caching."""

    def test_resolve_class_returns_class_for_valid_entry(self, adapter: ImportlibDependencyAdapter) -> None:
        """resolve_class imports and returns the registered class."""
        adapter.register("config", "core_settings", ("core_infrastructure.config.models", "CoreSettings"))
        cls = adapter.resolve_class("core_infrastructure.config.models", "CoreSettings")
        assert cls is not None
        assert cls.__name__ == "CoreSettings"

    def test_resolve_class_caches_result(self, adapter: ImportlibDependencyAdapter) -> None:
        """Second call to resolve_class returns same (cached) class instance."""
        adapter.register("config", "core_settings", ("core_infrastructure.config.models", "CoreSettings"))
        cls1 = adapter.resolve_class("core_infrastructure.config.models", "CoreSettings")
        cls2 = adapter.resolve_class("core_infrastructure.config.models", "CoreSettings")
        assert cls1 is cls2  # Same object from cache

    def test_resolve_class_with_module_not_in_allowlist_raises(self, adapter: ImportlibDependencyAdapter) -> None:
        """Calling resolve_class with module_path not in allowlist raises ValidationError."""
        with pytest.raises(ValidationError, match="not in allowlist"):
            adapter.resolve_class("os", "system")

    def test_resolve_class_with_class_not_found_raises(self, adapter: ImportlibDependencyAdapter) -> None:
        """Calling resolve_class for a class that doesn't exist in the module raises."""
        adapter.register("config", "bad_class", ("core_infrastructure.config.models", "NonExistentClass"))
        with pytest.raises(AttributeError):
            adapter.resolve_class("core_infrastructure.config.models", "NonExistentClass")


class TestGetRequiredPackages:
    """Verify get_required_packages() aggregates all packages."""

    def test_get_required_packages_aggregates_from_registry(self, adapter: ImportlibDependencyAdapter) -> None:
        """get_required_packages() returns packages from all registered entries."""
        adapter.register("models", "gpt4", ("openai.models", "GPT4Model", ["openai>=1.0"]))
        adapter.register("models", "claude", ("anthropic.models", "ClaudeModel", ["anthropic>=0.5"]))
        packages = adapter.get_required_packages()
        assert "openai>=1.0" in packages
        assert "anthropic>=0.5" in packages

    def test_get_required_packages_returns_empty_when_none_registered(self, adapter: ImportlibDependencyAdapter) -> None:
        """When no entries exist, get_required_packages() returns empty list."""
        packages = adapter.get_required_packages()
        assert packages == []

    def test_get_required_packages_no_duplicates(self, adapter: ImportlibDependencyAdapter) -> None:
        """Duplicate package specs appear only once."""
        adapter.register("a", "k1", ("m1", "C1", ["pkg>=1.0"]))
        adapter.register("b", "k2", ("m2", "C2", ["pkg>=1.0"]))
        packages = adapter.get_required_packages()
        assert packages.count("pkg>=1.0") == 1


class TestInvalidateCache:
    """Verify invalidate_cache() behavior."""

    @pytest.mark.asyncio
    async def test_invalidate_cache_clears_resolution_cache(self, adapter: ImportlibDependencyAdapter) -> None:
        """After cache invalidation, internal resolution cache is cleared."""
        adapter.register("config", "core_settings", ("core_infrastructure.config.models", "CoreSettings"))
        adapter.resolve_class("core_infrastructure.config.models", "CoreSettings")

        assert len(adapter._resolution_cache) == 1

        await adapter.invalidate_cache()

        assert len(adapter._resolution_cache) == 0

    @pytest.mark.asyncio
    async def test_invalidate_cache_allows_re_resolution(self, adapter: ImportlibDependencyAdapter) -> None:
        """After cache invalidation, resolve_class still works and repopulates cache."""
        adapter.register("config", "core_settings", ("core_infrastructure.config.models", "CoreSettings"))
        adapter.resolve_class("core_infrastructure.config.models", "CoreSettings")

        await adapter.invalidate_cache()
        assert len(adapter._resolution_cache) == 0

        cls = adapter.resolve_class("core_infrastructure.config.models", "CoreSettings")
        assert cls is not None
        assert cls.__name__ == "CoreSettings"
        assert len(adapter._resolution_cache) == 1
