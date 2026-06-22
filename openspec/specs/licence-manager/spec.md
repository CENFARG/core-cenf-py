---
Spec_ID: SPEC_M19
Title: LicenceManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [licence, jwt, claims, rs256, offline, grace-period]
Dependency_Hashes: []
Last_Updated: "2026-06-21"
---

# SPEC_M19: LicenceManager

## Purpose

Manage enterprise licenses with cryptographically signed claims (JWT-like with RS256/ES256). Supports online and offline activation, grace period instead of hard blocking, and clear separation from PermissionManager: licences define what features exist for a tenant; permissions define who can access those features.

**Does NOT**: Use obsolete cryptographic algorithms, implement intrusive DRM, mix with business logic, handle permission decisions (delegated to PermissionManager).

## Python Protocol

```python
from __future__ import annotations
from typing import Protocol, Mapping, Any, runtime_checkable


@runtime_checkable
class LicenseInfo(Protocol):
    """Represents a validated license for a tenant.

    Summary:
        Abstract view over a tenant license, including tier and enabled features.
    Security:
        MUST NOT expose raw keys or signatures; only derived information.
    """

    def tenant_id(self) -> str: ...
    def tier(self) -> str: ...
    def features(self) -> Mapping[str, bool]: ...
    def expires_at(self) -> float | None: ...
    def is_valid(self) -> bool: ...
    def is_grace_period(self) -> bool: ...
    def claims(self) -> Mapping[str, Any]: ...


@runtime_checkable
class LicenceManager(Protocol):
    """@ai-directive: Use LicenceManager to determine which features exist for a tenant.
    This manager validates cryptographically signed license documents and exposes
    feature availability as simple flags. It does NOT decide who can use features.
    """

    async def load_license_from_string(
        self, *, tenant_id: str, raw_license: str
    ) -> LicenseInfo:
        """Validate and load a license document for a tenant from a raw string."""
        ...

    async def load_license_from_file(
        self, *, tenant_id: str, path: str
    ) -> LicenseInfo:
        """Validate and load a license from a local file (offline activation)."""
        ...

    async def get_license(self, *, tenant_id: str) -> LicenseInfo | None:
        """Return the last known valid license for the tenant, if any."""
        ...

    async def is_feature_enabled(
        self, *, tenant_id: str, feature_key: str
    ) -> bool:
        """Check whether a feature is enabled for the tenant based on its license."""
        ...

    async def list_enabled_features(
        self, *, tenant_id: str
    ) -> Mapping[str, bool]:
        """Return all enabled features for a tenant as a map."""
        ...

    async def revoke_license(self, *, tenant_id: str) -> None:
        """Mark the current license as revoked (e.g. on server notification)."""
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract for agent discovery."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class LicenseClaims(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    license_id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64)
    tier: Literal["free", "pro", "enterprise"]
    features: dict[str, bool] = Field(default_factory=dict)
    expiry: float | None = Field(default=None, gt=0)
    not_before: float | None = Field(default=None, gt=0)
    max_seats: int | None = Field(default=None, gt=0)
    issued_at: float = Field(gt=0)
    installation_id: str | None = Field(default=None, max_length=128)


class LicenseSettings(BaseModel):
    model_config = {"extra": "forbid"}
    public_key_path: str | None = Field(default=None)
    public_key_pem: str | None = Field(default=None)
    algorithm: Literal["RS256", "ES256"] = Field(default="RS256")
    grace_period_days: int = Field(default=7, ge=0, le=30)
    offline_mode: bool = Field(default=False)
```

## Gherkin Scenarios

### Scenario: Valid license loaded from string

- GIVEN a cryptographically signed JWT-like license string with RS256 signature for tenant "t1", tier "enterprise", features `{"ai_agents": true, "advanced_analytics": true}`, expiry in 365 days
- WHEN `load_license_from_string(tenant_id="t1", raw_license=signed_token)` is called
- THEN it returns `LicenseInfo` with `tenant_id() == "t1"`, `tier() == "enterprise"`
- AND `is_valid() == True`
- AND `features()["ai_agents"] == True`

### Scenario: Expired license enters grace period

- GIVEN a valid license that expired 3 days ago
- GIVEN grace_period_days = 7
- WHEN `get_license(tenant_id="t1")` is called
- THEN it returns `LicenseInfo` with `is_valid() == False`
- AND `is_grace_period() == True`
- AND features remain accessible (degraded mode)

### Scenario: License past grace period denied

- GIVEN a license that expired 15 days ago
- GIVEN grace_period_days = 7
- WHEN `get_license(tenant_id="t1")` is called
- THEN it returns `None` (no valid license)
- AND all premium features are disabled

### Scenario: Offline activation from file

- GIVEN a `.lic` file containing a signed license document on disk
- WHEN `load_license_from_file(tenant_id="t1", path="/path/to/license.lic")` is called
- THEN it validates the signature using the configured public key
- AND returns `LicenseInfo` with the decoded claims
- AND caches the license for subsequent `get_license()` calls

### Scenario: Invalid signature raises AuthError

- GIVEN a tampered license string with modified claims but original signature
- WHEN `load_license_from_string(tenant_id="t1", raw_license=tampered)` is called
- THEN it raises `AuthError` with reason `"invalid_signature"`

### Scenario: Feature check for unlicensed tenant

- GIVEN no license has been loaded for tenant "t1"
- WHEN `is_feature_enabled(tenant_id="t1", feature_key="ai_agents")` is called
- THEN it returns `False`

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Invalid signature | AUTH | Re-raise immediately |
| Expired token (past grace) | AUTH | Return None, disable features |
| License file not found | PERMANENT | Return None |
| Public key misconfigured | PERMANENT | Fail bootstrap |
| Malformed license JSON | VALIDATION | Re-raise immediately |
| License server unreachable (online mode) | TRANSIENT | Retry with backoff, use cached |

## RED Metrics

- `cenf.licence.validate_total` (counter)
- `cenf.licence.expired_total` (counter)
- `cenf.licence.grace_period_active_total` (counter)
- `cenf.licence.validate_duration_seconds` (histogram)
- `cenf.licence.errors_total{reason="..."}` (counter)

## Test Requirements

- **Unit**: `InMemoryLicenceAdapter` — dict-based license store with mock signature validation. Tests all load methods, grace period logic, and feature checks.
- **Integration**: `CryptographyAdapter` with real RSA/ECDSA key pairs for signature verification.
- **E2E**: Full offline flow: generate signed license file → load → validate → check features → expire → grace period → hard deny.

## Do's and Don'ts

**Do**:
- Sign licenses with RSA/ECDSA (RS256 or ES256)
- Validate offline using configured public JWK
- Implement grace period instead of hard blocking
- Register license events as OTel metrics
- Separate licence concerns (what features exist) from permission concerns (who can use them)

**Don't**:
- Use obsolete cryptographic algorithms (MD5, SHA1, HS256 for licenses)
- Implement intrusive DRM (system scans, hard immediate blocking)
- Mix licence logic with business logic
- Log full license keys or signatures
