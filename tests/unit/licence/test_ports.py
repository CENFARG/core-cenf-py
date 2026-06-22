"""Unit tests for LicenceManager Protocol and Licence models.

Tests cover:
- LicenceManager Protocol contract (load_license_from_string,
  load_license_from_file, get_license, is_feature_enabled,
  list_enabled_features, revoke_license, get_json_schema)
- LicenseInfo Protocol (tenant_id, tier, features, expires_at,
  is_valid, is_grace_period, claims)
- LicenseClaims Pydantic model validation
- LicenceConfig Pydantic model defaults and constraints
- Protocol is runtime-checkable

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.licence.models import LicenceConfig, LicenseClaims
from core_infrastructure.licence.ports import LicenceManager, LicenseInfo


class TestLicenseInfoProtocol:
    """Verify LicenseInfo Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """LicenseInfo Protocol is decorated with @runtime_checkable."""
        assert hasattr(LicenseInfo, "_is_runtime_protocol") or hasattr(
            LicenseInfo, "__protocol_attrs__"
        )

    def test_has_tenant_id_method(self) -> None:
        """Protocol requires tenant_id() -> str."""
        assert hasattr(LicenseInfo, "tenant_id")

    def test_has_tier_method(self) -> None:
        """Protocol requires tier() -> str."""
        assert hasattr(LicenseInfo, "tier")

    def test_has_features_method(self) -> None:
        """Protocol requires features() -> Mapping[str, bool]."""
        assert hasattr(LicenseInfo, "features")

    def test_has_expires_at_method(self) -> None:
        """Protocol requires expires_at() -> float | None."""
        assert hasattr(LicenseInfo, "expires_at")

    def test_has_is_valid_method(self) -> None:
        """Protocol requires is_valid() -> bool."""
        assert hasattr(LicenseInfo, "is_valid")

    def test_has_is_grace_period_method(self) -> None:
        """Protocol requires is_grace_period() -> bool."""
        assert hasattr(LicenseInfo, "is_grace_period")

    def test_has_claims_method(self) -> None:
        """Protocol requires claims() -> Mapping[str, Any]."""
        assert hasattr(LicenseInfo, "claims")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all LicenseInfo methods satisfies the protocol."""

        class ValidLicenseInfo:
            def tenant_id(self) -> str:
                return "t1"

            def tier(self) -> str:
                return "pro"

            def features(self) -> dict[str, bool]:
                return {"ai": True}

            def expires_at(self) -> float | None:
                return None

            def is_valid(self) -> bool:
                return True

            def is_grace_period(self) -> bool:
                return False

            def claims(self) -> dict[str, Any]:
                return {}

        assert isinstance(ValidLicenseInfo(), LicenseInfo)

    def test_class_missing_tenant_id_fails_protocol(self) -> None:
        """A class without tenant_id() does NOT satisfy LicenseInfo."""

        class Incomplete:
            def tier(self) -> str:
                return "pro"

        assert not isinstance(Incomplete(), LicenseInfo)


class TestLicenceManagerProtocol:
    """Verify LicenceManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """LicenceManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(LicenceManager, "_is_runtime_protocol") or hasattr(
            LicenceManager, "__protocol_attrs__"
        )

    def test_has_load_license_from_string(self) -> None:
        """Protocol requires load_license_from_string() -> LicenseInfo."""
        assert hasattr(LicenceManager, "load_license_from_string")

    def test_has_load_license_from_file(self) -> None:
        """Protocol requires load_license_from_file() -> LicenseInfo."""
        assert hasattr(LicenceManager, "load_license_from_file")

    def test_has_get_license(self) -> None:
        """Protocol requires get_license() -> LicenseInfo | None."""
        assert hasattr(LicenceManager, "get_license")

    def test_has_is_feature_enabled(self) -> None:
        """Protocol requires is_feature_enabled() -> bool."""
        assert hasattr(LicenceManager, "is_feature_enabled")

    def test_has_list_enabled_features(self) -> None:
        """Protocol requires list_enabled_features() -> Mapping."""
        assert hasattr(LicenceManager, "list_enabled_features")

    def test_has_revoke_license(self) -> None:
        """Protocol requires revoke_license() -> None."""
        assert hasattr(LicenceManager, "revoke_license")

    def test_has_get_json_schema(self) -> None:
        """Protocol requires get_json_schema() -> dict."""
        assert hasattr(LicenceManager, "get_json_schema")

    def test_get_json_schema_is_static(self) -> None:
        """get_json_schema is a staticmethod on the Protocol."""
        import inspect

        method = inspect.getattr_static(LicenceManager, "get_json_schema")
        assert isinstance(method, staticmethod)

    def test_complete_adapter_satisfies_protocol(self) -> None:
        """A class implementing all methods satisfies the LicenceManager Protocol."""

        class CompleteAdapter:
            async def load_license_from_string(
                self, *, tenant_id: str, raw_license: str
            ):
                ...

            async def load_license_from_file(
                self, *, tenant_id: str, path: str
            ):
                ...

            async def get_license(self, *, tenant_id: str):
                return None

            async def is_feature_enabled(
                self, *, tenant_id: str, feature_key: str
            ) -> bool:
                return False

            async def list_enabled_features(
                self, *, tenant_id: str
            ) -> dict[str, bool]:
                return {}

            async def revoke_license(self, *, tenant_id: str) -> None:
                return None

            @staticmethod
            def get_json_schema() -> dict[str, Any]:
                return {}

        assert isinstance(CompleteAdapter(), LicenceManager)

    def test_class_missing_load_license_fails_protocol(self) -> None:
        """A class without load_license_from_string does NOT satisfy LicenceManager."""

        class Incomplete:
            @staticmethod
            def get_json_schema() -> dict[str, Any]:
                return {}

        assert not isinstance(Incomplete(), LicenceManager)


class TestLicenseClaimsModel:
    """Verify LicenseClaims Pydantic model."""

    def test_valid_minimal_claims(self) -> None:
        """LicenseClaims with required fields only."""
        claims = LicenseClaims(
            license_id="lic-1",
            tenant_id="t1",
            tier="pro",
            issued_at=1719000000.0,
        )
        assert claims.license_id == "lic-1"
        assert claims.tenant_id == "t1"
        assert claims.tier == "pro"
        assert claims.features == {}
        assert claims.expiry is None
        assert claims.not_before is None
        assert claims.max_seats is None
        assert claims.issued_at == 1719000000.0
        assert claims.installation_id is None

    def test_valid_full_claims(self) -> None:
        """LicenseClaims with all fields populated."""
        claims = LicenseClaims(
            license_id="lic-2",
            tenant_id="t2",
            tier="enterprise",
            features={"ai_agents": True, "advanced_analytics": True},
            expiry=1750000000.0,
            not_before=1719000000.0,
            max_seats=50,
            issued_at=1719000000.0,
            installation_id="inst-123",
        )
        assert claims.license_id == "lic-2"
        assert claims.tenant_id == "t2"
        assert claims.tier == "enterprise"
        assert claims.features == {"ai_agents": True, "advanced_analytics": True}
        assert claims.expiry == 1750000000.0
        assert claims.not_before == 1719000000.0
        assert claims.max_seats == 50
        assert claims.installation_id == "inst-123"

    def test_free_tier_valid(self) -> None:
        """tier='free' is a valid tier."""
        claims = LicenseClaims(
            license_id="lic-3",
            tenant_id="t3",
            tier="free",
            issued_at=1719000000.0,
        )
        assert claims.tier == "free"

    def test_invalid_tier_fails(self) -> None:
        """tier must be one of 'free', 'pro', 'enterprise'."""
        with pytest.raises(PydanticValidationError):
            LicenseClaims(
                license_id="lic-4",
                tenant_id="t4",
                tier="platinum",  # type: ignore[arg-type]
                issued_at=1719000000.0,
            )

    def test_empty_license_id_fails(self) -> None:
        """license_id must not be empty."""
        with pytest.raises(PydanticValidationError):
            LicenseClaims(
                license_id="",
                tenant_id="t5",
                tier="pro",
                issued_at=1719000000.0,
            )

    def test_empty_tenant_id_fails(self) -> None:
        """tenant_id must not be empty."""
        with pytest.raises(PydanticValidationError):
            LicenseClaims(
                license_id="lic-5",
                tenant_id="",
                tier="pro",
                issued_at=1719000000.0,
            )

    def test_negative_issued_at_fails(self) -> None:
        """issued_at must be greater than 0."""
        with pytest.raises(PydanticValidationError):
            LicenseClaims(
                license_id="lic-6",
                tenant_id="t6",
                tier="pro",
                issued_at=-1.0,
            )

    def test_zero_issued_at_fails(self) -> None:
        """issued_at=0 fails (must be > 0)."""
        with pytest.raises(PydanticValidationError):
            LicenseClaims(
                license_id="lic-7",
                tenant_id="t7",
                tier="pro",
                issued_at=0.0,
            )

    def test_negative_expiry_fails(self) -> None:
        """expiry must be greater than 0 if set."""
        with pytest.raises(PydanticValidationError):
            LicenseClaims(
                license_id="lic-8",
                tenant_id="t8",
                tier="pro",
                issued_at=1719000000.0,
                expiry=-1.0,
            )

    def test_negative_max_seats_fails(self) -> None:
        """max_seats must be greater than 0 if set."""
        with pytest.raises(PydanticValidationError):
            LicenseClaims(
                license_id="lic-9",
                tenant_id="t9",
                tier="pro",
                issued_at=1719000000.0,
                max_seats=-1,
            )

    def test_zero_max_seats_fails(self) -> None:
        """max_seats=0 fails (must be > 0)."""
        with pytest.raises(PydanticValidationError):
            LicenseClaims(
                license_id="lic-10",
                tenant_id="t10",
                tier="pro",
                issued_at=1719000000.0,
                max_seats=0,
            )

    def test_extra_fields_forbidden(self) -> None:
        """LicenseClaims forbids extra fields (model_config extra='forbid')."""
        with pytest.raises(PydanticValidationError):
            LicenseClaims(
                license_id="lic-11",
                tenant_id="t11",
                tier="pro",
                issued_at=1719000000.0,
                unknown_field="nope",
            )

    def test_model_is_frozen(self) -> None:
        """LicenseClaims is frozen — attributes cannot be changed after creation."""
        claims = LicenseClaims(
            license_id="lic-12",
            tenant_id="t12",
            tier="pro",
            issued_at=1719000000.0,
        )
        with pytest.raises(PydanticValidationError):
            claims.license_id = "modified"  # type: ignore[misc]


class TestLicenceConfigModel:
    """Verify LicenceConfig Pydantic model."""

    def test_default_config(self) -> None:
        """LicenceConfig has sensible defaults."""
        config = LicenceConfig()
        assert config.public_key_jwk == ""
        assert config.grace_period_days == 7
        assert config.offline_mode_allowed is False

    def test_custom_config(self) -> None:
        """LicenceConfig with custom values."""
        config = LicenceConfig(
            public_key_jwk='{"kty":"RSA"}',
            grace_period_days=14,
            offline_mode_allowed=True,
        )
        assert config.public_key_jwk == '{"kty":"RSA"}'
        assert config.grace_period_days == 14
        assert config.offline_mode_allowed is True

    def test_grace_period_days_min_zero(self) -> None:
        """grace_period_days=0 is allowed (no grace period)."""
        config = LicenceConfig(grace_period_days=0)
        assert config.grace_period_days == 0

    def test_grace_period_days_negative_fails(self) -> None:
        """grace_period_days must not be negative."""
        with pytest.raises(PydanticValidationError):
            LicenceConfig(grace_period_days=-1)

    def test_grace_period_days_exceeds_max_30_fails(self) -> None:
        """grace_period_days must not exceed 30."""
        with pytest.raises(PydanticValidationError):
            LicenceConfig(grace_period_days=31)

    def test_public_key_jwk_can_be_empty(self) -> None:
        """public_key_jwk can be empty (no key configured)."""
        config = LicenceConfig(public_key_jwk="", grace_period_days=7)
        assert config.public_key_jwk == ""
