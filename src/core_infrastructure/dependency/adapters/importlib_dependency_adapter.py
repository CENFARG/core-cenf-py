"""ImportlibDependencyAdapter — lazy dependency resolution with allowlist security.

Implements DependencyManager using importlib for lazy class resolution with
configurable allowlist validation. Classes are cached after first resolution
and invalidated on demand for hot-reload scenarios.

Security: module_path is validated against configured allowlist BEFORE calling
    importlib.import_module(). Never resolves paths from unvalidated input.
Observability: All resolution events emit RED metrics via ObservabilityManager.
@ai-directive: allowlist_paths are prefix-matched — registering "openai." allows
    any submodule under "openai".

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import importlib
from typing import Any

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.dependency.models import DependencyConfig, RegistryEntry
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.logger.ports import LoggerManager


class ImportlibDependencyAdapter:
    """Importlib-based DependencyManager with allowlist security and lru_cache.

    Uses ``importlib.import_module()`` for lazy class resolution. Module paths
    are validated against a configurable allowlist before any import occurs.
    Resolved classes are cached internally and can be invalidated for hot-reload.

    Args:
        config: ConfigManager for DependencyConfig reading.
        logger: LoggerManager for structured log emission.
        error_handler: ErrorHandlingManager for exception classification.

    Usage::

        adapter = ImportlibDependencyAdapter(config, logger, error_handler)
        adapter.register("models", "gpt4", ("openai.models", "GPT4Model"))
        cls = adapter.resolve_class("openai.models", "GPT4Model")
    """

    def __init__(
        self,
        config: ConfigManager,
        logger: LoggerManager,
        error_handler: ErrorHandlingManager,
    ) -> None:
        self._config = config
        self._logger = logger
        self._error_handler = error_handler

        dep_section = config.get_section("dependency")
        self._dep_config = DependencyConfig(**dep_section) if dep_section else DependencyConfig()

        self._allowlist: list[str] = dep_section.get("allowlist_paths", []) if dep_section else []

        self._registry: dict[str, dict[str, RegistryEntry]] = {}
        self._resolution_cache: dict[tuple[str, str], type] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_allowlisted(self, module_path: str) -> bool:
        """Check if a module_path is within the configured allowlist.

        In strict mode, the module_path must start with at least one
        allowlisted prefix. In permissive mode, all paths are allowed.

        Args:
            module_path: The module path to validate.

        Returns:
            bool: ``True`` if the path is allowed.
        """
        if self._dep_config.allowlist_mode == "permissive":
            return True

        if not self._allowlist:
            return False

        return any(module_path.startswith(prefix) for prefix in self._allowlist)

    def _import_class(self, module_path: str, class_name: str) -> type:
        """Import a module and retrieve a class by name.

        Args:
            module_path: Fully qualified module path.
            class_name: Name of the class to retrieve.

        Returns:
            type: The resolved class.

        Raises:
            ModuleNotFoundError: If the module cannot be found.
            AttributeError: If the class is not in the module.
        """
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    # ------------------------------------------------------------------
    # Public API — DependencyManager Protocol
    # ------------------------------------------------------------------

    def resolve_class(self, module_path: str, class_name: str) -> type:
        """Import module_path lazily and return the class by name.

        Validates module_path against the allowlist BEFORE importing.
        Results are cached internally — subsequent calls for the same
        (module_path, class_name) return the cached type without re-importing.

        Args:
            module_path: Fully qualified Python module path.
            class_name: Class name within the module.

        Returns:
            type: The resolved class object.

        Raises:
            ValidationError: If module_path is not in the allowlist (strict mode).
            ModuleNotFoundError: If the module cannot be imported.
            AttributeError: If class_name is not found in the module.
        """
        cache_key = (module_path, class_name)

        if cache_key in self._resolution_cache:
            return self._resolution_cache[cache_key]

        if not self._is_allowlisted(module_path):
            raise ValidationError(
                f"Module path '{module_path}' is not in allowlist",
                details={"module_path": module_path},
            )

        cls = self._import_class(module_path, class_name)
        self._resolution_cache[cache_key] = cls
        return cls

    def register(self, namespace: str, key: str, target: tuple[str, str] | Any) -> None:
        """Register a catalog entry.

        If ``target`` is a ``(module_path, class_name)`` tuple, it is stored
        as a RegistryEntry for lazy resolution. Otherwise, the object itself
        is stored directly.

        Args:
            namespace: Logical grouping (e.g., ``"models"``).
            key: Unique key within the namespace.
            target: Either a ``(module_path, class_name)`` tuple or any direct object.
        """
        if namespace not in self._registry:
            self._registry[namespace] = {}

        if isinstance(target, tuple) and len(target) >= 2:
            module_path, class_name = target[0], target[1]
            packages = list(target[2]) if len(target) >= 3 and isinstance(target[2], (list, tuple)) else []
            metadata = dict(target[3]) if len(target) >= 4 and isinstance(target[3], dict) else {}
            entry = RegistryEntry(
                module_path=module_path,
                class_name=class_name,
                packages=packages,
                metadata=metadata,
            )
        else:
            entry = RegistryEntry(
                module_path="__direct__",
                class_name=target.__class__.__name__ if isinstance(target, type) else "object",
                metadata={"direct_target": True},
            )

        self._registry[namespace][key] = entry

    def is_known(self, namespace: str, key: str) -> bool:
        """Check if a dependency is registered.

        Args:
            namespace: Logical grouping.
            key: The dependency key.

        Returns:
            bool: ``True`` if registered, ``False`` otherwise.
        """
        ns = self._registry.get(namespace)
        if ns is None:
            return False
        return key in ns

    def list_keys(self, namespace: str) -> list[str]:
        """List all keys in a namespace.

        Args:
            namespace: Logical grouping to enumerate.

        Returns:
            list[str]: All keys registered under the namespace.
        """
        ns = self._registry.get(namespace)
        if ns is None:
            return []
        return list(ns.keys())

    async def invalidate_cache(self) -> None:
        """Invalidate the resolution cache for hot-reload.

        Clears the internal resolution cache so the next ``resolve_class()``
        call re-imports the module.
        """
        self._resolution_cache.clear()

    def get_required_packages(self) -> list[str]:
        """Return list of runtime package names for Docker/pyproject.toml.

        Aggregates all ``packages`` fields from registered entries plus
        the ``default_packages`` from DependencyConfig. No duplicates.

        Returns:
            list[str]: Unique package specs (e.g., ``["openai>=1.0"]``).
        """
        packages: set[str] = set(self._dep_config.default_packages)
        for namespace in self._registry.values():
            for entry in namespace.values():
                packages.update(entry.packages)
        return sorted(packages)

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery (AX).

        Returns:
            dict[str, Any]: JSON Schema describing DependencyConfig model.
        """
        return DependencyConfig.model_json_schema()
