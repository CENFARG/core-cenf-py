"""InMemoryLicenceAdapter — dict-backed LicenceManager test double.

Provides a lightweight, zero-I/O adapter for unit testing components that
depend on LicenceManager. Pre-configured licences are stored per tenant
in a dict and evaluated entirely in memory.

Grace period logic: if a licence is expired but the current time is within
config.grace_period_days after expiry, features remain accessible but
is_valid() returns False and is_grace_period() returns True. Past the grace
period, get_license() returns None.

Security: This adapter performs NO real cryptographic validation. NEVER use
    it in production.
Observability: No RED metrics emitted — this is a test-only adapter.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from core_infrastructure.licence.models import LicenceConfig, LicenseClaims
from core_infrastructure.licence.ports import LicenseInfo


class _InMemoryLicenseInfo:
    """Concrete LicenseInfo returned by InMemoryLicenceAdapter.

    Wraps LicenseClaims and provides the LicenseInfo Protocol interface
    with grace-period aware is_valid() and is_grace_period().

    Security: Never exposes raw keys or signatures — only derived claims.
    """

    def __init__(
        self,
        claims: LicenseClaims,
        *,
        grace_period_days: int,
        is_revoked: bool = False,
    ) -> None:
        self._claims = claims
        self._grace_period_days = grace_period_days
        self._is_revoked = is_revoked

    def tenant_id(self) -> str:
        """Return the tenant identifier."""
        return self._claims.tenant_id

    def tier(self) -> str:
        """Return the licence tier."""
        return self._claims.tier

    def features(self) -> Mapping[str, bool]:
        """Return the feature flag map."""
        return dict(self._claims.features)

    def expires_at(self) -> float | None:
        """Return the expiration timestamp, or None if perpetual."""
        return self._claims.expiry

    def is_valid(self) -> bool:
        """Return True if the licence is neither expired nor revoked.

        A licence within the grace period is NOT valid.
        """
        if self._is_revoked:
            return False
        expiry = self._claims.expiry
        if expiry is None:
            return True  # perpetual
        return time.time() <= expiry

    def is_grace_period(self) -> bool:
        """Return True if the licence is expired but within grace period.

        Grace period is config.grace_period_days after expiry.
        """
        if self._is_revoked:
            return False
        expiry = self._claims.expiry
        if expiry is None:
            return False
        now = time.time()
        return expiry < now <= expiry + self._grace_period_days * 86400

    def claims(self) -> Mapping[str, Any]:
        """Return the full licence claims as a dict."""
        return {
            "license_id": self._claims.license_id,
            "tenant_id": self._claims.tenant_id,
            "tier": self._claims.tier,
            "features": dict(self._claims.features),
            "expiry": self._claims.expiry,
            "not_before": self._claims.not_before,
            "max_seats": self._claims.max_seats,
            "issued_at": self._claims.issued_at,
            "installation_id": self._claims.installation_id,
        }


class InMemoryLicenceAdapter:
    """Dict-backed LicenceManager test double with grace period support.

    Pre-load licences via add_license() before running tests. Each tenant
    can have exactly one licence. Grace period logic is governed by
    LicenceConfig.grace_period_days.

    Usage::

        config = LicenceConfig(grace_period_days=7)
        adapter = InMemoryLicenceAdapter(config=config)
        adapter.add_license("t1", LicenseClaims(...))
        info = await adapter.get_license(tenant_id="t1")
    """

    def __init__(self, *, config: LicenceConfig) -> None:
        """Initialize the in-memory adapter.

        Args:
            config: LicenceConfig with grace_period_days and other settings.
        """
        self._config = config
        self._licences: dict[str, LicenseClaims] = {}
        self._revoked: set[str] = set()

    # ── Test helpers ──────────────────────────────────────────────────────

    def add_license(self, tenant_id: str, claims: LicenseClaims) -> None:
        """Pre-load a licence for a tenant (test helper).

        Args:
            tenant_id: The tenant identifier.
            claims: The LicenseClaims to store.
        """
        self._licences[tenant_id] = claims

    # ── Public API — LicenceManager Protocol ───────────────────────────────

    async def load_license_from_string(
        self, *, tenant_id: str, raw_license: str
    ) -> LicenseInfo:
        """Load a licence from a raw string (mock — no real validation).

        Creates a basic valid licence entry for the tenant. In test scenarios,
        use add_license() for fine-grained control.

        Args:
            tenant_id: The tenant identifier.
            raw_license: The raw licence string (ignored in test adapter).

        Returns:
            LicenseInfo: A valid licence info for the tenant.
        """
        claims = LicenseClaims(
            license_id=f"mock-{tenant_id}",
            tenant_id=tenant_id,
            tier="pro",
            issued_at=time.time(),
            expiry=time.time() + 86400 * 365,
        )
        self._licences[tenant_id] = claims
        return self._build_info(tenant_id, claims)

    async def load_license_from_file(
        self, *, tenant_id: str, path: str
    ) -> LicenseInfo:
        """Load a licence from a file path (mock — delegates to string).

        Args:
            tenant_id: The tenant identifier.
            path: Path to the ``.lic`` file (ignored in test adapter).

        Returns:
            LicenseInfo: A valid licence info for the tenant.
        """
        _ = path  # unused in test double
        return await self.load_license_from_string(
            tenant_id=tenant_id, raw_license="mock-file-content"
        )

    async def get_license(self, *, tenant_id: str) -> LicenseInfo | None:
        """Return the cached licence for the tenant, or None.

        Applies grace period logic: if the licence is expired past
        grace_period_days, returns None.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            LicenseInfo | None: The licence info, or None if no valid
                licence exists or it is expired past grace period.
        """
        if tenant_id in self._revoked:
            return None

        claims = self._licences.get(tenant_id)
        if claims is None:
            return None

        # Check if past grace period
        expiry = claims.expiry
        if expiry is not None:
            grace_seconds = self._config.grace_period_days * 86400
            if time.time() > expiry + grace_seconds:
                return None

        return self._build_info(tenant_id, claims)

    async def is_feature_enabled(
        self, *, tenant_id: str, feature_key: str
    ) -> bool:
        """Check whether a feature is enabled for the tenant.

        Args:
            tenant_id: The tenant identifier.
            feature_key: The feature name to check.

        Returns:
            bool: True if the feature is enabled in the licence.
        """
        info = await self.get_license(tenant_id=tenant_id)
        if info is None:
            return False
        features = info.features()
        return features.get(feature_key, False)

    async def list_enabled_features(
        self, *, tenant_id: str
    ) -> Mapping[str, bool]:
        """Return all feature flags for the tenant.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            Mapping[str, bool]: All feature flags from the licence.
        """
        info = await self.get_license(tenant_id=tenant_id)
        if info is None:
            return {}
        return info.features()

    async def revoke_license(self, *, tenant_id: str) -> None:
        """Mark the licence as revoked for the tenant.

        Args:
            tenant_id: The tenant identifier.
        """
        self._revoked.add(tenant_id)

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract for agent discovery.

        Returns:
            dict[str, Any]: JSON Schema describing the LicenceManager interface.
        """
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "LicenceManager",
            "type": "object",
            "description": (
                "Manages enterprise licences with cryptographically signed "
                "claims. Supports online/offline activation, grace period, "
                "and feature-gating."
            ),
            "properties": {
                "load_license_from_string": {
                    "type": "object",
                    "description": "Validate and load a licence from a raw string.",
                },
                "load_license_from_file": {
                    "type": "object",
                    "description": "Validate and load a licence from a .lic file.",
                },
                "get_license": {
                    "type": "object",
                    "description": "Return the cached licence or None.",
                },
                "is_feature_enabled": {
                    "type": "object",
                    "description": "Check if a feature is enabled.",
                },
            },
        }

    # ── Private helpers ───────────────────────────────────────────────────

    def _build_info(
        self, tenant_id: str, claims: LicenseClaims
    ) -> LicenseInfo:
        """Build a LicenseInfo instance from claims and current state.

        Args:
            tenant_id: The tenant identifier.
            claims: The LicenseClaims for the tenant.

        Returns:
            LicenseInfo: The concrete licence info with grace-period logic.
        """
        is_revoked = tenant_id in self._revoked
        return _InMemoryLicenseInfo(
            claims,
            grace_period_days=self._config.grace_period_days,
            is_revoked=is_revoked,
        )
