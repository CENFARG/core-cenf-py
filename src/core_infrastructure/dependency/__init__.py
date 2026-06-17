"""CENF DependencyManager — lazy, validated dependency resolution via importlib.

Provides a Protocol-based interface for plugin/class loading with allowlist
security validation. ImportlibDependencyAdapter implements the full contract
with lru_cache resolution; InMemoryDependencyAdapter is a dict-based test double.

Security: resolve_class() validates against allowlist BEFORE importing.
Observability: All resolution events emit RED metrics via ObservabilityManager.
@ai-directive: Catalogs are injected by consuming programs — the manager is
    framework-agnostic.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.dependency.adapters.importlib_dependency_adapter import ImportlibDependencyAdapter
from core_infrastructure.dependency.adapters.in_memory_dependency_adapter import InMemoryDependencyAdapter
from core_infrastructure.dependency.models import DependencyConfig, RegistryEntry
from core_infrastructure.dependency.ports import DependencyManager

__all__ = [
    "DependencyConfig",
    "DependencyManager",
    "ImportlibDependencyAdapter",
    "InMemoryDependencyAdapter",
    "RegistryEntry",
]
