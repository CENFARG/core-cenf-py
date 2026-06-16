"""Unit tests for JwtAuthAdapter — HS256 JWT validation.

Tests cover:
- Valid HS256 token creation and validation
- Expired token rejection
- Invalid signature rejection
- Claims extraction (sub, iss, aud, scopes, tenant_id, principal_id)
- Scope validation
- Contextvars propagation (tenant_id, principal_id)
- nbf (not-before) validation
- iss/aud mismatch rejection

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import time

import pytest
from jose import jwt as jose_jwt

from core_infrastructure.auth.adapters.jwt_auth_adapter import JwtAuthAdapter
from core_infrastructure.auth.models import AuthConfig, TokenClaims
from core_infrastructure.auth.ports import AuthManager
from core_infrastructure.common.context import get_principal_id, get_tenant_id
from core_infrastructure.common.errors import AuthError
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import InMemorySecretAdapter


@pytest.fixture
def hs256_secret() -> str:
    """A valid HS256 symmetric key."""
    return "my-super-secret-hs256-key-for-testing-only-32bytes!!"


@pytest.fixture
def auth_adapter(hs256_secret: str) -> JwtAuthAdapter:
    """Create a JwtAuthAdapter with in-memory deps and HS256 secret."""
    secret_manager = InMemorySecretAdapter()
    secret_manager.set_secret("auth_signing_key", hs256_secret)
    config = InMemoryConfigAdapter()
    logger = InMemoryLoggerAdapter()
    observability = InMemoryObservabilityAdapter()
    auth_config = AuthConfig(
        issuer="https://auth.test.cenf.tech",
        audience="cenf-api-test",
        algorithms=["HS256"],
        token_leeway=30,
    )
    return JwtAuthAdapter(
        config=config,
        secret_manager=secret_manager,
        logger=logger,
        observability=observability,
        auth_config=auth_config,
    )


def _create_token(
    secret: str,
    claims: dict,
    algorithm: str = "HS256",
) -> str:
    """Helper to create a JWT token for testing."""
    return jose_jwt.encode(claims, secret, algorithm=algorithm)


class TestJwtAuthAdapterProtocol:
    """Verify JwtAuthAdapter satisfies AuthManager Protocol."""

    def test_satisfies_protocol(self, auth_adapter: JwtAuthAdapter) -> None:
        """JwtAuthAdapter passes isinstance check."""
        assert isinstance(auth_adapter, AuthManager)


class TestValidTokenValidation:
    """Verify JwtAuthAdapter validates legitimate tokens."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_claims(self, auth_adapter: JwtAuthAdapter, hs256_secret: str) -> None:
        """validate_token() returns TokenClaims for a valid HS256 token."""
        token = _create_token(
            hs256_secret,
            {
                "sub": "user-42",
                "iss": "https://auth.test.cenf.tech",
                "aud": "cenf-api-test",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()) - 60,
                "scopes": ["read:users", "write:users"],
                "tenant_id": "tenant-zeta",
                "principal_id": "principal-gamma",
            },
        )
        claims = await auth_adapter.validate_token(token)
        assert isinstance(claims, TokenClaims)
        assert claims.sub == "user-42"
        assert claims.iss == "https://auth.test.cenf.tech"
        assert claims.aud == "cenf-api-test"
        assert claims.tenant_id == "tenant-zeta"
        assert claims.principal_id == "principal-gamma"
        assert "read:users" in claims.scopes
        assert "write:users" in claims.scopes

    @pytest.mark.asyncio
    async def test_get_claims_returns_same_as_validate(self, auth_adapter: JwtAuthAdapter, hs256_secret: str) -> None:
        """get_claims() returns TokenClaims identical to validate_token()."""
        token = _create_token(
            hs256_secret,
            {
                "sub": "user-99",
                "iss": "https://auth.test.cenf.tech",
                "aud": "cenf-api-test",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()) - 60,
            },
        )
        claims = await auth_adapter.get_claims(token)
        assert claims.sub == "user-99"


