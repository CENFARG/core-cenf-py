# Design: M18–M20 Managers (Permission, Licence, Update)

## Technical Approach

Add three new horizontal managers following the established core-cenf pattern: `ports.py` Protocol + `models.py` Pydantic boundary models + `adapters/` concrete implementations. All three plug into the existing DI/bootstrap system and emit RED metrics via `ObservabilityManager`. `PermissionManager` handles RBAC+ABAC authorization with agent delegation; `LicenceManager` validates cryptographically signed feature licenses; `UpdateManager` discovers, verifies, and applies desktop app updates.

## Architecture Decisions

| Decision | Options | Tradeoffs | Choice |
|----------|---------|-----------|--------|
| Policy engine | pycasbin / Oso / OpenFGA | Casbin: lightweight, Apache 2.0, RBAC+ABAC; Oso: requires Polar; OpenFGA: needs DB+service | **pycasbin** for MVP; OpenFGA adapter reserved for future ReBAC phase |
| Delegation persistence | In-memory TTL dict / persistent store | Memory: zero deps, fast; DB: survives restart | **In-memory TTL dict** in adapter; persistent extension via future task |
| License crypto format | RS256 JWT / custom signed blob | JWT: standard, python-jose already in tree; Custom: more control, more code | **RS256 JWT** with JWK from `SecretManager` |
| Grace period behavior | Hard deny / degraded mode | Hard deny: simpler; Grace: better enterprise UX | **Grace period** returning degraded `LicenseInfo` |
| Update trust model | TUF multi-role / single signing key | TUF: robust but complex; Single-key: simpler, manual rotation | **Single-role ECDSA** with manual per-release key rotation |
| Install privilege | Per-user / per-machine | Per-user: avoids UAC; Per-machine: wider deploy | **Per-user preferred**, fallback to admin service if needed |

## Data Flow

**Permission check:**
```
Caller → PermissionManager.check_permission()
  → CasbinPermissionAdapter
    → Pydantic PermissionRequest validation
    → pycasbin RBAC evaluation + temporary delegation policy lookup
    → ObservabilityManager audit counter
    → PermissionDecision
```

**License validation:**
```
Caller → LicenceManager.is_feature_enabled()
  → JwtLicenceAdapter
    → parse JWT claims → verify RS256 with cached JWK
    → compare expiry against grace_period_days
    → return bool or LicenseInfo
```

**Update cycle:**
```
Caller → UpdateManager.check_for_updates()
  → HttpUpdateAdapter
    → GET /{app}/latest via ExternalAPIManager
    → SemVer comparison → filter by channel + platform
    → download artifact → SHA256 + ECDSA verification
    → apply_update() with automatic rollback on failure
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/core_infrastructure/permission/ports.py` | Create | `PermissionManager`, `PermissionDecision`, `PrincipalType`, `Action` |
| `src/core_infrastructure/permission/models.py` | Create | `PermissionConfig`, `PermissionRequest`, `DelegationRequest`, `DelegationRecord` |
| `src/core_infrastructure/permission/adapters/__init__.py` | Create | Exports `CasbinPermissionAdapter`, `InMemoryPermissionAdapter` |
| `src/core_infrastructure/permission/adapters/casbin_permission_adapter.py` | Create | pycasbin engine, model.conf + policy.csv, TTL delegation policies |
| `src/core_infrastructure/permission/adapters/in_memory_permission_adapter.py` | Create | Dict-backed role→permissions test double |
| `src/core_infrastructure/licence/ports.py` | Create | `LicenceManager`, `LicenseInfo` |
| `src/core_infrastructure/licence/models.py` | Create | `LicenseClaims`, `LicenceConfig` |
| `src/core_infrastructure/licence/adapters/__init__.py` | Create | Exports `JwtLicenceAdapter`, `InMemoryLicenceAdapter` |
| `src/core_infrastructure/licence/adapters/jwt_licence_adapter.py` | Create | RS256 verification, JWK cache from `SecretManager`, grace-period logic |
| `src/core_infrastructure/licence/adapters/in_memory_licence_adapter.py` | Create | Configurable always-valid license for tests |
| `src/core_infrastructure/update/ports.py` | Create | `UpdateManager`, `AvailableRelease`, `UpdateArtifact`, `UpdateResult` |
| `src/core_infrastructure/update/models.py` | Create | `UpdateConfig`, `ReleaseMetadata`, `ArtifactMetadata` |
| `src/core_infrastructure/update/adapters/__init__.py` | Create | Exports `HttpUpdateAdapter`, `InMemoryUpdateAdapter` |
| `src/core_infrastructure/update/adapters/http_update_adapter.py` | Create | SemVer check, download via `ExternalAPIManager`, SHA256+ECDSA verify, rollback |
| `src/core_infrastructure/update/adapters/in_memory_update_adapter.py` | Create | Configurable releases, simulated apply/rollback |
| `tests/unit/permission/test_casbin_adapter.py` | Create | RBAC + delegation TTL integration tests |
| `tests/unit/permission/test_in_memory_adapter.py` | Create | Unit tests for test double |
| `tests/unit/licence/test_jwt_adapter.py` | Create | RS256 validation, grace period, revocation tests |
| `tests/unit/licence/test_in_memory_adapter.py` | Create | Feature flag and offline flow tests |
| `tests/unit/update/test_http_adapter.py` | Create | SemVer, hash/signature verification, rollback tests |
| `tests/unit/update/test_in_memory_adapter.py` | Create | Simulated update cycle tests |
| `pyproject.toml` | Modify | Add `casbin` dependency |

