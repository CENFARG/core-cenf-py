---
sidebar_position: 19
---

# LicenceManager (M19)

Cryptographically signed licence validation using RS256 JWT tokens. Validates licence documents (online activation + offline `.lic` files), exposes feature availability as simple flags, and applies grace-period logic for degraded access — no hard block, features remain accessible in degraded mode. **LicenceManager determines WHAT features exist; PermissionManager determines WHO can use them.**

## Protocol

`LicenceManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.licence.ports`.

### `async load_license_from_string(*, tenant_id, raw_license) → LicenseInfo`

Validate and load a licence document from a raw JWT string. Decodes the JWT, verifies RS256 signature against the public JWK from SecretManager, validates `exp`/`iat`/`nbf` claims, extracts features, and caches the result.

```python
async def load_license_from_string(
    self, *, tenant_id: str, raw_license: str
) -> LicenseInfo: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `tenant_id` | `str` | Tenant identifier the licence is for |
| `raw_license` | `str` | Raw signed licence token (JWT) |

**Raises:** `AuthError` if signature is invalid or claims are tampered. `ValidationError` if the licence JSON is malformed.

---

### `async load_license_from_file(*, tenant_id, path) → LicenseInfo`

Validate and load a licence from a local `.lic` file (offline activation). Delegates to `load_license_from_string()`.

```python
async def load_license_from_file(
    self, *, tenant_id: str, path: str
) -> LicenseInfo: ...
```

**Raises:** `AuthError` if signature is invalid. `PermanentError` if file cannot be read.

---

### `async get_license(*, tenant_id) → LicenseInfo | None`

Return the last known valid licence for the tenant. Returns `None` if no valid licence is loaded or it has expired past the grace period.

```python
async def get_license(self, *, tenant_id: str) -> LicenseInfo | None: ...
```

---

### `async is_feature_enabled(*, tenant_id, feature_key) → bool`

Check whether a specific feature is enabled for the tenant.

```python
async def is_feature_enabled(
    self, *, tenant_id: str, feature_key: str
) -> bool: ...
```

---

### `async list_enabled_features(*, tenant_id) → Mapping[str, bool]`

Return all enabled features for a tenant as a map.

```python
async def list_enabled_features(
    self, *, tenant_id: str
) -> Mapping[str, bool]: ...
```

---

### `async revoke_license(*, tenant_id) → None`

Mark the current licence as revoked. After revocation, `get_license()` returns `None`.

```python
async def revoke_license(self, *, tenant_id: str) -> None: ...
```

---

### `get_json_schema() → dict[str, Any]` *(static)*

Return JSON Schema for agent discovery (AX).

---

## Models

**File:** `core_infrastructure.licence.models`

### `LicenseClaims`

Frozen model (`extra="forbid"`). Represents validated JWT claims — never carries raw token.

| Field | Type | Description |
|-------|------|-------------|
| `license_id` | `str` (1–64) | Unique licence identifier |
| `tenant_id` | `str` (1–64) | Tenant this licence is bound to |
| `tier` | `"free" \| "pro" \| "enterprise"` | Licence tier |
| `features` | `dict[str, bool]` | Feature name → enabled/disabled |
| `expiry` | `float \| None` | Expiration timestamp (UNIX epoch), `None` if perpetual |
| `not_before` | `float \| None` | Activation timestamp, `None` if immediately valid |
| `max_seats` | `int \| None` | Maximum concurrent seats, `None` if unlimited |
| `issued_at` | `float` (>0) | Issuance timestamp |
| `installation_id` | `str \| None` | Optional installation fingerprint for node-locking |

### `LicenceConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `public_key_jwk` | `str` (≤4096) | `""` | JWK JSON string for RS256 public key verification (from SecretManager) |
| `grace_period_days` | `int` (0–30) | `7` | Days after expiry with degraded feature access |
| `offline_mode_allowed` | `bool` | `False` | Whether offline `.lic` file activation is permitted |

