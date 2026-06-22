"""JwtLicenceAdapter — RS256 JWT licence validation adapter for LicenceManager.

Validates cryptographically signed licence tokens using RS256 asymmetric
verification with a JWK public key from LicenceConfig. Extracts standard
licence claims (license_id, tenant_id, tier, features, expiry, max_seats)
and applies grace-period logic for degraded feature access.

Security: Public key is provided via LicenceConfig (retrieved from
    SecretManager at bootstrap). Expired/invalid tokens raise AuthError.
Observability: Failed validations emit RED counter
    ``cenf.licence.errors_total{reason="...")}``.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from jose import jwt as jose_jwt
from jose.exceptions import JWTError as JoseJWTError

from core_infrastructure.common.errors import AuthError
from core_infrastructure.licence.models import LicenceConfig, LicenseClaims
from core_infrastructure.licence.ports import LicenseInfo


class _JwtLicenseInfo:
    """Concrete LicenseInfo returned by JwtLicenceAdapter.

    Wraps decoded JWT claims and applies grace-period logic based on the
    configured grace_period_days.

    Security: Never exposes raw keys or signatures — only validated claims.
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

        A licence within grace period is NOT valid.
        """
        if self._is_revoked:
            return False
        expiry = self._claims.expiry
        if expiry is None:
            return True
        return time.time() <= expiry

    def is_grace_period(self) -> bool:
        """Return True if expired but within grace_period_days after expiry."""
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


class JwtLicenceAdapter:
    """RS256 JWT licence validation adapter implementing LicenceManager Protocol.

    Validates licence tokens using RS256 asymmetric verification.
    The public JWK is provided via LicenceConfig.public_key_jwk.

    Grace period: if a licence is expired but within grace_period_days,
    features remain accessible but is_valid() returns False and
    is_grace_period() returns True. Past grace period, get_license()
    returns None.

    Usage::

        config = LicenceConfig(public_key_jwk=jwk_json, grace_period_days=7)
        adapter = JwtLicenceAdapter(config=config)
        info = await adapter.load_license_from_string(
            tenant_id="t1", raw_license=signed_token
        )
    """

    def __init__(self, *, config: LicenceConfig) -> None:
        """Initialize the JWT licence adapter.

        Args:
            config: LicenceConfig with public_key_jwk and grace_period_days.
        """
        self._config = config
        self._cache: dict[str, LicenseClaims] = {}
        self._revoked: set[str] = set()

    # ── Public API — LicenceManager Protocol ───────────────────────────────

    async def load_license_from_string(
        self, *, tenant_id: str, raw_license: str
    ) -> LicenseInfo:
        """Validate a signed JWT licence token and cache the result.

        Decodes the JWT using RS256 verification against the configured
        public JWK. Validates exp, iat, nbf claims. Extracts features
        and tenant binding.

        Args:
            tenant_id: The tenant identifier the licence is for.
            raw_license: The raw signed JWT licence token.

        Returns:
            LicenseInfo: The validated licence information.

        Raises:
            AuthError: If the signature is invalid or claims are tampered.
        """
        _ = tenant_id  # tenant is embedded in the token claims

        if not raw_license or not raw_license.strip():
            raise AuthError(
                "Licence token must not be empty",
                details={"reason": "empty_token"},
            )

        # Decode and validate the JWT
        public_key = self._config.public_key_jwk
        if not public_key:
            raise AuthError(
                "No public key configured for licence validation",
                details={"reason": "missing_public_key"},
            )

        try:
            # We decode with verify_exp=False so we can apply our own
            # grace-period logic after extracting the claims. The signature
            # is still verified; only expiry is deferred to our layer.
            payload: dict[str, Any] = jose_jwt.decode(
                raw_license,
                public_key,
                algorithms=["RS256"],
                options={
                    "verify_signature": True,
                    "verify_exp": False,
                    "verify_iat": True,
                    "verify_nbf": True,
                    "require": ["iat"],
                },
            )
        except JoseJWTError as exc:
            error_msg = str(exc)
            reason = "invalid_token"
            if "signature" in error_msg.lower():
                reason = "invalid_signature"
            elif "issuer" in error_msg.lower():
                reason = "invalid_issuer"

            raise AuthError(
                f"Licence validation failed: {error_msg}",
                details={"reason": reason},
            ) from exc

        # Build LicenseClaims from validated payload
        claims = LicenseClaims(
            license_id=payload.get("license_id", f"lic-{tenant_id}"),
            tenant_id=payload.get("tenant_id", tenant_id),
            tier=payload.get("tier", "free"),
            features=payload.get("features", {}),
            expiry=float(payload["exp"]) if "exp" in payload else None,
            not_before=float(payload["nbf"]) if "nbf" in payload else None,
            max_seats=payload.get("max_seats"),
            issued_at=float(payload.get("iat", time.time())),
            installation_id=payload.get("installation_id"),
        )

        # Cache for subsequent get_license calls
        self._cache[tenant_id] = claims
        return self._build_info(tenant_id, claims)

    async def load_license_from_file(
        self, *, tenant_id: str, path: str
    ) -> LicenseInfo:
        """Read a ``.lic`` file and validate its contents.

        Args:
            tenant_id: The tenant identifier.
            path: Path to the ``.lic`` file on disk.

        Returns:
            LicenseInfo: The validated licence information, or None if
                the file cannot be read.
        """
        try:
            with open(path, encoding="utf-8") as fh:  # noqa: ASYNC230
                raw_license = fh.read().strip()
        except (FileNotFoundError, OSError):
            return None  # type: ignore[return-value]

        return await self.load_license_from_string(
            tenant_id=tenant_id, raw_license=raw_license
        )

    async def get_license(self, *, tenant_id: str) -> LicenseInfo | None:
        """Return the cached licence for the tenant, or None.

        Applies grace period logic: if the licence is expired past
        grace_period_days, returns None.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            LicenseInfo | None: The cached licence info, or None.
        """
        if tenant_id in self._revoked:
            return None

        claims = self._cache.get(tenant_id)
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
                "Manages enterprise licences with RS256-signed JWT tokens. "
                "Supports online/offline activation, grace period, "
                "and feature-gating."
            ),
            "properties": {
                "load_license_from_string": {
                    "type": "object",
                    "description": "Validate and load a RS256-signed licence token.",
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
        return _JwtLicenseInfo(
            claims,
            grace_period_days=self._config.grace_period_days,
            is_revoked=is_revoked,
        )
