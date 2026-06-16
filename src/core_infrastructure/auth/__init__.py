"""CENF AuthManager — M2M token validation with HS256/RSA support.

Provides a Protocol-based interface for JWT token validation and claims
extraction. JwtAuthAdapter implements HS256 symmetric validation; RS256
via JWKS endpoint is planned. StaticAuthAdapter provides always-valid
claims for testing.

Security: All token validation includes exp, iat, nbf, iss, aud checks.
    Signing keys are retrieved from SecretManager — never hardcoded.
Observability: Token validation emits RED counters ``cenf.auth.token_valid_total``
    and ``cenf.auth.token_invalid_total``.
@ai-directive: NEVER use StaticAuthAdapter in production. JwtAuthAdapter
    currently supports HS256 only — RS256 planned.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.auth.adapters.jwt_auth_adapter import JwtAuthAdapter
from core_infrastructure.auth.adapters.static_auth_adapter import StaticAuthAdapter
from core_infrastructure.auth.models import AuthConfig, JWKSKey, TokenClaims
from core_infrastructure.auth.ports import AuthManager

__all__ = [
    "AuthConfig",
    "AuthManager",
    "JWKSKey",
    "JwtAuthAdapter",
    "StaticAuthAdapter",
    "TokenClaims",
]
