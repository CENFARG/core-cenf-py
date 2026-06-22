---
sidebar_position: 3
---

# SecretManager (M03)

Encrypted credential storage with automatic `__repr__` masking. Every infrastructure manager that needs secrets (auth signing keys, DB connection strings, API tokens) reads them through this interface.

## Protocol

`SecretManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.secrets.ports`.

### `async get_secret(key: str) → str`

Retrieve a decrypted secret by its key.

```python
async def get_secret(self, key: str) -> str: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `key` | `str` | The secret key name (e.g., `"db_password"`) |

**Returns:** The decrypted secret value (raw string).

**Raises:**
- `ValidationError` — key not found or is empty
- `PermanentError` — storage backend corrupted or unreachable

**Security:** The returned string MUST NOT be logged or serialized without masking. Use `SecretValue(value).get_masked()` for safe display.

---

### `async rotate_secret(key: str, new_value: str) → None`

Store a new value for the given key and invalidate its cache.

```python
async def rotate_secret(self, key: str, new_value: str) -> None: ...
```

The old value is immediately evicted from cache. Raises `PermanentError` if the write to backing storage fails.

---

### `invalidate_cache(key: str | None = None) → None`

Invalidate cached secret entries.

```python
def invalidate_cache(self, key: str | None = None) -> None: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `key` | `str \| None` | Specific key to invalidate, or `None` to invalidate **all** |

Safe to call concurrently. Called automatically after `rotate_secret()`.

---

### `get_json_schema() → dict[str, Any]`

Return the JSON Schema describing `SecretConfig`. Used by LLM agents for tool discovery.

## Models

### `SecretRef`

**File:** `core_infrastructure.secrets.models`

A lightweight reference to a secret by key and namespace — used when a manager needs to declare which secret it depends on without retrieving the value at construction time.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `key` | `str` (1–256) | *(required)* | The secret key name |
| `namespace` | `str` (1–128) | `"default"` | Optional namespace for multi-tenant secret isolation |

---

### `SecretValue`

A secret value wrapper that **ALWAYS masks itself in `__repr__`**. The raw value is accessible **only** via `.value`.

```python
class SecretValue(BaseModel):
    value: str  # NEVER log or serialize this field

    def __repr__(self) -> str: ...   # → "SecretValue(value='*****2345')"
    def __str__(self) -> str: ...    # → same as __repr__
    def get_masked(self, visible_chars: int = 4) -> str: ...  # → "*****2345"
```

| Field | Type | Description |
|-------|------|-------------|
| `value` | `str` | The raw secret. **NEVER log or serialize.** |

| Method | Returns | Description |
|--------|---------|-------------|
| `get_masked(visible_chars=4)` | `str` | Masked version safe for logs (e.g., `"*****2345"`) |

**Edge cases:**
- Empty value → `get_masked()` returns `"<empty>"`
- Value shorter than `visible_chars` → returns all `*`

---

### `SecretConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `cache_ttl_seconds` | `int` (1–86400) | `300` | TTL before cached secrets are re-read |
| `fernet_key` | `str` (0–256) | `""` | Fernet symmetric encryption key (base64-encoded) |
| `max_cache_size` | `int` (10–10000) | `100` | Maximum cached secret entries |
| `encryption_algorithm` | `str` (regex: `^fernet$`) | `"fernet"` | Only `"fernet"` supported currently |

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `EncryptedSecretAdapter` | Fernet-encrypted file storage | Production — secrets encrypted at rest with symmetric key |
| `InMemorySecretAdapter` | Python dict | Testing — no encryption, values stored in memory |

## Usage Example

```python
from core_infrastructure.secrets.adapters.encrypted_secret_adapter import EncryptedSecretAdapter
from core_infrastructure.secrets.models import SecretValue

# Bootstrap
secrets = EncryptedSecretAdapter(config_manager=config, logger_manager=logger)

# Retrieve a secret
db_password = await secrets.get_secret("db_password")

# NEVER log the raw value:
# logger.info(f"Password: {db_password}")  ← WRONG

# ALWAYS mask for display:
sv = SecretValue(value=db_password)
logger.info("Using DB credentials", password=sv.get_masked())  # logs "*****2345"

# Rotate a secret (writes new value + invalidates cache)
await secrets.rotate_secret("api_key", "new-secret-value")

# Invalidate specific cache entry
secrets.invalidate_cache("db_password")

# Invalidate ALL cached secrets
secrets.invalidate_cache()

# LLM agent discovery
schema = secrets.get_json_schema()
```

## @ai-directive

- **SecretValue.__repr__ is auto-masked. Never log raw `.value`.**
- NEVER add a method that returns raw secrets without masking warnings.
- All secret adapters MUST mask secrets in `__repr__` and logs.
- The `get_secret()` return value is a raw `str` — callers are responsible for NOT logging or displaying it.

## Related

- [LoggerManager](logger-manager.md) — use `logger.mask()` before logging any secret
- [ConfigManager](config-manager.md) — reads `fernet_key` from config
- [AuthManager](auth-manager.md) — retrieves signing keys via SecretManager
- [DatabaseManager](database-manager.md) — retrieves `dsn` connection string
