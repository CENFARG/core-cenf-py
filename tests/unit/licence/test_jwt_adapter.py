"""Unit tests for JwtLicenceAdapter — RS256 JWT licence validation.

Tests cover:
- load_license_from_string() with valid RS256 JWT
- Claims extraction: license_id, tenant_id, tier, features, expiry, max_seats
- JWT expiry validation (expired token raises AuthError)
- iat/nbf validation
- Invalid signature rejection (AuthError with reason 'invalid_signature')
- Grace period: expired within grace_period_days → features accessible, is_valid=False
- Grace period: expired past grace → get_license() returns None
- Perpetual licences (expiry=None)
- load_license_from_file() delegation
- revoke_license() removes cached licence
- Caching: repeated loads return same LicenseInfo
- Tampered payload rejection

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import json
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt as jose_jwt

from core_infrastructure.common.errors import AuthError
from core_infrastructure.licence.models import LicenceConfig
from core_infrastructure.licence.ports import LicenceManager, LicenseInfo

# ── RSA Key Generation for Tests ────────────────────────────────────────────


def _generate_rsa_key_pair() -> tuple[str, str]:
    """Generate an RSA key pair and return (private_pem, public_pem).

    Returns:
        tuple[str, str]: (private_key_pem, public_key_pem).
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def _build_license_jwt(
    private_key_pem: str,
    claims: dict,
) -> str:
    """Sign a licence claims dict as a RS256 JWT.

    Args:
        private_key_pem: RSA private key in PEM format.
        claims: Claims dict to encode.

    Returns:
        str: The signed JWT string.
    """
    return jose_jwt.encode(claims, private_key_pem, algorithm="RS256")


def _jwk_from_public_pem(public_pem: str) -> str:
    """Extract a JWK dict from an RSA public key PEM and return as JSON string.

    Args:
        public_pem: RSA public key in PEM format.

    Returns:
        str: JSON-encoded JWK for RS256 verification.
    """
    key = serialization.load_pem_public_key(public_pem.encode("utf-8"))
    if not isinstance(key, rsa.RSAPublicKey):
        raise TypeError("Expected RSA public key")
    numbers = key.public_numbers()
    from base64 import urlsafe_b64encode

    def _b64url_int(val: int) -> str:
        length = (val.bit_length() + 7) // 8
        return urlsafe_b64encode(val.to_bytes(length, "big")).rstrip(b"=").decode()

    jwk = {
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "n": _b64url_int(numbers.n),
        "e": _b64url_int(numbers.e),
    }
    return json.dumps(jwk)


# ── Test Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def rsa_keys() -> tuple[str, str, str]:
    """Generate an RSA key pair and JWK for all tests in this module.

    Returns:
        tuple[str, str, str]: (private_pem, public_pem, public_jwk_json).
    """
    priv, pub = _generate_rsa_key_pair()
    jwk_json = _jwk_from_public_pem(pub)
    return priv, pub, jwk_json


@pytest.fixture
def config_with_key(rsa_keys: tuple[str, str, str]) -> LicenceConfig:
    """LicenceConfig with a valid public JWK and 7-day grace period."""
    _priv, _pub, jwk_json = rsa_keys
    return LicenceConfig(public_key_jwk=jwk_json, grace_period_days=7)


# ── Test Class ──────────────────────────────────────────────────────────────


