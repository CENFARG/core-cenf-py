# M24 MaintenanceManager — Implementation Tasks

## Phase 1: Foundation (3 tasks)
- [ ] 1.1 Create src/core_infrastructure/maintenance/ports.py — MaintenanceManager Protocol
- [ ] 1.2 Create src/core_infrastructure/maintenance/models.py — ErrorReport, ConsentResult, ReportResult, MaintenanceConfig
- [ ] 1.3 Create pii_scrubber.py + consent_store.py helpers + tests

## Phase 2: InMemory Adapter TDD (4 tasks)
- [ ] 2.1 RED: tests/unit/maintenance/test_in_memory_adapter.py — 6 test cases
- [ ] 2.2 GREEN: src/.../adapters/in_memory_maintenance_adapter.py
- [ ] 2.3 RED: tests for consent flow (grant, revoke, check)
- [ ] 2.4 GREEN: consent_store.py implementation

## Phase 3: PII Scrubbing (3 tasks)
- [ ] 3.1 RED: tests for email, JWT, password masking
- [ ] 3.2 GREEN: pii_scrubber.py with regex patterns
- [ ] 3.3 INTEGRATION: test capture_error with real stack traces

## Phase 4: Discord Adapter (3 tasks)
- [ ] 4.1 RED: tests for Discord webhook payload
- [ ] 4.2 GREEN: discord_alert_adapter.py
- [ ] 4.3 TEST: truncation at 2000 chars

## Phase 5: GitHub Adapter (3 tasks)
- [ ] 5.1 RED: tests for GitHub issue creation
- [ ] 5.2 GREEN: github_issue_adapter.py
- [ ] 5.3 TEST: deduplication via stack trace hash

## Phase 6: CENF Server + GlitchTip (4 tasks)
- [ ] 6.1 RED: tests for CENF Server API
- [ ] 6.2 GREEN: cenf_server_adapter.py
- [ ] 6.3 RED: tests for GlitchTip
- [ ] 6.4 GREEN: glitchtip_adapter.py

## Phase 7: Registration (3 tasks)
- [ ] 7.1 Update AGENTS.md with M24 row
- [ ] 7.2 Update __init__.py exports
- [ ] 7.3 Update llms.txt
