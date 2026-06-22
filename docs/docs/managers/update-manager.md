---
sidebar_position: 20
---

# UpdateManager (M20)

Desktop auto-update with TUF-inspired verification. Discovers, downloads, and applies application updates with Ed25519 digital signature + SHA-256 hash verification. Supports SemVer comparison, update channels (stable/beta/canary), and automatic rollback to the last known-good version. **Always verify signatures and hashes before installing — never install unverified artifacts.**

## Protocol

`UpdateManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.update.ports`.

### Channel Type

```python
Channel = Literal["stable", "beta", "canary"]
```

---

### `async get_current_version(*, app_id) → str`

Return the currently installed version for an app as a SemVer string.

```python
async def get_current_version(self, *, app_id: str) -> str: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `app_id` | `str` | Application identifier (e.g., `"cenf-desktop"`) |

**Returns:** SemVer string (e.g., `"1.0.0"`).

---

### `async check_for_updates(*, app_id, channel) → AvailableRelease | None`

Query the remote update service for the latest compatible release. Compares current version against latest in the specified channel. Returns `None` if up-to-date.

```python
async def check_for_updates(
    self,
    *,
    app_id: str,
    channel: Channel = "stable",
) -> AvailableRelease | None: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `channel` | `Channel` | Update channel (default `"stable"`) |

**Raises:** `TransientError` if the remote endpoint is unreachable.

---

### `async download_update(*, app_id, release) → UpdateArtifact`

Download and verify the appropriate artifact for the current platform. Selects the correct artifact for current platform/architecture, downloads it, and verifies BOTH SHA-256 hash AND Ed25519 signature before returning.

```python
async def download_update(
    self,
    *,
    app_id: str,
    release: AvailableRelease,
) -> UpdateArtifact: ...
```

**Raises:** `AuthError` if hash or signature verification fails. `PermanentError` if no artifact matches the current platform.

---

### `async apply_update(*, app_id, artifact) → UpdateResult`

Apply the update using platform-specific mechanisms. Saves the current version as rollback state before installing. If installation fails and rollback is enabled, automatically restores the previous version.

```python
async def apply_update(
    self,
    *,
    app_id: str,
    artifact: UpdateArtifact,
) -> UpdateResult: ...
```

---

### `async rollback(*, app_id) → UpdateResult`

Rollback to the previous known-good version. Restores the previously installed version from rollback state and verifies the restored hash.

```python
async def rollback(self, *, app_id: str) -> UpdateResult: ...
```

**Raises:** `PermanentError` if no rollback state exists for the app.

---

### `get_json_schema() → dict[str, Any]` *(static)*

Return JSON Schema for agent discovery (AX).

---

## Models

**File:** `core_infrastructure.update.models`

### `UpdateConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `update_url` | `str` (1–2048) | required | Base URL of the update service endpoint |
| `public_key` | `str` (1–256) | required | Ed25519 public key (hex-encoded) for signature verification |
| `current_version` | `str` (1–64) | required | Currently installed SemVer version |
| `rollback_enabled` | `bool` | `True` | Whether automatic rollback on failure is enabled |

### `ReleaseMetadata`

Frozen model (`extra="forbid"`). SemVer validated with pattern `^\d+\.\d+\.\d+`.

| Field | Type | Description |
|-------|------|-------------|
| `version` | `str` (5–64) | SemVer version (e.g., `"1.1.0"`) |
| `channel` | `Channel` | Update channel |
| `release_notes_url` | `str` (1–2048) | URL to release notes |
| `artifacts` | `list[ArtifactMeta]` | Platform-specific artifacts |
| `min_version` | `str \| None` | Minimum version required to upgrade |

### `ArtifactMeta`

Frozen model (`extra="forbid"`).

