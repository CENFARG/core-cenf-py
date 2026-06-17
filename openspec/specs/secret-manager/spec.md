---
Spec_ID: SPEC_M03
Title: SecretManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [secrets, cryptography, fernet, zero-trust]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M03: SecretManager

## Purpose

Provide secure credential management with Zero-Trust principles. Supports encrypted local storage (cryptography Fernet) and Vault integration. Implements TTL cache and masked `__repr__`.

**Does NOT**: Persist secrets in permanent env vars, list all secrets, log raw secret values.

## Python Protocol

```python
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class SecretManager(Protocol):
    """@ai-directive: NEVER log the return value of get_secret(). Use SecretValue.get_masked() for display."""

    async def get_secret(self, key: str) -> str:
        """Retrieve a decrypted secret by its key."""
        ...

    def invalidate_cache(self, key: str | None = None) -> None:
        """Invalidate cached secret entries."""
        ...

    async def rotate_secret(self, key: str, new_value: str) -> None:
        """Store a new value for the given key and invalidate its cache."""
        ...

    def get_json_schema(self) -> dict[str, Any]:
        """Return JSON Schema describing SecretConfig."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class SecretSettings(BaseModel):
    backend: Literal["encrypted_file", "vault", "memory"] = Field(default="encrypted_file")
    vault_url: str | None = Field(default=None, min_length=1)
    vault_token_path: str | None = Field(default=None)
    ttl_seconds: int = Field(default=300, ge=60, le=3600)
    cache_max_size: int = Field(default=100, ge=10)
    encryption_algorithm: Literal["fernet"] = Field(default="fernet")
    encrypted_file_path: str | None = Field(default=None)
```

## Gherkin Scenarios

### Scenario: Get secret from cache

- GIVEN a secret "db_password" is cached with TTL=300s
- WHEN `get_secret("db_password")` is called within TTL
- THEN it returns the cached value without hitting the backend

### Scenario: Cache miss fetches from backend

- GIVEN secret "api_key" is not cached
- WHEN `get_secret("api_key")` is called
- THEN it fetches from backend, caches the value, and returns it

### Scenario: Secret rotation invalidates cache

- GIVEN secret "db_password" is cached with old value
- WHEN `rotate_secret("db_password", "new-value")` is called
- THEN the cache for "db_password" is invalidated
- AND the next `get_secret("db_password")` fetches the new value

### Scenario: Masked __repr__

- GIVEN a SecretValue wrapping "super-secret-key"
- WHEN `repr(secret_value)` is called
- THEN it returns `"SecretValue(****ret-key)"` (masked)

### Scenario: Key not found raises ValidationError

- WHEN `get_secret("nonexistent_key")` is called
- THEN it raises `ValidationError`

### Scenario: Backend unreachable raises TransientError

- GIVEN the Vault backend is down
- WHEN `get_secret("any_key")` is called
- THEN it raises `TransientError` (backend unreachable)

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Key not found | VALIDATION | Re-raise immediately |
| Backend unreachable | TRANSIENT | Retry with backoff |
| Token expired (Vault) | AUTH | Refresh token, retry |
| Misconfiguration | PERMANENT | Fail bootstrap |

## RED Metrics

- `cenf.secret.get_total` (counter)
- `cenf.secret.errors_total{error_type="..."}` (counter)
- `cenf.secret.get_duration_seconds` (histogram)

## Test Requirements

- **Unit**: `InMemorySecretAdapter` — dict-based with TTL simulation.
- **Integration**: `EncryptedFileAdapter` with temp encrypted files using Fernet.
- **E2E**: Secret rotation end-to-end, verify no secrets in logs.

## Do's and Don'ts

**Do**:
- Implement TTL cache with configurable expiration
- Mask secrets in `__repr__` and all log output
- Support encrypted local file storage (Fernet) as default
- Integrate with IAM Roles (Workload Identity) for Vault

**Don't**:
- Persist secrets in permanent env vars
- List all secrets (no enumeration endpoint)
- Log raw secret values at any level
