# M20 UpdateManager — Production Adapters Specification

## Purpose

Five production adapters implementing the `UpdateManager` protocol for desktop (HttpUpdateAdapter, GitHubReleaseAdapter), web (WebUpdateAdapter), CLI (PipUpdateAdapter), and Android (AndroidUpdateAdapter). Each implements all 5 protocol methods (`get_current_version`, `check_for_updates`, `download_update`, `apply_update`, `rollback`) with platform-specific mechanisms.

## ADDED Requirements

### Requirement: HttpUpdateAdapter — Electron Desktop Updates

Wraps electron-updater (NSIS/DMG targets). MUST verify Ed25519 signature AND SHA-512 hash before `apply_update`. MUST store downloads in restricted temp dirs for TOCTOU prevention.

#### Scenario: Delta update via signed manifest
- GIVEN app "arca-desktop" on v1.0.0 and remote `latest.yml` signed with Ed25519
- WHEN `check_for_updates(app_id="arca-desktop", channel="stable")`
- THEN returns `AvailableRelease` with version "1.1.0" and `UpdateArtifact` matching current platform+arch
- AND artifact.hash() SHALL equal SHA-512 digest from signed manifest

#### Scenario: Signature mismatch raises AuthError
- GIVEN `download_update` receives artifact with invalid Ed25519 signature
- WHEN the adapter verifies manifest signature against embedded public key
- THEN raises `AuthError("Ed25519 signature verification failed")`
- AND partial download SHALL be deleted from restricted temp dir

### Requirement: GitHubReleaseAdapter — Desktop via GitHub Releases

Queries GitHub Releases API for latest tag. MUST authenticate via GitHub App installation tokens (not PATs). SHALL filter channel via tag suffix (`-stable`, `-beta`, `-canary`). SHOULD cache last known release for 5 minutes.

#### Scenario: New release detected
- GIVEN GitHub repo "CENFARG/arca-desktop" has release tag "v1.1.0-stable"
- WHEN `check_for_updates(app_id="arca-desktop", channel="stable")`
- THEN fetches release metadata via GitHub API
- AND returns `AvailableRelease(version="1.1.0")`

#### Scenario: Rate-limited API escalates
- GIVEN GitHub API returns HTTP 403 with `X-RateLimit-Remaining: 0`
- WHEN `check_for_updates` is called
- THEN raises `TransientError("GitHub API rate limit exceeded")`
- AND adapter SHALL serve cached release from last successful poll

### Requirement: WebUpdateAdapter — SPA Stale-Client Refresh

HTTP interceptor that compares `x-client-version` response header against `process.env.APP_VERSION`. MUST show banner before forcing Service Worker `skipWaiting()` + `window.location.reload(true)`.

#### Scenario: Stale client via response header
- GIVEN SPA on v1.0.0 and server returns `x-client-version: 1.1.0`
- WHEN the HTTP interceptor processes the header
- THEN `check_for_updates` returns `AvailableRelease(version="1.1.0")`
- AND banner SHALL display "New version available — save work and click to update"

#### Scenario: Apply triggers skipWaiting and reload
- GIVEN Service Worker registered in `waiting` state
- WHEN `apply_update(app_id="grama")` is called
- THEN posts `{type: 'SKIP_WAITING'}` message to the worker
- AND calls `window.location.reload(true)`

### Requirement: PipUpdateAdapter — CLI Git-SHA Install

Resolves HEAD SHA via GitHub API. Installs via `pip install git+https://{repo}@{sha}`. MUST persist `update_state.json` with `previous_stable_sha` before install. Rollback reinstalls previous SHA. SHALL run health check after install.

#### Scenario: SHA mismatch triggers pip install
- GIVEN current SHA "abc123" and remote HEAD resolved to "def456"
- WHEN `check_for_updates(app_id="arca-mcp")`
- THEN returns `AvailableRelease(version="def456")`
- AND `apply_update` writes `{"previous_stable_sha":"abc123"}` to `update_state.json`

#### Scenario: Rollback reinstates previous SHA
- GIVEN `update_state.json` has `{"previous_stable_sha":"abc123"}` and pip install of "def456" failed
- WHEN `rollback(app_id="arca-mcp")`
- THEN reinstalls `git+https://github.com/org/repo@abc123`
- AND returns `UpdateResult(success=true, new_version="abc123")`

### Requirement: AndroidUpdateAdapter — Play Core + PackageInstaller Facade

Runtime-detects install source. MUST use Play Core In-App Updates API for Play Store builds. MUST use `PackageInstaller.Session(MODE_FULL_INSTALL)` for self-hosted APKs. SHALL require `REQUEST_INSTALL_PACKAGES` permission in manifest.

#### Scenario: Flexible update via Play Core
- GIVEN app installed from Play Store and Play Core SDK detects update v1.1.0
- WHEN `check_for_updates(app_id="instaldor-agente")`
- THEN returns `AvailableRelease(version="1.1.0")`
- AND `apply_update` SHALL start flexible background download

#### Scenario: Self-hosted APK via PackageInstaller
- GIVEN app sideloaded and APK binary cached via HTTPS download
- WHEN `apply_update(app_id="instaldor-agente")`
- THEN creates `PackageInstaller.Session(MODE_FULL_INSTALL)` and opens `openWrite()` stream
- AND on `commit()`, SHALL show system install dialog
- AND returns `UpdateResult(success=true, new_version="1.1.0")`

#### Scenario: Rollback raises PermanentError
- GIVEN Android OS
- WHEN `rollback(app_id="instaldor-agente")`
- THEN raises `PermanentError("Android does not support downgrade via PackageInstaller")`
- AND error SHALL include migration hint: "Revert server-side endpoint to previous build version"
