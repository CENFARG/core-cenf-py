"""Unit tests for DependencyManager Protocol and models.

Tests cover:
- DependencyManager Protocol contract methods
- Protocol is runtime-checkable
- RegistryEntry Pydantic model validation
- DependencyConfig Pydantic model validation
- Allowlist mode validation

Author: CENF AI Team
Version: 0.1.0
"""

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.dependency.models import DependencyConfig, RegistryEntry
from core_infrastructure.dependency.ports import DependencyManager


class TestDependencyManagerProtocol:
    """Verify DependencyManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """DependencyManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(DependencyManager, "_is_runtime_protocol")

    def test_has_resolve_class_method(self) -> None:
        """Protocol requires resolve_class(module_path, class_name) -> type."""
        assert hasattr(DependencyManager, "resolve_class")

    def test_has_register_method(self) -> None:
        """Protocol requires register(namespace, key, target)."""
        assert hasattr(DependencyManager, "register")

    def test_has_is_known_method(self) -> None:
        """Protocol requires is_known(namespace, key) -> bool."""
        assert hasattr(DependencyManager, "is_known")

    def test_has_list_keys_method(self) -> None:
        """Protocol requires list_keys(namespace) -> list[str]."""
        assert hasattr(DependencyManager, "list_keys")

    def test_has_invalidate_cache_method(self) -> None:
        """Protocol requires invalidate_cache() async."""
        assert hasattr(DependencyManager, "invalidate_cache")

    def test_has_get_required_packages_method(self) -> None:
        """Protocol requires get_required_packages() -> list[str]."""
        assert hasattr(DependencyManager, "get_required_packages")

    def test_has_get_json_schema_static_method(self) -> None:
        """Protocol requires get_json_schema() static method."""
        assert hasattr(DependencyManager, "get_json_schema")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all DependencyManager methods satisfies the protocol."""

        class ValidDep:
            def resolve_class(self, module_path: str, class_name: str) -> type:
                ...

            def register(self, namespace: str, key: str, target: tuple[str, str] | object) -> None:
                ...

            def is_known(self, namespace: str, key: str) -> bool:
                ...

            def list_keys(self, namespace: str) -> list[str]:
                ...

            async def invalidate_cache(self) -> None:
                ...

            @staticmethod
            def get_json_schema() -> dict[str, object]:
                ...

            def get_required_packages(self) -> list[str]:
                ...

        assert isinstance(ValidDep(), DependencyManager)

    def test_class_missing_resolve_class_fails_protocol(self) -> None:
        """A class without resolve_class() does NOT satisfy DependencyManager."""

        class Incomplete:
            def register(self, namespace: str, key: str, target: tuple[str, str] | object) -> None:
                ...

        assert not isinstance(Incomplete(), DependencyManager)


class TestRegistryEntryModel:
    """Verify RegistryEntry Pydantic model validation."""

    def test_registry_entry_creation(self) -> None:
        """RegistryEntry stores module_path, class_name, packages, metadata."""
        entry = RegistryEntry(
            module_path="test.module",
            class_name="TestClass",
            packages=["test>=1.0"],
            metadata={"version": "1.0"},
        )
        assert entry.module_path == "test.module"
        assert entry.class_name == "TestClass"
        assert entry.packages == ["test>=1.0"]
        assert entry.metadata == {"version": "1.0"}

    def test_registry_entry_default_packages_and_metadata(self) -> None:
        """RegistryEntry defaults packages to empty list and metadata to empty dict."""
        entry = RegistryEntry(module_path="a.b", class_name="C")
        assert entry.packages == []
        assert entry.metadata == {}

    def test_empty_module_path_fails(self) -> None:
        """module_path must have min_length=1."""
        with pytest.raises(PydanticValidationError):
            RegistryEntry(module_path="", class_name="C")

    def test_empty_class_name_fails(self) -> None:
        """class_name must have min_length=1."""
        with pytest.raises(PydanticValidationError):
            RegistryEntry(module_path="a.b", class_name="")


class TestDependencyConfigModel:
    """Verify DependencyConfig Pydantic model validation."""

    def test_default_config(self) -> None:
        """DependencyConfig creates with sensible defaults."""
        config = DependencyConfig()
        assert config.allowlist_mode == "strict"
        assert config.default_packages == []

    def test_custom_config(self) -> None:
        """DependencyConfig accepts custom allowlist_mode and packages."""
        config = DependencyConfig(
            allowlist_mode="permissive",
            default_packages=["pydantic>=2.0"],
        )
        assert config.allowlist_mode == "permissive"
        assert config.default_packages == ["pydantic>=2.0"]

    def test_invalid_allowlist_mode_fails(self) -> None:
        """allowlist_mode must be 'strict' or 'permissive'."""
        with pytest.raises(PydanticValidationError):
            DependencyConfig(allowlist_mode="block")  # type: ignore[arg-type]

    def test_default_packages_is_list(self) -> None:
        """default_packages is a list of strings."""
        config = DependencyConfig(default_packages=["a>=1.0", "b>=0.5"])
        assert isinstance(config.default_packages, list)
        assert len(config.default_packages) == 2