| Field | Type | Description |
|-------|------|-------------|
| `url` | `str` (1–2048) | Download URL |
| `platform` | `"windows" \| "macos" \| "linux"` | Target platform |
| `arch` | `"x64" \| "arm64"` | Target CPU architecture |
| `kind` | `"installer" \| "archive" \| "delta"` | Artifact kind |
| `hash` | `str` (64–128) | SHA-256 hex digest |
| `signature` | `str \| None` | Ed25519 base64-encoded signature, or `None` |

### `RollbackState`

Frozen model (`extra="forbid"`).

| Field | Type | Description |
|-------|------|-------------|
| `previous_version` | `str` (1–64) | Previously installed SemVer version |
| `previous_hash` | `str` (64–128) | SHA-256 hex of previous artifact |
| `rollback_available` | `bool` | Whether rollback is currently possible |

---

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `HttpUpdateAdapter` | `ExternalAPIManager` + `cryptography` | Production — HTTP-based update check, Ed25519 verification, `packaging.version` for SemVer |
| `InMemoryUpdateAdapter` | In-memory dict | Testing — preconfigure releases, simulate download/apply/rollback |

**Verification flow:** `download_update()` uses `ExternalAPIManager` (M11) for resilient HTTP download, then verifies SHA-256 hash with `hashlib` and Ed25519 signature with the `cryptography` library. Partial downloads are discarded on failure. `apply_update()` uses `packaging.version.Version` for SemVer comparison.

---

## Usage Example

```python
from core_infrastructure.update.adapters.in_memory_update_adapter import (
    InMemoryUpdateAdapter,
)
from core_infrastructure.update.models import UpdateConfig, ArtifactMeta, ReleaseMetadata

# Testing: InMemoryUpdateAdapter
update_mgr = InMemoryUpdateAdapter(config=UpdateConfig(
    update_url="https://updates.cenf.tech",
    public_key="abcdef...",
    current_version="1.0.0",
    rollback_enabled=True,
))

# Check current version
current = await update_mgr.get_current_version(app_id="cenf-desktop")
# → "1.0.0"

# Pre-configure a release
release = ReleaseMetadata(
    version="1.1.0",
    channel="stable",
    release_notes_url="https://updates.cenf.tech/releases/1.1.0",
    artifacts=[
        ArtifactMeta(
            url="https://updates.cenf.tech/artifacts/cenf-1.1.0-x64.exe",
            platform="windows",
            arch="x64",
            kind="installer",
            hash="a" * 64,
            signature="sig_base64...",
        ),
    ],
)
update_mgr.set_available_release("cenf-desktop", release)

# Check for updates
update = await update_mgr.check_for_updates(
    app_id="cenf-desktop",
    channel="stable",
)
assert update is not None
assert update.version() == "1.1.0"

# Download and verify
artifact = await update_mgr.download_update(
    app_id="cenf-desktop",
    release=update,
)
assert artifact.platform() == "windows"
assert artifact.hash() == "a" * 64

# Apply update
result = await update_mgr.apply_update(
    app_id="cenf-desktop",
    artifact=artifact,
)
assert result.success() is True
assert result.new_version() == "1.1.0"

# Rollback on failure (if rollback_enabled)
rollback_result = await update_mgr.rollback(app_id="cenf-desktop")
assert rollback_result.success() is True
assert rollback_result.new_version() == "1.0.0"

# Up-to-date: no update available
update_mgr.set_available_release("cenf-desktop", None)
no_update = await update_mgr.check_for_updates(app_id="cenf-desktop")
# → None
```

---

## @ai-directive

> **Always verify signatures and hashes before installing. Never install unverified artifacts.** Use `rollback()` to recover from failed updates. SemVer comparison uses `packaging.version.Version`. Partial downloads are deleted on failure. `download_update()` MUST verify SHA-256 hash AND Ed25519 signature before returning. `apply_update()` MUST support rollback. Always delete partial downloads on failure.

## Related

- [ExternalAPIManager](external-api-manager.md) — used for resilient HTTP download of update artifacts
- [SecretManager](secret-manager.md) — supplies Ed25519 public key for signature verification
- [ConfigManager](config-manager.md) — supplies `update.update_url` and `update.current_version`