## Interfaces / Contracts

```python
# PermissionManager — ports.py excerpt
class PermissionDecision(Protocol):
    def is_allowed(self) -> bool: ...
    def reason(self) -> str: ...
    def attributes(self) -> Mapping[str, Any]: ...

class PermissionManager(Protocol):
    async def check_permission(
        self, *, tenant_id: str, principal_id: str, principal_type: PrincipalType,
        resource_type: str, resource_id: str, action: Action,
        context: Mapping[str, Any] | None = None,
    ) -> PermissionDecision: ...
    async def check_delegation(self, *, ...) -> PermissionDecision: ...
    async def list_effective_permissions(self, *, ...) -> list[Mapping[str, Any]]: ...

# LicenceManager — ports.py excerpt
class LicenseInfo(Protocol):
    def tenant_id(self) -> str: ...
    def tier(self) -> str: ...
    def features(self) -> Mapping[str, bool]: ...
    def is_valid(self) -> bool: ...
    def is_grace_period(self) -> bool: ...

class LicenceManager(Protocol):
    async def load_license_from_string(self, *, tenant_id: str, raw_license: str) -> LicenseInfo: ...
    async def is_feature_enabled(self, *, tenant_id: str, feature_key: str) -> bool: ...

# UpdateManager — ports.py excerpt
class UpdateManager(Protocol):
    async def check_for_updates(self, *, app_id: str, channel: Channel = "stable") -> AvailableRelease | None: ...
    async def download_update(self, *, app_id: str, release: AvailableRelease) -> UpdateArtifact: ...
    async def apply_update(self, *, app_id: str, artifact: UpdateArtifact) -> UpdateResult: ...
    async def rollback(self, *, app_id: str) -> UpdateResult: ...
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | In-memory adapters for all 3 managers | pytest, zero I/O, mock time for TTL/grace period |
| Integration | Casbin adapter with real `model.conf` + `policy.csv`; JWT adapter with real RSA key pair; HTTP adapter against local test server | pytest-asyncio, temp files/keys |
| E2E | Full delegation chain (Permission); offline activation flow (Licence); check → download → verify → apply → rollback (Update) | Full bootstrap, real HTTP server |

## Migration / Rollout

No migration required. These are net-new managers. Existing code is unaffected. `BootstrapOrchestrator` wiring will happen in a downstream `sdd-tasks` phase.

## Open Questions

- [ ] Should `PermissionManager` support a persistent delegation store (Redis/DB) beyond in-memory TTL?
- [ ] Should `UpdateManager` include a background polling loop or remain strictly on-demand?
- [ ] Should `LicenceManager` expose a `refresh_license()` online method for periodic re-validation?
