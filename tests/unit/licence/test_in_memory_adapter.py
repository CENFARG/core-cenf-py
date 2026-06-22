"""Unit tests for InMemoryLicenceAdapter — dict-backed test double.

Tests cover:
- load_license_from_string() for valid and invalid claims
- load_license_from_file() delegation
- get_license() for cached licences
- is_feature_enabled() single feature checks
- list_enabled_features() full feature map return
- Grace period: expired within grace_period_days → features accessible, is_valid=False
- Grace period: expired past grace_period_days → get_license() returns None
- revoke_license() removes cached licence
- get_json_schema() returns a dict
- Feature check for unlicensed tenant returns False

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import time

import pytest

from core_infrastructure.licence.models import LicenceConfig, LicenseClaims
from core_infrastructure.licence.ports import LicenceManager, LicenseInfo


class TestInMemoryLicenceAdapter:
    """Tests for InMemoryLicenceAdapter core behaviour."""

    @pytest.fixture
    def config(self) -> LicenceConfig:
        """Default LicenceConfig with 7-day grace period."""
        return LicenceConfig(grace_period_days=7)

    @pytest.fixture
    def valid_claims(self) -> LicenseClaims:
        """A valid enterprise licence with features."""
        return LicenseClaims(
            license_id="lic-001",
            tenant_id="t1",
            tier="enterprise",
            features={"ai_agents": True, "advanced_analytics": True, "api_access": True},
            issued_at=time.time() - 86400,
            expiry=time.time() + 86400 * 365,  # 1 year from now
        )

    @pytest.fixture
    def adapter(
        self, config: LicenceConfig, valid_claims: LicenseClaims
    ):
        """Create a fresh adapter with a pre-loaded licence for t1."""
        from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
            InMemoryLicenceAdapter,
        )

        adapter = InMemoryLicenceAdapter(config=config)
        adapter.add_license(valid_claims.tenant_id, valid_claims)
        return adapter

    # ── load_license_from_string ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_load_valid_license_from_string(
        self, config: LicenceConfig
    ) -> None:
        """load_license_from_string returns LicenseInfo for valid claims."""
        from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
            InMemoryLicenceAdapter,
        )

        adapter = InMemoryLicenceAdapter(config=config)
        info = await adapter.load_license_from_string(
            tenant_id="t1",
            raw_license="mock-valid-token",
        )
        assert isinstance(info, LicenseInfo)
        assert info.tenant_id() == "t1"
        assert info.is_valid() is True

    @pytest.mark.asyncio
    async def test_load_license_from_string_caches(
        self, config: LicenceConfig
    ) -> None:
        """After load_license_from_string, get_license returns the licence."""
        from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
            InMemoryLicenceAdapter,
        )

        adapter = InMemoryLicenceAdapter(config=config)
        await adapter.load_license_from_string(
            tenant_id="t1",
            raw_license="mock-valid-token",
        )
        info = await adapter.get_license(tenant_id="t1")
        assert info is not None
        assert info.tenant_id() == "t1"

    # ── load_license_from_file ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_load_license_from_file(self, config: LicenceConfig) -> None:
        """load_license_from_file delegates to load_license_from_string."""
        from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
            InMemoryLicenceAdapter,
        )

        adapter = InMemoryLicenceAdapter(config=config)
        info = await adapter.load_license_from_file(
            tenant_id="t1",
            path="/fake/path/license.lic",
        )
        assert info.tenant_id() == "t1"
        assert info.is_valid() is True

    # ── get_license ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_license_returns_info(self, adapter) -> None:
        """get_license returns LicenseInfo for a pre-loaded tenant."""
        info = await adapter.get_license(tenant_id="t1")
        assert info is not None
        assert info.tenant_id() == "t1"
        assert info.tier() == "enterprise"
        assert info.is_valid() is True
        assert info.is_grace_period() is False

    @pytest.mark.asyncio
    async def test_get_license_unknown_tenant_returns_none(
        self, adapter
    ) -> None:
        """get_license returns None for an unknown tenant."""
        info = await adapter.get_license(tenant_id="unknown")
        assert info is None

    # ── is_feature_enabled ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_is_feature_enabled_true(self, adapter) -> None:
        """is_feature_enabled returns True for an enabled feature."""
        result = await adapter.is_feature_enabled(
            tenant_id="t1", feature_key="ai_agents"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_is_feature_enabled_false(self, adapter) -> None:
        """is_feature_enabled returns False for a disabled/missing feature."""
        result = await adapter.is_feature_enabled(
            tenant_id="t1", feature_key="nonexistent"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_is_feature_enabled_unlicensed_tenant(
        self, adapter
    ) -> None:
        """Feature check for unlicensed tenant returns False."""
        result = await adapter.is_feature_enabled(
            tenant_id="unknown", feature_key="ai_agents"
        )
        assert result is False

    # ── list_enabled_features ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_enabled_features(self, adapter) -> None:
        """list_enabled_features returns all feature flags."""
        features = await adapter.list_enabled_features(tenant_id="t1")
        assert features == {
            "ai_agents": True,
            "advanced_analytics": True,
            "api_access": True,
        }

    @pytest.mark.asyncio
    async def test_list_enabled_features_unknown_tenant(self, adapter) -> None:
        """list_enabled_features for unknown tenant returns empty dict."""
        features = await adapter.list_enabled_features(tenant_id="unknown")
        assert features == {}

    # ── revoke_license ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_revoke_license(self, adapter) -> None:
        """revoke_license removes the licence from the adapter."""
        await adapter.revoke_license(tenant_id="t1")
        info = await adapter.get_license(tenant_id="t1")
        assert info is None

    @pytest.mark.asyncio
    async def test_revoke_license_unknown_tenant_noop(self, adapter) -> None:
        """revoke_license on unknown tenant is a no-op."""
        await adapter.revoke_license(tenant_id="unknown")
        # Should not raise

    # ── get_json_schema ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_json_schema_returns_dict(self) -> None:
        """get_json_schema returns a non-empty dict."""
        from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
            InMemoryLicenceAdapter,
        )

        schema = InMemoryLicenceAdapter.get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0

    # ── protocol compliance ───────────────────────────────────────────

    def test_satisfies_licence_manager_protocol(
        self, config: LicenceConfig
    ) -> None:
        """InMemoryLicenceAdapter satisfies the LicenceManager Protocol."""
        from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
            InMemoryLicenceAdapter,
        )

        adapter = InMemoryLicenceAdapter(config=config)
        assert isinstance(adapter, LicenceManager)


class TestGracePeriod:
    """Tests for grace period behaviour in InMemoryLicenceAdapter."""

    @pytest.fixture
    def config_grace_7d(self) -> LicenceConfig:
        """LicenceConfig with 7-day grace period."""
        return LicenceConfig(grace_period_days=7)

    @pytest.fixture
    def config_grace_0d(self) -> LicenceConfig:
        """LicenceConfig with 0-day grace period (hard deny)."""
        return LicenceConfig(grace_period_days=0)

    @pytest.mark.asyncio
    async def test_expired_within_grace_period_is_not_valid(
        self, config_grace_7d: LicenceConfig
    ) -> None:
        """Licence expired 3 days ago: is_valid=False, is_grace_period=True."""
        from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
            InMemoryLicenceAdapter,
        )

        now = time.time()
        expired_claims = LicenseClaims(
            license_id="lic-grace",
            tenant_id="t-grace",
            tier="pro",
            features={"feature_a": True},
            issued_at=now - 86400 * 30,
            expiry=now - 86400 * 3,  # expired 3 days ago
        )
        adapter = InMemoryLicenceAdapter(config=config_grace_7d)
        adapter.add_license("t-grace", expired_claims)

        info = await adapter.get_license(tenant_id="t-grace")
        assert info is not None
        assert info.is_valid() is False
        assert info.is_grace_period() is True

    @pytest.mark.asyncio
    async def test_expired_within_grace_period_features_accessible(
        self, config_grace_7d: LicenceConfig
    ) -> None:
        """Features remain accessible during grace period."""
        from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
            InMemoryLicenceAdapter,
        )

        now = time.time()
        expired_claims = LicenseClaims(
            license_id="lic-grace",
            tenant_id="t-grace",
            tier="pro",
            features={"feature_a": True, "feature_b": False},
            issued_at=now - 86400 * 30,
            expiry=now - 86400 * 3,
        )
        adapter = InMemoryLicenceAdapter(config=config_grace_7d)
        adapter.add_license("t-grace", expired_claims)

        enabled = await adapter.is_feature_enabled(
            tenant_id="t-grace", feature_key="feature_a"
        )
        assert enabled is True

        features = await adapter.list_enabled_features(tenant_id="t-grace")
        assert features == {"feature_a": True, "feature_b": False}

    @pytest.mark.asyncio
    async def test_expired_past_grace_period_returns_none(
        self, config_grace_7d: LicenceConfig
    ) -> None:
        """Licence expired 15 days ago with 7-day grace: get_license returns None."""
        from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
            InMemoryLicenceAdapter,
        )

        now = time.time()
        expired_claims = LicenseClaims(
            license_id="lic-old",
            tenant_id="t-old",
            tier="pro",
            features={"feature_a": True},
            issued_at=now - 86400 * 60,
            expiry=now - 86400 * 15,  # expired 15 days ago
        )
        adapter = InMemoryLicenceAdapter(config=config_grace_7d)
        adapter.add_license("t-old", expired_claims)

        info = await adapter.get_license(tenant_id="t-old")
        assert info is None

    @pytest.mark.asyncio
    async def test_expired_past_grace_features_disabled(
        self, config_grace_7d: LicenceConfig
    ) -> None:
        """Features are disabled when past grace period."""
        from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
            InMemoryLicenceAdapter,
        )

        now = time.time()
        expired_claims = LicenseClaims(
            license_id="lic-old",
            tenant_id="t-old",
            tier="pro",
            features={"feature_a": True},
            issued_at=now - 86400 * 60,
            expiry=now - 86400 * 15,
        )
        adapter = InMemoryLicenceAdapter(config=config_grace_7d)
        adapter.add_license("t-old", expired_claims)

        enabled = await adapter.is_feature_enabled(
            tenant_id="t-old", feature_key="feature_a"
        )
        assert enabled is False

    @pytest.mark.asyncio
    async def test_zero_grace_period_hard_deny(
        self, config_grace_0d: LicenceConfig
    ) -> None:
        """With 0 grace period days, any expired licence returns None immediately."""
        from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
            InMemoryLicenceAdapter,
        )

        now = time.time()
        expired_claims = LicenseClaims(
            license_id="lic-hard",
            tenant_id="t-hard",
            tier="pro",
            features={"feature_x": True},
            issued_at=now - 86400 * 30,
            expiry=now - 1,  # expired 1 second ago
        )
        adapter = InMemoryLicenceAdapter(config=config_grace_0d)
        adapter.add_license("t-hard", expired_claims)

        info = await adapter.get_license(tenant_id="t-hard")
        assert info is None

    @pytest.mark.asyncio
    async def test_perpetual_license_never_expires(
        self, config_grace_7d: LicenceConfig
    ) -> None:
        """A licence with expiry=None is always valid."""
        from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
            InMemoryLicenceAdapter,
        )

        perpetual_claims = LicenseClaims(
            license_id="lic-perpetual",
            tenant_id="t-perp",
            tier="enterprise",
            features={"all_access": True},
            issued_at=time.time() - 86400 * 30,
            expiry=None,  # perpetual
        )
        adapter = InMemoryLicenceAdapter(config=config_grace_7d)
        adapter.add_license("t-perp", perpetual_claims)

        info = await adapter.get_license(tenant_id="t-perp")
        assert info is not None
        assert info.is_valid() is True
        assert info.is_grace_period() is False

    @pytest.mark.asyncio
    async def test_revoked_license_returns_none(
        self, config_grace_7d: LicenceConfig
    ) -> None:
        """A revoked licence returns None regardless of validity."""
        from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
            InMemoryLicenceAdapter,
        )

        valid_claims = LicenseClaims(
            license_id="lic-rev",
            tenant_id="t-rev",
            tier="pro",
            features={"f1": True},
            issued_at=time.time() - 86400,
            expiry=time.time() + 86400 * 365,
        )
        adapter = InMemoryLicenceAdapter(config=config_grace_7d)
        adapter.add_license("t-rev", valid_claims)

        # Before revocation: valid
        info = await adapter.get_license(tenant_id="t-rev")
        assert info is not None
        assert info.is_valid() is True

        # Revoke
        await adapter.revoke_license(tenant_id="t-rev")

        # After revocation: None
        info = await adapter.get_license(tenant_id="t-rev")
        assert info is None
