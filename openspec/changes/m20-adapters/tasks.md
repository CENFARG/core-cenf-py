# Tasks: M20 UpdateManager — Production Adapters

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 1500–2000 (5 adapters + tests + exports) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: Http → PR 2: Pip → PR 3: Web → PR 4: GitHubRelease → PR 5: Android |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | HttpUpdateAdapter electron lifecycle | PR 1 | `pytest tests/unit/update/test_http_adapter.py -v` | N/A — requires Electron runtime (deferred per design) | Revert http_update_adapter.py + helpers |
| 2 | PipUpdateAdapter subprocess pip install | PR 2 | `pytest tests/unit/update/test_pip_adapter.py -v` | N/A — requires GH token for real SHA resolution | Revert pip_update_adapter.py + helpers |
| 3 | WebUpdateAdapter SW skipWaiting | PR 3 | `pytest tests/unit/update/test_web_adapter.py -v` | N/A — requires SW browser env | Revert web_update_adapter.py |
| 4 | GitHubReleaseAdapter GH API + cache | PR 4 | `pytest tests/unit/update/test_gh_release_adapter.py -v` | N/A — requires GH API token | Revert github_release_adapter.py + helpers |
| 5 | AndroidUpdateAdapter Play/PackageInstaller | PR 5 | `pytest tests/unit/update/test_android_adapter.py -v` | N/A — requires Android emulator | Revert android_update_adapter.py |

## Phase 1: Foundation — Shared Helpers & Exports

- [ ] 1.1 Add `compute_shasum()` to `http_update_adapter_helpers.py` (SHA-256 + SHA-512 dual)
- [ ] 1.2 Register all 5 adapters in `adapters/__init__.py`
- [ ] 1.3 Add lazy imports in top-level `__init__.py` (try/except ImportError → None)

## Phase 2: A1 — HttpUpdateAdapter (Electron Desktop)

- [ ] 2.1 RED: test `apply_update` calls `electron.quitAndInstall()`
- [ ] 2.2 GREEN: implement electron-updater lifecycle in `apply_update`
- [ ] 2.3 RED: test `rollback` restores AppImage backup
- [ ] 2.4 GREEN: implement rollback — backup restore
- [ ] 2.5 RED: test `get_current_version` reads package.json then fallback config
- [ ] 2.6 GREEN: implement `get_current_version` — try `package.json` → `UpdateConfig`
- [ ] 2.7 REFACTOR: verify ≤250 lines, extract logic if oversized

## Phase 3: A4 — PipUpdateAdapter (CLI Git-SHA)

- [ ] 3.1 RED: test `check_for_updates` resolves HEAD SHA via GitHub API
- [ ] 3.2 GREEN: implement SHA resolution in `pip_update_adapter_helpers.py`
- [ ] 3.3 RED: test `apply_update` writes `update_state.json` + pip install @SHA
- [ ] 3.4 GREEN: implement `asyncio.create_subprocess_exec("pip", "install", ...)`
- [ ] 3.5 RED: test subprocess guard — frozen org/repo dict, SHA validated 40 hex (threat)
- [ ] 3.6 GREEN: implement guard — frozen mapping, SHA hex validation before URL
- [ ] 3.7 RED: test `rollback` reinstates previous SHA from `update_state.json`
- [ ] 3.8 GREEN: implement rollback — read state, reinstall previous SHA
- [ ] 3.9 REFACTOR: verify async subprocess only, zero shell injection surface

## Phase 4: A3 — WebUpdateAdapter (SPA/PWA)

- [ ] 4.1 RED: test `check_for_updates` compares `x-client-version` header
- [ ] 4.2 GREEN: implement header comparison against current version
- [ ] 4.3 RED: test `apply_update` posts `{type: 'SKIP_WAITING'}` + `reload(true)`
- [ ] 4.4 GREEN: implement SW lifecycle — postMessage + location.reload
- [ ] 4.5 RED: test rollback — SW cache isolated (no-op)
- [ ] 4.6 GREEN: implement rollback — no-op with cache isolation comment
- [ ] 4.7 REFACTOR: expose middleware factory for web framework integration

## Phase 5: A2 — GitHubReleaseAdapter (Desktop via GH)

- [ ] 5.1 RED: test `check_for_updates` parses GH release by tag-channel suffix
- [ ] 5.2 GREEN: implement GH API pagination + tag→channel filter in helpers
- [ ] 5.3 RED: test rate-limit 403 → cached release fallback + TransientError
- [ ] 5.4 GREEN: implement 5-min TTL cache
- [ ] 5.5 RED: test hardcoded `app_id→org/repo` mapping (threat)
- [ ] 5.6 GREEN: implement frozen mapping config, never from user input
- [ ] 5.7 RED: test `download_update` selects platform artifact
- [ ] 5.8 GREEN: implement artifact selection + download via ExternalAPIManager

## Phase 6: A5 — AndroidUpdateAdapter (Play Core + PackageInstaller)

- [ ] 6.1 RED: test Play Core flexible update path (detected install source)
- [ ] 6.2 GREEN: implement Play Core In-App Updates API for Play Store builds
- [ ] 6.3 RED: test self-hosted APK via `PackageInstaller.Session(MODE_FULL_INSTALL)`
- [ ] 6.4 GREEN: implement PackageInstaller — `openWrite()` + `commit()`
- [ ] 6.5 RED: test `rollback` raises `PermanentError` with migration hint
- [ ] 6.6 GREEN: implement rollback → `PermanentError("Android OS prohibits downgrade")`
- [ ] 6.7 REFACTOR: verify runtime install-source detection

## Phase 7: Registration & Docs

- [ ] 7.1 Update AGENTS.md M20 row with all 5 production adapters
- [ ] 7.2 Update `tests/unit/update/test_exports.py` with new adapter symbols
- [ ] 7.3 Update `llms.txt` and `docs/INFORME_TECNICO.md` adapter tables
