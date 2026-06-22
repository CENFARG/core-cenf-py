"""LicenceManager Protocol — the contract every licence adapter must satisfy.

Defines the licence validation interface consumed by all infrastructure
managers that need feature-gating based on cryptographically signed licences.
Adapters implement RS256 JWT validation (JwtLicenceAdapter) or dict-backed
licences (InMemoryLicenceAdapter for testing).

Security: load_license_from_string() validates RS256 signatures against a
    public JWK from SecretManager. Grace-period logic returns degraded
    LicenseInfo rather than hard-blocking expired licences.
Observability: Licence validation events emit RED counters via
    ObservabilityManager.
@ai-directive: Use LicenceManager to determine which features exist for a
    tenant. This manager validates cryptographically signed licence documents
    and exposes feature availability as simple flags. It does NOT decide who
    can use features.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LicenseInfo(Protocol):
    """Represents a validated licence for a tenant.

    Abstract view over a tenant licence, including tier and enabled features.
    Implementations must be immutable or provide stable return values.

    Security:
        MUST NOT expose raw keys or signatures; only derived information.

    Observability:
        is_valid() and is_grace_period() are used to emit RED metrics for
        expired and grace-period licences.
    """

    def tenant_id(self) -> str:
        """Return the tenant identifier this licence is bound to.

        Returns:
            str: The tenant ID (e.g. ``"cntrs"``).
        """
        ...

    def tier(self) -> str:
        """Return the licence tier.

        Returns:
            str: One of ``"free"``, ``"pro"``, ``"enterprise"``.
        """
        ...

    def features(self) -> Mapping[str, bool]:
        """Return the feature flag map for this licence.

        Returns:
            Mapping[str, bool]: Feature name to enabled/disabled mapping.
        """
        ...

    def expires_at(self) -> float | None:
        """Return the expiration timestamp, or None if perpetual.

        Returns:
            float | None: UNIX epoch seconds, or None.
        """
        ...

    def is_valid(self) -> bool:
        """Return whether the licence is currently valid (not expired).

        A licence past its expiry but within the grace period is NOT valid
        but may still return features (degraded mode).

        Returns:
            bool: True if the licence has not expired and is not revoked.
        """
        ...

    def is_grace_period(self) -> bool:
        """Return whether the licence is within the grace period.

        During grace period, features remain accessible but is_valid()
        returns False.

        Returns:
            bool: True if the licence is expired but within grace period.
        """
        ...

    def claims(self) -> Mapping[str, Any]:
        """Return the full licence claims for inspection.

        Security:
            MUST NOT expose raw keys or signatures.

        Returns:
            Mapping[str, Any]: All licence claims as a read-only mapping.
        """
        ...


@runtime_checkable
class LicenceManager(Protocol):
    """Licence validation and feature-gating contract.

    All infrastructure managers that need feature-gating based on licences
    consume this interface. Concrete adapters provide RS256 JWT validation,
    offline activation from files, or configurable test licences.

    Rules:
        - load_license_from_string() validates RS256 + claims.
        - load_license_from_file() delegates to load_license_from_string().
        - get_license() returns the cached licence or None.
        - is_feature_enabled() checks a single feature flag.
        - list_enabled_features() returns all enabled features.
        - revoke_license() marks the current licence as revoked.
        - get_json_schema() describes this contract for agent discovery.
        - Grace period: expired licences within grace_period_days return
          degraded LicenseInfo (features accessible, is_valid=False).

    Security: NEVER trust a licence without full signature validation.
        Expired licences past grace period MUST return None.

    @ai-directive: Use LicenceManager to determine which features exist for
        a tenant. It does NOT decide who can use features — that is the
        PermissionManager's responsibility.
    """

    async def load_license_from_string(
        self, *, tenant_id: str, raw_license: str
    ) -> LicenseInfo:
        """Validate and load a licence document for a tenant from a raw string.

        Decodes the JWT, verifies RS256 signature, validates exp/iat/nbf
        claims, extracts features, and caches the result.

        Args:
            tenant_id: The tenant identifier the licence is for.
            raw_license: The raw signed licence token string (JWT).

        Returns:
            LicenseInfo: The validated licence information.

        Raises:
            AuthError: If the signature is invalid or claims are tampered.
            ValidationError: If the licence JSON is malformed.
        """
        ...

    async def load_license_from_file(
        self, *, tenant_id: str, path: str
    ) -> LicenseInfo:
        """Validate and load a licence from a local file (offline activation).

        Reads a ``.lic`` file, delegates to load_license_from_string() for
        validation.

        Args:
            tenant_id: The tenant identifier the licence is for.
            path: Path to the ``.lic`` file on disk.

        Returns:
            LicenseInfo: The validated licence information.

        Raises:
            AuthError: If the signature is invalid.
            PermanentError: If the file cannot be read.
        """
        ...

    async def get_license(self, *, tenant_id: str) -> LicenseInfo | None:
        """Return the last known valid licence for the tenant, if any.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            LicenseInfo | None: The cached licence, or None if no valid
                licence is loaded or it has expired past grace period.
        """
        ...

    async def is_feature_enabled(
        self, *, tenant_id: str, feature_key: str
    ) -> bool:
        """Check whether a feature is enabled for the tenant based on its licence.

        Args:
            tenant_id: The tenant identifier.
            feature_key: The feature name to check (e.g. ``"ai_agents"``).

        Returns:
            bool: True if the feature is listed and enabled in the licence.
        """
        ...

    async def list_enabled_features(
        self, *, tenant_id: str
    ) -> Mapping[str, bool]:
        """Return all enabled features for a tenant as a map.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            Mapping[str, bool]: All feature flags from the licence.
        """
        ...

    async def revoke_license(self, *, tenant_id: str) -> None:
        """Mark the current licence as revoked.

        Used when a licence server sends a revocation notification.
        After revocation, get_license() returns None.

        Args:
            tenant_id: The tenant identifier.
        """
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract for agent discovery.

        Returns a JSON Schema that tools/agents can use to understand
        how to call the LicenceManager.

        Returns:
            dict[str, Any]: JSON Schema describing the LicenceManager
                interface (methods, parameters, return types).
        """
        ...
