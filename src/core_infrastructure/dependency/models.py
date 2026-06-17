"""CENF DependencyManager models — RegistryEntry, DependencyConfig.

Defines the Pydantic models for DependencyManager configuration and data
transfer. RegistryEntry captures the target metadata for lazy resolution;
DependencyConfig controls allowlist mode and default packages.

Security: allowlist_mode enforces module_path validation before import.
Observability: RegistryEntry.metadata is free-form — no fixed schema.
@ai-directive: default_packages are merged with per-entry packages in
    get_required_packages(). No duplicates are returned.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RegistryEntry(BaseModel):
    """Metadata for a single registered dependency.

    Captures the module path, class name, required packages, and arbitrary
    metadata for a dependency. Used by both the Protocol and the adapter
    implementations to track registered entries.

    Attributes:
        module_path: Fully qualified Python module path.
        class_name: Target class name within the module.
        packages: List of pip package specs required at runtime.
        metadata: Arbitrary key-value metadata for the entry.
    """

    module_path: str = Field(..., min_length=1, description="Fully qualified Python module path.")
    class_name: str = Field(..., min_length=1, max_length=128, description="Target class name within the module.")
    packages: list[str] = Field(default_factory=list, description="pip package specs required at runtime.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary key-value metadata.")


class DependencyConfig(BaseModel):
    """Configuration for DependencyManager adapters.

    Controls the allowlist mode (strict vs permissive) and default packages
    that are always included regardless of what individual entries declare.

    Attributes:
        allowlist_mode: ``"strict"`` — only registered module_path prefixes
            are allowed. ``"permissive"`` — unregistered paths are allowed
            with a warning.
        default_packages: Packages always included in get_required_packages(),
            merged with per-entry packages.
    """

    allowlist_mode: Literal["strict", "permissive"] = Field(
        default="strict",
        description="Allowlist mode: 'strict' (block unknown paths) or 'permissive' (warn only).",
    )
    default_packages: list[str] = Field(
        default_factory=list,
        description="Packages always included in get_required_packages() output.",
    )
