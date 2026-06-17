"""InMemoryDependencyAdapter — dict-based DependencyManager test double.

Provides a zero-dependency DependencyManager implementation for unit tests.
All dependencies are stored in a plain dict — no real imports, no filesystem,
no side effects. Useful for testing consumers that depend on DependencyManager.

Security: No real module imports occur — safe for CI without network.
Observability: Fully deterministic — no logging, no metrics emission.
@ai-directive: This adapter exists solely for testing. NEVER use it in
    production code paths.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any


class InMemoryDependencyAdapter:
    """Dict-based DependencyManager test double.

    All dependency registrations are stored in-memory. ``resolve_class()``
    resolves against a caller-provided mapping or the internal registry
    directly — no ``importlib`` calls are made.

    Args:
        mapping: Optional dict mapping ``(module_path, class_name)`` to
            the resolved object. Used for direct resolution without
            registering via ``register()``.
    """

    def __init__(self, mapping: dict[tuple[str, str], Any] | None = None) -> None:
        self._registry: dict[str, dict[str, tuple[str, str] | Any]] = {}
        self._mapping: dict[tuple[str, str], Any] = dict(mapping) if mapping else {}

    # ------------------------------------------------------------------
    # Public API — DependencyManager Protocol
    # ------------------------------------------------------------------

    def resolve_class(self, module_path: str, class_name: str) -> Any:
        """Return the registered target for the given module_path and class_name.

        First checks the explicit mapping, then falls back to the internal
        registry. Returns ``None`` if not found — never raises.

        Args:
            module_path: Module path (unused for actual import, used as lookup key).
            class_name: Class name (unused for actual import, used as lookup key).

        Returns:
            Any: The registered object, or ``None`` if not found.
        """
        key = (module_path, class_name)
        if key in self._mapping:
            return self._mapping[key]

        for namespace in self._registry.values():
            for entry_key, entry in namespace.items():
                if isinstance(entry, tuple) and len(entry) >= 2 and entry[0] == module_path and entry[1] == class_name and len(entry) > 2:
                    return entry[2] if len(entry) == 3 else entry
                elif entry_key == class_name:
                    return entry

        return None

    def register(self, namespace: str, key: str, target: tuple[str, str] | Any) -> None:
        """Register a catalog entry in the internal dict.

        Args:
            namespace: Logical grouping.
            key: Unique key within the namespace.
            target: Either a ``(module_path, class_name, [packages])`` tuple
                or any direct object.
        """
        if namespace not in self._registry:
            self._registry[namespace] = {}
        self._registry[namespace][key] = target

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
            namespace: Logical grouping.

        Returns:
            list[str]: All registered keys, or empty list.
        """
        ns = self._registry.get(namespace)
        if ns is None:
            return []
        return list(ns.keys())

    async def invalidate_cache(self) -> None:
        """Clear the internal registry entirely.

        After calling this, all registrations are lost and ``is_known()``
        returns ``False`` for all keys.
        """
        self._registry.clear()
        self._mapping.clear()

    def get_required_packages(self) -> list[str]:
        """Return aggregated packages from registered entries.

        Extracts the third element of tuples registered as targets
        (the packages list).

        Returns:
            list[str]: Package spec strings.
        """
        packages: set[str] = set()
        for namespace in self._registry.values():
            for entry in namespace.values():
                if isinstance(entry, tuple) and len(entry) >= 3:
                    pkg_list = entry[2]
                    if isinstance(pkg_list, (list, tuple)):
                        packages.update(str(p) for p in pkg_list)
        return sorted(packages)

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery (AX).

        Returns:
            dict[str, Any]: A minimal JSON Schema stub.
        """
        return {"type": "object", "description": "InMemoryDependencyAdapter schema stub."}