---

## LicenseInfo Protocol

The `LicenseInfo` Protocol exposes:

| Method | Returns | Description |
|--------|---------|-------------|
| `tenant_id()` | `str` | Tenant the licence is bound to |
| `tier()` | `str` | `"free"`, `"pro"`, `"enterprise"` |
| `features()` | `Mapping[str, bool]` | Feature flag map |
| `expires_at()` | `float \| None` | Expiry timestamp or `None` (perpetual) |
| `is_valid()` | `bool` | `True` if not expired and not revoked |
| `is_grace_period()` | `bool` | `True` if expired but within grace period |
| `claims()` | `Mapping[str, Any]` | Full licence claims (no raw keys/signatures) |

---

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `JwtLicenceAdapter` | `python-jose` RS256 | Production — validates JWT signatures against JWK public key |
| `InMemoryLicenceAdapter` | In-memory dict | Testing — inject pre-configured licence claims |

**Grace period:** Expired licences within `grace_period_days` return degraded `LicenseInfo`: features remain accessible but `is_valid()` returns `False` and `is_grace_period()` returns `True`. After grace period expires, `get_license()` returns `None` and all features are disabled.

---

## Usage Example

```python
from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
    InMemoryLicenceAdapter,
)
from core_infrastructure.licence.models import LicenceConfig, LicenseClaims

# Testing: InMemoryLicenceAdapter
licence_mgr = InMemoryLicenceAdapter(config=LicenceConfig(grace_period_days=7))

# Load a licence for a tenant
claims = LicenseClaims(
    license_id="lic-001",
    tenant_id="cntrs",
    tier="pro",
    features={"ai_agents": True, "advanced_reports": True, "api_access": False},
    issued_at=1700000000.0,
)
await licence_mgr.load_license_from_claims(tenant_id="cntrs", claims=claims)

# Check features
licence = await licence_mgr.get_license(tenant_id="cntrs")
assert licence is not None
assert licence.tier() == "pro"
assert licence.is_valid() is True

# Feature gating
has_ai = await licence_mgr.is_feature_enabled(
    tenant_id="cntrs", feature_key="ai_agents"
)
# → True

has_api = await licence_mgr.is_feature_enabled(
    tenant_id="cntrs", feature_key="api_access"
)
# → False

all_features = await licence_mgr.list_enabled_features(tenant_id="cntrs")
# → {"ai_agents": True, "advanced_reports": True, "api_access": False}

# Unknown tenant
none = await licence_mgr.get_license(tenant_id="unknown")
# → None

# Revocation
await licence_mgr.revoke_license(tenant_id="cntrs")
assert await licence_mgr.get_license(tenant_id="cntrs") is None

# Production: JwtLicenceAdapter
# from core_infrastructure.licence.adapters.jwt_licence_adapter import JwtLicenceAdapter
# jose_mgr = JwtLicenceAdapter(config=LicenceConfig(
#     public_key_jwk=jwk_json_from_secret_manager,
#     grace_period_days=7,
#     offline_mode_allowed=True,
# ))
# info = await jose_mgr.load_license_from_string(
#     tenant_id="cntrs",
#     raw_license=signed_jwt_token,
# )
```

---

## @ai-directive

> **LicenceManager determines WHAT features exist; PermissionManager determines WHO can use them.** This manager validates cryptographically signed licence documents and exposes feature availability as simple flags. It does NOT decide who can use features. Always verify RS256 signatures and claims before caching. Expired licences within grace period return degraded `LicenseInfo` — features accessible, `is_valid=False`. Past grace period, `get_license()` returns `None`.

## Related

- [PermissionManager](permission-manager.md) — determines WHO can use features
- [SecretManager](secret-manager.md) — supplies the RS256 public JWK for signature verification
- [AuthManager](auth-manager.md) — same JWT verification pattern (HS256 vs RS256)
- [FeatureFlagManager](feature-flag-manager.md) — complementary runtime toggle system for non-licence features
