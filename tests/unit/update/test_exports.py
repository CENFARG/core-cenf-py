"""Unit tests for UpdateManager package exports.

Tests cover:
- UpdateManager Protocol is importable from core_infrastructure
- UpdateConfig model is importable from core_infrastructure
- ReleaseMetadata model is importable from core_infrastructure
- ArtifactMeta model is importable from core_infrastructure
- RollbackState model is importable from core_infrastructure
- Channel literal type is importable from core_infrastructure
- InMemoryUpdateAdapter is importable (zero optional deps)
- AvailableRelease Protocol is importable
- UpdateArtifact Protocol is importable
- UpdateResult Protocol is importable

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import importlib


class TestUpdateManagerExports:
    """Verify UpdateManager symbols are exported from core_infrastructure."""

    def test_update_manager_protocol_exported(self) -> None:
        """UpdateManager Protocol is available from core_infrastructure."""
        import core_infrastructure

        assert hasattr(core_infrastructure, "UpdateManager")

    def test_available_release_exported(self) -> None:
        """AvailableRelease Protocol is available from core_infrastructure."""
        import core_infrastructure

        assert hasattr(core_infrastructure, "AvailableRelease")

    def test_update_artifact_exported(self) -> None:
        """UpdateArtifact Protocol is available from core_infrastructure."""
        import core_infrastructure

        assert hasattr(core_infrastructure, "UpdateArtifact")

    def test_update_result_exported(self) -> None:
        """UpdateResult Protocol is available from core_infrastructure."""
        import core_infrastructure

        assert hasattr(core_infrastructure, "UpdateResult")

    def test_update_config_exported(self) -> None:
        """UpdateConfig model is available from core_infrastructure."""
        import core_infrastructure

        assert hasattr(core_infrastructure, "UpdateConfig")

    def test_release_metadata_exported(self) -> None:
        """ReleaseMetadata model is available from core_infrastructure."""
        import core_infrastructure

        assert hasattr(core_infrastructure, "ReleaseMetadata")

    def test_artifact_meta_exported(self) -> None:
        """ArtifactMeta model is available from core_infrastructure."""
        import core_infrastructure

        assert hasattr(core_infrastructure, "ArtifactMeta")

    def test_rollback_state_exported(self) -> None:
        """RollbackState model is available from core_infrastructure."""
        import core_infrastructure

        assert hasattr(core_infrastructure, "RollbackState")

    def test_channel_exported(self) -> None:
        """Channel literal is available from core_infrastructure."""
        import core_infrastructure

        assert hasattr(core_infrastructure, "Channel")

    def test_in_memory_update_adapter_exported(self) -> None:
        """InMemoryUpdateAdapter is available from core_infrastructure."""
        import core_infrastructure

        assert hasattr(core_infrastructure, "InMemoryUpdateAdapter")
        assert core_infrastructure.InMemoryUpdateAdapter is not None

    def test_http_update_adapter_reachable(self) -> None:
        """HttpUpdateAdapter is importable from its module."""
        from core_infrastructure.update.adapters.http_update_adapter import (
            HttpUpdateAdapter,
        )

        assert HttpUpdateAdapter is not None

    def test_module_reimport_does_not_crash(self) -> None:
        """Re-importing core_infrastructure is safe."""
        import core_infrastructure

        importlib.reload(core_infrastructure)
