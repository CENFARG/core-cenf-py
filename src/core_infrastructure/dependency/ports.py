"""DependencyManager Protocol — lazy, validated dependency resolution via importlib.

Defines the contract for lazy dependency resolution consumed by infrastructure
managers that need plugin-like class loading. The Protocol validates module_path
against a configured allowlist BEFORE importing — never from user input directly.

Security: resolve_class() MUST validate against allowlist before importlib call.
Observability: All resolution events emit RED metrics via ObservabilityManager.
@ai-directive: module_path must come from a registry allowlisted; never from
    direct user input.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DependencyManager(Protocol):
    """Lazy dependency resolution contract for plugin/class loading.

    All infrastructure managers that need dynamic class loading consume this
    interface. Catalogs are injected by consuming programs — the manager itself
    is framework-agnostic.

    Rules:
        - resolve_class() validates module_path against allowlist BEFORE importing.
        - register() adds catalog entries injected by the consuming program.
        - is_known() is synchronous and cheap — no imports.
        - invalidate_cache() is async — supports hot-reload scenarios.
        - get_required_packages() enables Docker/pyproject.toml generation.

    @ai-directive: module_path must come from a registry allowlisted; never from
        direct user input.
    """

    def resolve_class(self, module_path: str, class_name: str) -> type:
        """Import module_path (lazy) and return class_name. Cached.

        Validates module_path against the configured allowlist BEFORE importing.
        Subsequent calls for the same (module_path, class_name) return the
        cached class without re-importing.

        Args:
            module_path: Fully qualified module path (e.g., ``"openai.models"``).
            class_name: The class name to retrieve from the module.

        Returns:
            type: The resolved class object.

        Raises:
            ValidationError: If module_path is not in the allowlist.
            ModuleNotFoundError: If the module cannot be imported.
            AttributeError: If class_name is not found in the module.
        """
        ...

    def register(self, namespace: str, key: str, target: tuple[str, str] | Any) -> None:
        """Register a catalog entry injected by the consuming program.

        Args:
            namespace: Logical grouping (e.g., ``"models"``, ``"agents"``).
            key: Unique key within the namespace (e.g., ``"gpt4"``).
            target: Either a ``(module_path, class_name)`` tuple for lazy
                resolution, or any direct object (pre-instantiated).
        """
        ...

    def is_known(self, namespace: str, key: str) -> bool:
        """Check if a dependency is registered.

        Synchronous and cheap — does not trigger any import.

        Args:
            namespace: Logical grouping.
            key: The dependency key.

        Returns:
            bool: ``True`` if the dependency is registered, ``False`` otherwise.
        """
        ...

    def list_keys(self, namespace: str) -> list[str]:
        """List all keys in a namespace.

        Args:
            namespace: Logical grouping to enumerate.

        Returns:
            list[str]: All keys registered under the namespace.
        """
        ...

    async def invalidate_cache(self) -> None:
        """Invalidate the resolution cache.

        Invoke on catalog hot-reload to force re-import of all dependencies
        on the next resolve_class() call.
        """
        ...

    def get_required_packages(self) -> list[str]:
        """Return list of runtime package names for Dockerfile/pyproject.toml.

        Aggregates all ``packages`` fields from registered RegistryEntry
        objects across all namespaces.

        Returns:
            list[str]: Package specs (e.g., ``["openai>=1.0", "anthropic>=0.5"]``)
                for use in ``pip install`` or Dockerfile commands.
        """
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery (AX).

        Returns:
            dict[str, Any]: A valid JSON Schema object describing the
                DependencyConfig model, enabling LLM agents to discover
                available configuration keys.
        """
        ...
