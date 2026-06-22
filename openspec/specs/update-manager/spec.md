---
Spec_ID: SPEC_M20
Title: UpdateManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [update, tuf, signature, rollback, auto-update, desktop]
Dependency_Hashes: []
Last_Updated: "2026-06-21"
---

# SPEC_M20: UpdateManager

## Purpose

Provide secure desktop app auto-update with TUF-inspired pattern. Verifies metadata signatures and artifact hashes before installation, supports rollback to previous known-good version, and works across platforms (Windows, macOS, Linux). PyUpdater is explicitly discarded (archived 2026).

**Does NOT**: Download without verifying signature, use PyUpdater, execute installers with elevated privileges without user control, mix update logic with business logic.

## Python Protocol

```python
from __future__ import annotations
from typing import Protocol, Literal, Mapping, Any, runtime_checkable

Channel = Literal["stable", "beta", "canary"]


@runtime_checkable
class UpdateArtifact(Protocol):
    """A downloadable update package for a specific platform."""

    def url(self) -> str: ...
    def platform(self) -> str: ...
    def arch(self) -> str: ...
    def kind(self) -> str: ...
    def hash(self) -> str: ...
    def signature(self) -> str | None: ...
    def size_bytes(self) -> int: ...


@runtime_checkable
class AvailableRelease(Protocol):
    """Metadata describing an available update release."""

    def version(self) -> str: ...
    def channel(self) -> Channel: ...
    def artifacts(self) -> list[UpdateArtifact]: ...
    def metadata(self) -> Mapping[str, Any]: ...
    def release_notes_url(self) -> str | None: ...


@runtime_checkable
class UpdateResult(Protocol):
    """Result of an update application attempt."""

    def success(self) -> bool: ...
    def new_version(self) -> str | None: ...
    def error(self) -> str | None: ...
    def requires_restart(self) -> bool: ...


@runtime_checkable
class UpdateManager(Protocol):
    """@ai-directive: Use UpdateManager to discover and apply desktop app updates.
    Always verify signatures and hashes before installing. Never install unverified artifacts.
    """

    async def get_current_version(self, *, app_id: str) -> str:
        """Return the currently installed version for an app (SemVer)."""
        ...

    async def check_for_updates(
        self,
        *,
        app_id: str,
        channel: Channel = "stable",
    ) -> AvailableRelease | None:
        """Query the remote update service for the latest compatible release."""
        ...

    async def download_update(
        self,
        *,
        app_id: str,
        release: AvailableRelease,
    ) -> UpdateArtifact:
        """Download and verify the appropriate artifact for the current platform.
        MUST verify hash and signature before returning.
        """
        ...

    async def apply_update(
        self,
        *,
        app_id: str,
        artifact: UpdateArtifact,
    ) -> UpdateResult:
        """Apply the update using platform-specific mechanisms, supporting rollback.
        """
        ...

    async def rollback(self, *, app_id: str) -> UpdateResult:
        """Rollback to the previous known-good version."""
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract for agent discovery."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class ReleaseMetadata(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    version: str = Field(pattern=r"^\d+\.\d+\.\d+")
    channel: Literal["stable", "beta", "canary"]
    release_notes_url: str | None = Field(default=None)
    published_at: float = Field(gt=0)
    min_supported_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+")


class ArtifactMetadata(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    url: str = Field(min_length=1)
    platform: Literal["windows", "macos", "linux"]
    arch: Literal["x64", "arm64"]
    kind: Literal["installer", "archive", "delta"]
    hash: str = Field(min_length=64)  # SHA-256 hex
    signature: str | None = Field(default=None)
    size_bytes: int = Field(gt=0)


class UpdateSettings(BaseModel):
    model_config = {"extra": "forbid"}
    update_endpoint: str = Field(min_length=1)
    public_key_path: str | None = Field(default=None)
    public_key_pem: str | None = Field(default=None)
    check_interval_seconds: int = Field(default=3600, ge=300)
    auto_download: bool = Field(default=False)
    auto_install: bool = Field(default=False)
```

## Gherkin Scenarios

### Scenario: Check for updates — update available

- GIVEN current version is "1.0.0" and remote has release "1.1.0" on stable channel
- WHEN `check_for_updates(app_id="cenf-desktop", channel="stable")` is called
- THEN it returns `AvailableRelease` with `version() == "1.1.0"`
- AND `artifacts()` contains at least one artifact for current platform

### Scenario: Check for updates — no update needed

- GIVEN current version is "1.1.0" and remote latest is also "1.1.0"
- WHEN `check_for_updates(app_id="cenf-desktop", channel="stable")` is called
- THEN it returns `None`

### Scenario: Download verifies hash and signature

- GIVEN an AvailableRelease with an artifact for current platform
- WHEN `download_update(app_id="cenf-desktop", release=release)` is called
- THEN it downloads the artifact from the URL
- AND verifies SHA-256 hash matches `artifact.hash()`
- AND verifies digital signature using configured public key
- AND returns the verified `UpdateArtifact`

### Scenario: Download fails on signature mismatch

- GIVEN an artifact with a valid hash but tampered signature
- WHEN `download_update(app_id="cenf-desktop", release=release)` is called
- THEN it raises `AuthError` with reason `"signature_mismatch"`
- AND the downloaded file is deleted (no partial artifacts remain)

### Scenario: Apply update with rollback on failure

- GIVEN a verified UpdateArtifact is ready
- WHEN `apply_update(app_id="cenf-desktop", artifact=artifact)` is called
- AND the installation fails (e.g., health check post-install fails)
- THEN it returns `UpdateResult` with `success() == False`
- AND `rollback()` is triggered automatically to restore previous version
- AND previous version is marked as active

### Scenario: Manual rollback to previous version

- GIVEN version "1.1.0" is installed and "1.0.0" is stored as previous known-good
- WHEN `rollback(app_id="cenf-desktop")` is called
- THEN it restores version "1.0.0"
- AND returns `UpdateResult` with `success() == True` and `new_version() == "1.0.0"`

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Signature mismatch | AUTH | Abort download, delete partial, alert |
| Hash mismatch | AUTH | Abort download, delete partial, alert |
| Update endpoint unreachable | TRANSIENT | Retry with backoff |
| Insufficient disk space | PERMANENT | Return error, notify user |
| Installation failure | PERMANENT | Trigger automatic rollback |
| Rollback failure | PERMANENT | Alert critical, mark degraded |

## RED Metrics

- `cenf.update.check_total` (counter)
- `cenf.update.apply_total` (counter, labels: `result=success|failure|rollback`)
- `cenf.update.download_duration_seconds` (histogram)
- `cenf.update.install_duration_seconds` (histogram)
- `cenf.update.errors_total{reason="..."}` (counter)
- `cenf.update.rollback_total` (counter)

## Test Requirements

- **Unit**: `InMemoryUpdateAdapter` — mock release metadata, simulated download with hash/signature verification. Tests all check, download, and apply paths including rollback.
- **Integration**: `TufInspiredAdapter` with local test server serving signed metadata and artifacts.
- **E2E**: Full update cycle: check → download → verify → apply → health check → success. Plus failure path: apply → fail → auto-rollback → verify previous version active.

## Do's and Don'ts

**Do**:
- Verify signature before installing any artifact
- Support rollback to previous known-good version
- Install per-user when possible to avoid UAC prompts
- Use HTTPS for all update endpoint communication
- Register update events as OTel metrics

**Don't**:
- Download artifacts without verifying signature and hash
- Use PyUpdater (archived, unmaintained)
- Execute installers with elevated privileges without user control
- Mix update logic with business logic
- Leave partial downloaded artifacts on disk after failure