class TestTokenRejection:
    """Verify JwtAuthAdapter rejects invalid tokens."""

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, auth_adapter: JwtAuthAdapter, hs256_secret: str) -> None:
        """validate_token() raises AuthError for expired tokens."""
        token = _create_token(
            hs256_secret,
            {
                "sub": "user-1",
                "iss": "https://auth.test.cenf.tech",
                "aud": "cenf-api-test",
                "exp": int(time.time()) - 3600,  # 1 hour expired
                "iat": int(time.time()) - 7200,
            },
        )
        with pytest.raises(AuthError) as exc_info:
            await auth_adapter.validate_token(token)
        assert "expired" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_wrong_signing_key_rejected(self, auth_adapter: JwtAuthAdapter) -> None:
        """validate_token() raises AuthError when signed with wrong key."""
        wrong_token = _create_token(
            "a-different-secret-that-does-not-match!!!!",
            {
                "sub": "user-1",
                "iss": "https://auth.test.cenf.tech",
                "aud": "cenf-api-test",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()),
            },
        )
        with pytest.raises(AuthError) as exc_info:
            await auth_adapter.validate_token(wrong_token)
        assert "signature" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_wrong_issuer_rejected(self, auth_adapter: JwtAuthAdapter, hs256_secret: str) -> None:
        """validate_token() raises AuthError when iss doesn't match."""
        token = _create_token(
            hs256_secret,
            {
                "sub": "user-1",
                "iss": "https://evil.example.com",
                "aud": "cenf-api-test",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()),
            },
        )
        with pytest.raises(AuthError) as exc_info:
            await auth_adapter.validate_token(token)
        assert "issuer" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_wrong_audience_rejected(self, auth_adapter: JwtAuthAdapter, hs256_secret: str) -> None:
        """validate_token() raises AuthError when aud doesn't match."""
        token = _create_token(
            hs256_secret,
            {
                "sub": "user-1",
                "iss": "https://auth.test.cenf.tech",
                "aud": "wrong-audience",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()),
            },
        )
        with pytest.raises(AuthError) as exc_info:
            await auth_adapter.validate_token(token)
        assert "audience" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_not_before_token_rejected(self, auth_adapter: JwtAuthAdapter, hs256_secret: str) -> None:
        """validate_token() raises AuthError when token is not yet valid (nbf)."""
        token = _create_token(
            hs256_secret,
            {
                "sub": "user-1",
                "iss": "https://auth.test.cenf.tech",
                "aud": "cenf-api-test",
                "exp": int(time.time()) + 7200,
                "iat": int(time.time()),
                "nbf": int(time.time()) + 3600,  # Not valid for 1 hour
            },
        )
        with pytest.raises(AuthError) as exc_info:
            await auth_adapter.validate_token(token)
        assert "not yet valid" in str(exc_info.value).lower() or "nbf" in str(exc_info.value).lower()


class TestScopeValidation:
    """Verify scope validation logic."""

    @pytest.mark.asyncio
    async def test_validate_scopes_with_sufficient_scopes(self, auth_adapter: JwtAuthAdapter) -> None:
        """validate_scopes() returns True when claims have required scopes."""
        claims = TokenClaims(
            sub="u",
            iss="i",
            aud="a",
            exp=9999999999,
            iat=1,
            scopes=["read:users", "write:users", "admin"],
        )
        result = auth_adapter.validate_scopes(claims, ["read:users"])
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_scopes_with_insufficient_scopes(self, auth_adapter: JwtAuthAdapter) -> None:
        """validate_scopes() returns False when claims lack required scopes."""
        claims = TokenClaims(
            sub="u",
            iss="i",
            aud="a",
            exp=9999999999,
            iat=1,
            scopes=["read:users"],
        )
        result = auth_adapter.validate_scopes(claims, ["admin"])
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_scopes_all_required(self, auth_adapter: JwtAuthAdapter) -> None:
        """validate_scopes() requires ALL scopes to be present."""
        claims = TokenClaims(
            sub="u",
            iss="i",
            aud="a",
            exp=9999999999,
            iat=1,
            scopes=["read:users"],
        )
        # Has read:users but NOT write:users
        result = auth_adapter.validate_scopes(claims, ["read:users", "write:users"])
        assert result is False


class TestContextvarsPropagation:
    """Verify token validation sets contextvars."""

    @pytest.mark.asyncio
    async def test_validate_token_sets_tenant_id(self, auth_adapter: JwtAuthAdapter, hs256_secret: str) -> None:
        """After validate_token(), tenant_id contextvar is set from claims."""
        token = _create_token(
            hs256_secret,
            {
                "sub": "user-1",
                "iss": "https://auth.test.cenf.tech",
                "aud": "cenf-api-test",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()),
                "tenant_id": "ctx-tenant",
            },
        )
        await auth_adapter.validate_token(token)
        assert get_tenant_id() == "ctx-tenant"

    @pytest.mark.asyncio
    async def test_validate_token_sets_principal_id(self, auth_adapter: JwtAuthAdapter, hs256_secret: str) -> None:
        """After validate_token(), principal_id contextvar is set from claims."""
        token = _create_token(
            hs256_secret,
            {
                "sub": "user-1",
                "iss": "https://auth.test.cenf.tech",
                "aud": "cenf-api-test",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()),
                "principal_id": "ctx-principal",
            },
        )
        await auth_adapter.validate_token(token)
        assert get_principal_id() == "ctx-principal"
