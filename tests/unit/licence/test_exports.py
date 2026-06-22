"""Verify LicenceManager package exports are accessible.

Tests cover:
- LicenceManager Protocol and LicenseInfo are exportable from package init
- LicenceConfig and LicenseClaims models are exportable
- Adapters are importable from their modules
- Exports match the __all__ list

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations


class TestPackageExports:
    """Verify that all LicenceManager symbols are properly exported."""

    def test_licence_manager_protocol_importable(self) -> None:
        """LicenceManager Protocol is importable from package."""
        from core_infrastructure.licence import LicenceManager

        assert LicenceManager is not None

    def test_license_info_protocol_importable(self) -> None:
        """LicenseInfo Protocol is importable from package."""
        from core_infrastructure.licence import LicenseInfo

        assert LicenseInfo is not None

    def test_licence_config_model_importable(self) -> None:
        """LicenceConfig model is importable from package."""
        from core_infrastructure.licence import LicenceConfig

        assert LicenceConfig is not None

    def test_license_claims_model_importable(self) -> None:
        """LicenseClaims model is importable from package."""
        from core_infrastructure.licence import LicenseClaims

        assert LicenseClaims is not None

    def test_in_memory_adapter_importable(self) -> None:
        """InMemoryLicenceAdapter is importable from its module."""
        from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
            InMemoryLicenceAdapter,
        )

        assert InMemoryLicenceAdapter is not None

    def test_jwt_adapter_importable(self) -> None:
        """JwtLicenceAdapter is importable from its module."""
        from core_infrastructure.licence.adapters.jwt_licence_adapter import (
            JwtLicenceAdapter,
        )

        assert JwtLicenceAdapter is not None

    def test_all_exports_match_expected(self) -> None:
        """Package __all__ contains expected symbols."""
        from core_infrastructure.licence import __all__ as exports

        expected = {"LicenceConfig", "LicenceManager", "LicenseClaims", "LicenseInfo"}
        assert expected.issubset(set(exports))

    def test_top_level_init_exports_licence_manager(self) -> None:
        """core_infrastructure init exports LicenceManager Protocol."""
        from core_infrastructure import LicenceManager  # type: ignore[attr-defined]

        assert LicenceManager is not None