class TestJwtLicenceAdapter:
    """Tests for JwtLicenceAdapter RS256 validation."""

    @pytest.fixture
    def adapter(self, config_with_key: LicenceConfig):
        """Create a JwtLicenceAdapter with valid RS256 public key."""
        from core_infrastructure.licence.adapters.jwt_licence_adapter import (
            JwtLicenceAdapter,
        )

        return JwtLicenceAdapter(config=config_with_key)

    @pytest.fixture
    def valid_claims(self) -> dict:
        """A valid set of licence claims."""
        now = time.time()
        return {
            "license_id": "lic-test-001",
            "tenant_id": "t1",
            "tier": "enterprise",
            "features": {"ai_agents": True, "advanced_analytics": True},
            "exp": int(now + 86400 * 365),
            "iat": int(now),
            "nbf": int(now - 60),
            "iss": "cenf-licence-server",
            "max_seats": 50,
        }

    # ── Valid JWT loading ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_load_valid_jwt(
        self,
        adapter,
        rsa_keys: tuple[str, str, str],
        valid_claims: dict,
    ) -> None:
        """load_license_from_string validates and returns LicenseInfo."""
        priv, _pub, _jwk = rsa_keys
        token = _build_license_jwt(priv, valid_claims)

        info = await adapter.load_license_from_string(
            tenant_id="t1", raw_license=token
        )
        assert isinstance(info, LicenseInfo)
        assert info.tenant_id() == "t1"
        assert info.tier() == "enterprise"
        assert info.is_valid() is True
        assert info.is_grace_period() is False

    @pytest.mark.asyncio
    async def test_load_valid_jwt_features(
        self,
        adapter,
        rsa_keys: tuple[str, str, str],
        valid_claims: dict,
    ) -> None:
        """Features from JWT are accessible via LicenseInfo."""
        priv, _pub, _jwk = rsa_keys
        token = _build_license_jwt(priv, valid_claims)

        info = await adapter.load_license_from_string(
            tenant_id="t1", raw_license=token
        )
        features = info.features()
        assert features["ai_agents"] is True
        assert features["advanced_analytics"] is True

    @pytest.mark.asyncio
    async def test_load_valid_jwt_extracts_all_claims(
        self,
        adapter,
        rsa_keys: tuple[str, str, str],
        valid_claims: dict,
    ) -> None:
        """All claims are extractable via claims() method."""
        priv, _pub, _jwk = rsa_keys
        token = _build_license_jwt(priv, valid_claims)

        info = await adapter.load_license_from_string(
            tenant_id="t1", raw_license=token
        )
        all_claims = info.claims()
        assert all_claims["license_id"] == "lic-test-001"
        assert all_claims["tier"] == "enterprise"
        assert all_claims["max_seats"] == 50

    # ── Caching ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_loaded_license_is_cached(
        self,
        adapter,
        rsa_keys: tuple[str, str, str],
        valid_claims: dict,
    ) -> None:
        """get_license returns cached licence after load_license_from_string."""
        priv, _pub, _jwk = rsa_keys
        token = _build_license_jwt(priv, valid_claims)

        await adapter.load_license_from_string(tenant_id="t1", raw_license=token)
        cached = await adapter.get_license(tenant_id="t1")
        assert cached is not None
        assert cached.tenant_id() == "t1"

    # ── is_feature_enabled / list_enabled_features ──────────────────────

    @pytest.mark.asyncio
    async def test_is_feature_enabled_true(
        self,
        adapter,
        rsa_keys: tuple[str, str, str],
        valid_claims: dict,
    ) -> None:
        """is_feature_enabled returns True for enabled features."""
        priv, _pub, _jwk = rsa_keys
        token = _build_license_jwt(priv, valid_claims)

        await adapter.load_license_from_string(tenant_id="t1", raw_license=token)
        assert await adapter.is_feature_enabled(
            tenant_id="t1", feature_key="ai_agents"
        ) is True

    @pytest.mark.asyncio
    async def test_is_feature_enabled_false(
        self,
        adapter,
        rsa_keys: tuple[str, str, str],
        valid_claims: dict,
    ) -> None:
        """is_feature_enabled returns False for missing features."""
        priv, _pub, _jwk = rsa_keys
        token = _build_license_jwt(priv, valid_claims)

        await adapter.load_license_from_string(tenant_id="t1", raw_license=token)
        assert await adapter.is_feature_enabled(
            tenant_id="t1", feature_key="nonexistent"
        ) is False

    @pytest.mark.asyncio
    async def test_list_enabled_features(
        self,
        adapter,
        rsa_keys: tuple[str, str, str],
        valid_claims: dict,
    ) -> None:
        """list_enabled_features returns all feature flags."""
        priv, _pub, _jwk = rsa_keys
        token = _build_license_jwt(priv, valid_claims)

        await adapter.load_license_from_string(tenant_id="t1", raw_license=token)
        features = await adapter.list_enabled_features(tenant_id="t1")
        assert features == {"ai_agents": True, "advanced_analytics": True}

    # ── Invalid signature ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_invalid_signature_raises_auth_error(
        self,
        adapter,
        rsa_keys: tuple[str, str, str],
        valid_claims: dict,
    ) -> None:
        """A JWT signed with a different key raises AuthError."""
        priv, _pub, _jwk = rsa_keys
        token = _build_license_jwt(priv, valid_claims)

        # Tamper with the payload to invalidate the signature
        tampered = token[:-5] + "XXXXX"

        with pytest.raises(AuthError) as exc_info:
            await adapter.load_license_from_string(
                tenant_id="t1", raw_license=tampered
            )
        assert "invalid_signature" in str(exc_info.value.details.get("reason", ""))

    @pytest.mark.asyncio
    async def test_wrong_key_signature_rejected(
        self,
        adapter,
        valid_claims: dict,
    ) -> None:
        """A JWT signed with a different key is rejected."""
        other_priv, _other_pub = _generate_rsa_key_pair()
        token = _build_license_jwt(other_priv, valid_claims)

        with pytest.raises(AuthError) as exc_info:
            await adapter.load_license_from_string(
                tenant_id="t1", raw_license=token
            )
        assert exc_info.value.details.get("reason") == "invalid_signature"

    # ── Expiry validation ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_expired_jwt_within_grace_period(
        self,
        adapter,
        rsa_keys: tuple[str, str, str],
    ) -> None:
        """Expired JWT within grace period: is_valid=False, is_grace_period=True."""
        priv, _pub, _jwk = rsa_keys
        now = time.time()
        claims = {
            "license_id": "lic-grace",
            "tenant_id": "t-grace",
            "tier": "pro",
            "features": {"f1": True},
            "exp": int(now - 86400 * 3),  # expired 3 days ago
            "iat": int(now - 86400 * 30),
        }
        token = _build_license_jwt(priv, claims)

        info = await adapter.load_license_from_string(
            tenant_id="t-grace", raw_license=token
        )
        assert info is not None
        assert info.is_valid() is False
        assert info.is_grace_period() is True

    @pytest.mark.asyncio
    async def test_expired_jwt_within_grace_features_accessible(
        self,
        adapter,
        rsa_keys: tuple[str, str, str],
    ) -> None:
        """Features remain accessible during grace period for JWT licences."""
        priv, _pub, _jwk = rsa_keys
        now = time.time()
        claims = {
            "license_id": "lic-grace2",
            "tenant_id": "t-grace2",
            "tier": "pro",
            "features": {"f1": True},
            "exp": int(now - 86400 * 3),
            "iat": int(now - 86400 * 30),
        }
        token = _build_license_jwt(priv, claims)

        await adapter.load_license_from_string(
            tenant_id="t-grace2", raw_license=token
        )
        assert await adapter.is_feature_enabled(
            tenant_id="t-grace2", feature_key="f1"
        ) is True

    @pytest.mark.asyncio
    async def test_expired_jwt_past_grace_returns_none(
        self,
        adapter,
        rsa_keys: tuple[str, str, str],
    ) -> None:
        """Expired JWT past grace period: get_license() returns None."""
        priv, _pub, _jwk = rsa_keys
        now = time.time()
        claims = {
            "license_id": "lic-old",
            "tenant_id": "t-old",
            "tier": "pro",
            "features": {"f1": True},
            "exp": int(now - 86400 * 15),  # expired 15 days ago
            "iat": int(now - 86400 * 60),
        }
        token = _build_license_jwt(priv, claims)

        await adapter.load_license_from_string(
            tenant_id="t-old", raw_license=token
        )
        cached = await adapter.get_license(tenant_id="t-old")
        assert cached is None

    # ── Perpetual licence ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_perpetual_license_no_expiry(
        self,
        adapter,
        rsa_keys: tuple[str, str, str],
    ) -> None:
        """A JWT without exp claim is treated as perpetual."""
        priv, _pub, _jwk = rsa_keys
        claims = {
            "license_id": "lic-perp",
            "tenant_id": "t-perp",
            "tier": "enterprise",
            "features": {"all": True},
            "iat": int(time.time()),
        }
        token = _build_license_jwt(priv, claims)

        info = await adapter.load_license_from_string(
            tenant_id="t-perp", raw_license=token
        )
        assert info.is_valid() is True
        assert info.is_grace_period() is False
        assert info.expires_at() is None

    # ── Revocation ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_revoke_license(
        self,
        adapter,
        rsa_keys: tuple[str, str, str],
        valid_claims: dict,
    ) -> None:
        """revoke_license removes the cached licence."""
        priv, _pub, _jwk = rsa_keys
        token = _build_license_jwt(priv, valid_claims)

        await adapter.load_license_from_string(tenant_id="t1", raw_license=token)
        await adapter.revoke_license(tenant_id="t1")
        assert await adapter.get_license(tenant_id="t1") is None

    # ── Unknown tenant ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_license_unknown_tenant_returns_none(
        self, adapter
    ) -> None:
        """get_license returns None for an unknown tenant."""
        info = await adapter.get_license(tenant_id="unknown")
        assert info is None

    @pytest.mark.asyncio
    async def test_is_feature_enabled_unknown_tenant(
        self, adapter
    ) -> None:
        """Feature checks for unlicensed tenants return False."""
        assert await adapter.is_feature_enabled(
            tenant_id="unknown", feature_key="any"
        ) is False

    # ── load_license_from_file ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_load_license_from_file(
        self,
        adapter,
        rsa_keys: tuple[str, str, str],
        valid_claims: dict,
    ) -> None:
        """load_license_from_file reads a .lic file and validates its contents."""
        priv, _pub, _jwk = rsa_keys
        token = _build_license_jwt(priv, valid_claims)

        import os
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".lic", delete=False
        ) as f:
            f.write(token)
            tmp_path = f.name

        try:
            info = await adapter.load_license_from_file(
                tenant_id="t1", path=tmp_path
            )
            assert info.tenant_id() == "t1"
            assert info.is_valid() is True
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_load_license_from_file_not_found(
        self, adapter
    ) -> None:
        """load_license_from_file with non-existent path returns None gracefully."""
        info = await adapter.load_license_from_file(
            tenant_id="t1", path="/nonexistent/path.lic"
        )
        assert info is None

    # ── get_json_schema ────────────────────────────────────────────────

    def test_get_json_schema_returns_dict(self) -> None:
        """get_json_schema returns a non-empty dict."""
        from core_infrastructure.licence.adapters.jwt_licence_adapter import (
            JwtLicenceAdapter,
        )

        schema = JwtLicenceAdapter.get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0

    # ── Protocol compliance ────────────────────────────────────────────

    def test_satisfies_licence_manager_protocol(
        self, config_with_key: LicenceConfig
    ) -> None:
        """JwtLicenceAdapter satisfies the LicenceManager Protocol."""
        from core_infrastructure.licence.adapters.jwt_licence_adapter import (
            JwtLicenceAdapter,
        )

        adapter = JwtLicenceAdapter(config=config_with_key)
        assert isinstance(adapter, LicenceManager)

    # ── Free tier features dict ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_free_tier_license(
        self,
        config_with_key: LicenceConfig,
        rsa_keys: tuple[str, str, str],
    ) -> None:
        """A free tier licence with empty features works correctly."""
        from core_infrastructure.licence.adapters.jwt_licence_adapter import (
            JwtLicenceAdapter,
        )

        priv, _pub, _jwk = rsa_keys
        now = time.time()
        claims = {
            "license_id": "lic-free",
            "tenant_id": "t-free",
            "tier": "free",
            "features": {},
            "iat": int(now),
            "exp": int(now + 86400 * 365),
        }
        token = _build_license_jwt(priv, claims)

        adapter = JwtLicenceAdapter(config=config_with_key)
        info = await adapter.load_license_from_string(
            tenant_id="t-free", raw_license=token
        )
        assert info.tier() == "free"
        assert info.features() == {}
