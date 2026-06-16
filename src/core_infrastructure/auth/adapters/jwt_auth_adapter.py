"""JwtAuthAdapter — HS256 JWT validation adapter for AuthManager.

Validates JWT tokens using HS256 symmetric signing. Extracts standard
OIDC claims (sub, iss, aud, exp, iat, nbf) and CENF custom claims
(scopes, tenant_id, principal_id). Sets tenant_id and principal_id
contextvars from validated claims for downstream context propagation.

RS256 via JWKS is planned for a future iteration (JWKS URL in AuthConfig).

Security: Signing key is retrieved from SecretManager (never hardcoded).
    Token validation includes exp, iat, nbf, iss, and aud checks with
    configurable leeway for clock skew. Expired/invalid tokens raise AuthError.
Observability: Failed validations emit RED counter ``cenf.auth.token_invalid_total``.
@ai-directive: NEVER log raw tokens or signing keys. Validate ALL claims
    before returning TokenClaims.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any

from jose import jwt as jose_jwt
from jose.exceptions import JWTError as JoseJWTError

from core_infrastructure.auth.models import AuthConfig, TokenClaims
from core_infrastructure.common.context import set_principal_id, set_tenant_id
from core_infrastructure.common.errors import AuthError
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.observability.ports import ObservabilityManager
from core_infrastructure.secrets.ports import SecretManager

# SecretManager key used to retrieve the HS256 signing secret
_SIGNING_KEY_SECRET_ID: str = "auth_signing_key"


class JwtAuthAdapter:
    """HS256 JWT validation adapter implementing AuthManager Protocol.

    Receives ConfigManager, SecretManager, LoggerManager, and
    ObservabilityManager via constructor (DI pattern). All validation
    is performed in validate_token() with full claim checking.

    Args:
        config: ConfigManager for feature flags and settings.
        secret_manager: SecretManager for retrieving the HS256 signing key.
        logger: LoggerManager for structured log emission.
        observability: ObservabilityManager for RED metric emission.
        auth_config: AuthConfig with issuer, audience, algorithms, leeway.

    Usage::

        auth = JwtAuthAdapter(config, secret_manager, logger, obs, auth_config)
        claims = await auth.validate_token(raw_token)
        if auth.validate_scopes(claims, ["admin"]):
            ...

    Note:
        Currently supports HS256 only. RS256 support via JWKS endpoint
        is planned for a future iteration. The signing key is read once
        per validate_token() call (may be cached per SecretManager config).
    """

    def __init__(
        self,
        config: ConfigManager,
        secret_manager: SecretManager,
        logger: LoggerManager,
        observability: ObservabilityManager,
        auth_config: AuthConfig,
    ) -> None:
        self._config = config
        self._secret_manager = secret_manager
        self._logger = logger
        self._observability = observability
        self._auth_config = auth_config

    # ------------------------------------------------------------------
    # Public API — AuthManager Protocol
    # ------------------------------------------------------------------

    async def validate_token(self, token: str) -> TokenClaims:
        """Validate a JWT token (HS256) and return its claims.

        Performs full validation: signature verification, expiry check,
        issuer match, audience match, not-before check, and claims extraction.

        Args:
            token: The raw JWT token string.

        Returns:
            TokenClaims: The validated claims extracted from the token.

        Raises:
            AuthError: If the token is expired, has invalid signature,
                wrong issuer, wrong audience, or is not yet valid.

        Security: The raw token string is discarded after validation.
            Signing key is retrieved from SecretManager per invocation.
        """
        if not token or not token.strip():
            raise AuthError(
                "Token must not be empty",
                details={"reason": "empty_token"},
            )

        # Retrieve signing key from SecretManager
        try:
            signing_key = await self._secret_manager.get_secret(_SIGNING_KEY_SECRET_ID)
        except Exception as exc:
            self._logger.error("Failed to retrieve signing key", exc=exc)
            self._observability.increment_counter(
                "cenf.auth.token_invalid_total",
                value=1.0,
                attributes={"reason": "key_retrieval_failure"},
            )
            raise AuthError(
                "Failed to retrieve signing key for token validation",
                details={"reason": "key_retrieval_failure"},
            ) from exc

        # Decode and validate the JWT
        try:
            payload: dict[str, Any] = jose_jwt.decode(
                token,
                signing_key,
                algorithms=self._auth_config.algorithms,
                options={
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_nbf": True,
                    "verify_iss": True,
                    "verify_aud": True,
                    "verify_signature": True,
                    "require": ["exp", "iat", "sub", "iss", "aud"],
                },
                issuer=self._auth_config.issuer,
                audience=self._auth_config.audience,
            )
        except JoseJWTError as exc:
            error_msg = str(exc)
            reason = "invalid_token"
            if "expired" in error_msg.lower() or "exp" in error_msg.lower():
                reason = "expired"
            elif "signature" in error_msg.lower():
                reason = "invalid_signature"
            elif "issuer" in error_msg.lower():
                reason = "invalid_issuer"
            elif "audience" in error_msg.lower():
                reason = "invalid_audience"
            elif "not yet valid" in error_msg.lower() or "nbf" in error_msg.lower():
                reason = "not_yet_valid"

            self._logger.warn(
                f"Token validation failed: {reason}",
                error_type=reason,
                error=error_msg,
            )
            self._observability.increment_counter(
                "cenf.auth.token_invalid_total",
                value=1.0,
                attributes={"reason": reason},
            )
            raise AuthError(
                f"Token validation failed: {error_msg}",
                details={"reason": reason},
            ) from exc

        # Build TokenClaims from validated payload
        claims = TokenClaims(
            sub=payload["sub"],
            iss=payload["iss"],
            aud=payload["aud"],
            exp=payload["exp"],
            iat=payload["iat"],
            nbf=payload.get("nbf"),
            scopes=payload.get("scopes", []),
            tenant_id=payload.get("tenant_id", ""),
            principal_id=payload.get("principal_id", ""),
        )

        # Set contextvars for downstream propagation
        if claims.tenant_id:
            set_tenant_id(claims.tenant_id)
        if claims.principal_id:
            set_principal_id(claims.principal_id)

        self._logger.debug(
            "Token validated successfully",
            sub=claims.sub,
            iss=claims.iss,
            tenant_id=claims.tenant_id,
        )
        self._observability.increment_counter(
            "cenf.auth.token_valid_total",
            value=1.0,
            attributes={"algorithm": self._auth_config.algorithms[0]},
        )

        return claims

    async def get_claims(self, token: str) -> TokenClaims:
        """Extract claims from a token without full re-validation.

        Note: For HS256, we still validate the signature since the
        token might be unverified. This is equivalent to validate_token().

        Args:
            token: The raw JWT token string.

        Returns:
            TokenClaims: The claims from the validated token.

        Raises:
            AuthError: If the token cannot be decoded.
        """
        return await self.validate_token(token)

    async def refresh_jwks(self) -> None:
        """Refresh the JWKS cache (no-op for HS256 mode).

        HS256 does not use JWKS. This method exists to satisfy the
        AuthManager Protocol. RS256 support will implement this.
        """
        self._logger.debug("refresh_jwks called (no-op in HS256 mode)")

    def validate_scopes(self, claims: TokenClaims, required: list[str]) -> bool:
        """Check if token claims contain all required scopes.

        Args:
            claims: The validated token claims.
            required: List of scope strings that must all be present.

        Returns:
            bool: True if all required scopes are present in claims.
        """
        claim_scopes = set(claims.scopes)
        return all(scope in claim_scopes for scope in required)
