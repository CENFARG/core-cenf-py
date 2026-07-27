# Design: M20 UpdateManager — Production Adapters

## Technical Approach

Five adapters implementing the `UpdateManager` Protocol (ports.py), each platform-native. Reuse existing `http_update_adapter_helpers.py` for crypto (Ed25519, SHA-256) and platform detection. Each adapter ≤250 lines per CENF rule — oversized ones get a `_helpers.py` sibling. Hybrid persistence (openspec + engram).

## Architecture Decisions

### Decision: Hash Algorithm — Dual SHA-256 / SHA-512

**Choice**: Compute BOTH hashes from downloaded bytes. Port contract requires SHA-256 (64 hex chars). Electron-updater's `latest.yml` uses SHA-512 (128 hex chars). HttpUpdateAdapter verifies both; `artifact.hash()` exposes SHA-256 for port compatibility.

**Alternatives**: Force SHA-512 into port protocol (breaks existing `InMemoryUpdateAdapter` contracts). Only SHA-256 (spec says SHA-512 for electron-updater).

**Rationale**: Zero protocol breakage + full spec compliance. Other adapters use SHA-256 only.

### Decision: Amend Existing HttpUpdateAdapter

**Choice**: Add electron-updater lifecycle to existing 238-line `http_update_adapter.py`. `apply_update` → `electron.quitAndInstall()`, `rollback` → restore backup. `get_current_version` → read `package.json`. Backward-compatible: `ExternalAPIManager` still used for `check_for_updates`.

**Alternatives**: New `ElectronUpdateAdapter` class (duplication of 80% code). Full rewrite (risk of breaking dependents).

**Rationale**: Existing adapter already has 4/5 methods — only amend the two `raise NotImplementedError` stubs.

### Decision: Async Subprocess for PipUpdateAdapter

**Choice**: `asyncio.create_subprocess_exec("pip", "install", ...)` with `PIPE` capture — never `subprocess.run()`. SHA resolved from GitHub API before install; `update_state.json` written synchronously via `aiofiles`.

**Alternatives**: `subprocess.run()` in thread pool (blocks event loop). Shell=True (injection risk).

**Rationale**: Event loop safety + zero shell injection surface.

### Decision: Adapter-Specific Rollback Model

| Adapter | Strategy | Mechanism |
|---------|----------|-----------|
| HttpUpdateAdapter | electron-updater built-in | Restores AppImage backup |
| GitHubReleaseAdapter | File-level backup | Backup current install → restore on failure |
| WebUpdateAdapter | SW cache isolation | Previous SW cache retained until next activation |
| PipUpdateAdapter | SHA reinstall | `update_state.json` → `pip install git+...@{previous_sha}` |
| AndroidUpdateAdapter | PermanentError | Android OS prohibits downgrade via PackageInstaller |

## Data Flow

```
                           ┌──────────────────┐
                           │   UpdateManager    │
                           │    (Protocol)      │
                           └────┬──────────┬───┘
                                │          │
              ┌─────────────────┤    ┌─────┴──────────┐
              │                 │    │  InMemoryUpdate │
              │   ┌─────────────┼────┤  (test only)    │
              │   │             │    └────────────────┘
         ┌────┴───┴────┐  ┌────┴────┐  ┌────┴────┐  ┌────┴──────┐  ┌────┴───────┐
         │ HttpUpdate  │  │ GitHub  │  │  Web    │  │  Pip     │  │  Android  │
         │ (Electron)  │  │ Release │  │ (SPA)   │  │ (CLI)    │  │ (Play/SL)│
         └──────┬──────┘  └────┬────┘  └────┬────┘  └────┬─────┘  └────┬───────┘
                │              │             │            │             │
         Electron-updater  GitHub API    Service Worker  subprocess  PackageInstaller
         quitAndInstall    Releases       skipWaiting     pip install  / Play Core
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/.../update/adapters/http_update_adapter.py` | Modify | Replace NotImplementedError stubs with electron-updater calls, add package.json reader |
| `src/.../update/adapters/http_update_adapter_helpers.py` | Modify | Add `compute_shasum()` for dual SHA-256/SHA-512 |
| `src/.../update/adapters/github_release_adapter.py` | Create | GitHub Releases API adapter with 5-min caching |
| `src/.../update/adapters/github_release_adapter_helpers.py` | Create | GH API pagination, tag→channel filter, helpers |
| `src/.../update/adapters/web_update_adapter.py` | Create | SPA/PWA SW lifecycle adapter |
| `src/.../update/adapters/pip_update_adapter.py` | Create | CLI `pip install` via subprocess |
| `src/.../update/adapters/pip_update_adapter_helpers.py` | Create | SHA resolution, update_state.json I/O |
| `src/.../update/adapters/android_update_adapter.py` | Create | Play Core / PackageInstaller dual-path |

## Interfaces / Contracts

All adapters reference existing Protocol only — no new ports. Error types follow `common/errors.py`:

```python
# Every adapter raises:
from core_infrastructure.common.errors import (
    AuthError,      # signature/hash mismatch
    TransientError, # network timeout, rate limit
    PermanentError, # no artifact, no rollback state
)
```

Existing `UpdateConfig.public_key` reused for Ed25519 adapters (HttpUpdateAdapter, GitHubReleaseAdapter). WebUpdateAdapter has no signing. PipUpdateAdapter uses SHA commit ID (not Ed25519).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Each adapter method in isolation | Mock ExternalAPIManager / GH API / subprocess. Use existing InMemoryUpdateAdapter contract compliance suite |
| Integration | PipUpdateAdapter `check → download → apply → rollback` | Fixture with real `pip install git+` in isolated venv |
| Integration | HttpUpdateAdapter signature verification | Pre-signed test artifacts, tampered bytes |
| E2E | WebUpdateAdapter SW `skipWaiting + reload` | Playwright/custom browser test with version header injection |
| E2E | AndroidUpdateAdapter PackageInstaller | Emulator test with test APK |

## Threat Matrix

| Boundary | Applicability | Design response |
|----------|---------------|----------------|
| Documentation-like paths | **Applicable** — PipUpdateAdapter constructs `git+https://...@{sha}` URL | SHA is validated before URL construction. Input is `app_id` (mapped to known org/repo), not user string |
| Git repository selection | **Applicable** — GitHubReleaseAdapter maps `app_id` to `org/repo` | Mapping is hardcoded in adapter config, not runtime-supplied |
| Commit state | **N/A** — no local git operations | — |
| Push state | **N/A** | — |
| PR commands | **N/A** | — |

**PipUpdateAdapter subprocess guard**: `app_id → (org, repo)` is a frozen dict in config, never from user input. `subprocess_exec` receives `"git+https://github.com/{org}/{repo}@{sha}"` — sha is validated (40 hex chars) before exec.

## Migration / Rollout

No migration required. New adapters are additive — existing `InMemoryUpdateAdapter` and `HttpUpdateAdapter` continue working unchanged. Each adapter is importable only when its dependencies are installed (lazy import pattern per AGENTS.md).

## Open Questions

- [ ] HttpUpdateAdapter: Should `get_current_version` read `package.json` always, or fall back to `UpdateConfig.current_version`? **Recommend**: try `package.json` first, fall back to config.
- [ ] WebUpdateAdapter: requires HTTP interceptor (aiohttp middleware?) — how to register in the project's web framework? **Deferred to implementation**: adapter exposes a middleware factory.
- [ ] GitHubReleaseAdapter: GitHub App vs PAT authentication — config structure not yet defined for per-adapter auth. **Recommend**: inject `ExternalAPIManager` with pre-configured auth.
