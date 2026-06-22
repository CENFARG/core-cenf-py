---
sidebar_position: 6
---

# AuthManager (M06)

JWT token validation with HS256 symmetric signing and JWKS-based RS256 support. Sets `tenant_id` and `principal_id` contextvars from validated claims for multi-tenant authorization.

## Protocol

`AuthManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.auth.ports`.

### `async validate_token(token: str) → TokenClaims`

Validate a JWT token and return its claims.

```python
async def validate_token(self, token: str) -> TokenClaims: ...
```

Performs **full validation**: signature, expiry (`exp`), issuer (`iss`), audience (`aud`), not-before (`nbf`), and issued-at (`iat`). Sets `tenant_id` and `principal_id` contextvars on success.

| Param | Type | Description |
|-------|------|-------------|
| `token` | `str` | The raw JWT token string |

**Returns:** `TokenClaims` — validated claims extracted from the token.

**Raises `AuthError` if:**
- The token is expired
- The signature is invalid
- The issuer is wrong
- The audience is wrong
- The token is not yet valid (`nbf`)

**Security:** The raw token string is NEVER stored in `TokenClaims`.

---

### `async get_claims(token: str) → TokenClaims`

Extract claims from a token without full re-validation.

```python
async def get_claims(self, token: str) -> TokenClaims: ...
```

Useful for reading claims from an already-validated token (e.g., middleware that validates once, then downstream code reads claims).

**Raises:** `AuthError` if the token cannot be decoded.

---

### `async refresh_jwks() → None`

Refresh the JWKS cache from the configured JWKS endpoint.

```python
async def refresh_jwks(self) -> None: ...
```

Called periodically (e.g., every 60 minutes) to pick up key rotations. Must be idempotent and safe to call concurrently.

**Raises:** `AuthError` if the JWKS endpoint is unreachable.

---

### `validate_scopes(claims: TokenClaims, required: list[str]) → bool`

Check if token claims contain all required scopes.

```python
def validate_scopes(self, claims: TokenClaims, required: list[str]) -> bool: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `claims` | `TokenClaims` | The validated token claims |
| `required` | `list[str]` | List of scope strings that must all be present |

**Returns:** `True` if all required scopes are present in `claims.scopes`.

**Note:** This method is **sync** — pure logic with no I/O.

---

### `get_json_schema() → dict[str, Any]`

Return the JSON Schema describing `AuthConfig`.

## Models

### `TokenClaims`

**File:** `core_infrastructure.auth.models`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `sub` | `str` (1–256) | *(required)* | Subject identifier |
| `iss` | `str` (1–512) | *(required)* | Issuer URL (e.g., `https://auth.cenf.tech`) |
| `aud` | `str` (1–256) | *(required)* | Intended audience |
| `exp` | `int` (>0) | *(required)* | Expiration timestamp (UNIX epoch seconds) |
| `iat` | `int` (≥0) | *(required)* | Issued-at timestamp |
| `nbf` | `int \| None` | `None` | Not-before timestamp |
| `scopes` | `list[str]` | `[]` | Scope strings (e.g., `["read:users"]`) |
| `tenant_id` | `str` (max 64) | `""` | CENF multi-tenant identifier |
| `principal_id` | `str` (max 64) | `""` | CENF principal identifier |

**Security:** TokenClaims NEVER carries the raw token string. `scopes` are NOT encrypted — callers must not log sensitive scopes in production.

---

### `JWKSKey`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `kid` | `str` (1+) | *(required)* | Key ID for matching the token header |
| `kty` | `str` (1+) | `"RSA"` | Key type |
| `alg` | `str` (1+) | `"RS256"` | Algorithm |
| `n` | `str` | `""` | RSA modulus (base64url) |
| `e` | `str` | `"AQAB"` | RSA exponent (base64url) |

---

### `AuthConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `issuer` | `str` (max 512) | `""` | Expected `iss` claim value |
| `audience` | `str` (max 256) | `""` | Expected `aud` claim value |
| `jwks_url` | `str` (max 2048) | `""` | JWKS endpoint URL for RS256 verification |
| `algorithms` | `list[str]` (min 1) | `["HS256"]` | Allowed signing algorithms |
| `token_leeway` | `int` (0–300) | `60` | Clock skew tolerance in seconds |

## Adapters

| Adapter | Algorithm | Use Case |
|---------|-----------|----------|
| `JwtAuthAdapter` | HS256 (symmetric) | Production — validates against shared secret from SecretManager |
| `StaticAuthAdapter` | None (static claims) | Testing — returns pre-configured claims without real token validation |

## Usage Example

```python
from core_infrastructure.auth.adapters.jwt_auth_adapter import JwtAuthAdapter

# Bootstrap
auth = JwtAuthAdapter(config_manager=config, logger_manager=logger, secret_manager=secrets)

# Validate a token from Authorization header
token = "eyJhbGciOiJIUzI1NiIs..."
try:
    claims = await auth.validate_token(token)
    # On success, tenant_id and principal_id are set in contextvars
    # → LoggerManager auto-injects them into every log record
    # → DatabaseManager uses tenant_id for multi-tenant isolation

    logger.info("Authenticated", sub=claims.sub)

    # Check scopes for authorization
    if auth.validate_scopes(claims, required=["read:users", "write:reports"]):
        logger.info("Authorized for users + reports")
    else:
        raise AuthError("Insufficient scopes")

except AuthError as e:
    logger.error("Auth failed", exc=e, reason=str(e))

# Read claims from an already-validated token (no re-validation)
claims = await auth.get_claims(token)

# Periodic JWKS refresh (e.g., in a background task)
await auth.refresh_jwks()
```

### Testing with StaticAuthAdapter

```python
from core_infrastructure.auth.adapters.static_auth_adapter import StaticAuthAdapter
from core_infrastructure.auth.models import TokenClaims

auth = StaticAuthAdapter(
    config_manager=config,
    logger_manager=logger,
    static_claims=TokenClaims(
        sub="test-user",
        iss="https://auth.cenf.tech",
        aud="cenf-test",
        exp=9999999999,
        iat=0,
        scopes=["read:all"],
        tenant_id="cntrs",
        principal_id="usr-test-001",
    ),
)

claims = await auth.validate_token("any-string")
assert claims.tenant_id == "cntrs"
```

## @ai-directive

- **Set `tenant_id` and `principal_id` contextvars after validation.** These are consumed by LoggerManager (auto-injected into logs), DatabaseManager (multi-tenant queries), and FeatureFlagManager (tenant-scoped flags).
- All `validate_token()` methods MUST be async — token validation may involve network I/O (JWKS refresh).
- **NEVER cache validation results indefinitely.** Tokens can be revoked.
- NEVER accept tokens without full validation. Expired tokens MUST raise `AuthError`. Wrong signature MUST raise `AuthError`.
- NEVER add a `raw_token` field to `TokenClaims`. The token itself is consumed by `validate_token()` and discarded.

## Related

- [SecretManager](secret-manager.md) — retrieves signing keys for HS256 validation
- [LoggerManager](logger-manager.md) — auto-injects tenant_id from validated claims
- [DatabaseManager](database-manager.md) — uses tenant_id for row-level multi-tenant isolation
- [ErrorHandlingManager](error-handling-manager.md) — `AuthError` is classified as AUTH by the taxonomy
