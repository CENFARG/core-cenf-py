# M20 UpdateManager — Production Adapters

## Summary

M20 UpdateManager protocol exists (308 lines, 5 methods). Only InMemoryUpdateAdapter (testing) exists. Need 5 production adapters for the CENF product ecosystem.

## Motivation

- Arca SaaS (Electron desktop) needs auto-update for Windows/macOS/Linux
- grama (web SPA) needs zero-stale-client force-refresh
- arcaMCP + instaldorAgentico (Python CLI) need pip-based update + rollback via Git SHAs
- instaldorAgentico (Android) needs Play Store + self-hosted update
- All need TUF/Sigstore cryptographic signature verification

## Proposed Adapters

| # | Adapter | Product | Technology |
|---|---------|---------|------------|
| A1 | HttpUpdateAdapter | Desktop | electron-updater + Ed25519/SHA-512 |
| A2 | GitHubReleaseAdapter | Desktop | GitHub Releases API |
| A3 | WebUpdateAdapter | Web SPA/PWA | Service Worker + x-client-version header |
| A4 | PipUpdateAdapter | Python CLI | pip install git+https@SHA + update_state.json |
| A5 | AndroidUpdateAdapter | Android | Play Core API + PackageInstaller |

## Non-Goals

- Full TUF infrastructure (tuf-on-ci) — deferred 3 months
- Android Play Store listing — requires Google account setup
- electron-updater actual packaging — requires electron-builder config

## Risks

- A4 PipUpdateAdapter has no direct SOTA precedent — custom design required
- A5 Android requires dual-path (Play Store vs self-hosted) — complexity
- electron-updater testing requires Electron runtime — integration tests deferred

## Dependencies

- M20 protocol already exists in src/core_infrastructure/update/
- Research: deepresearch-Investigación-SOTA_UpdateManager-MaintenanceManager.md
