# Tasks: M23 FileReaderPort

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~320 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-chain |
| Chain strategy | pending (single slice resolves at apply) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | SDD docs (spec, design, tasks) + tests + registry updates | PR 1 | Single PR; all documentation and test artifacts |
| 2 | (future) DockerFileReaderAdapter — mount-aware file reader | Follow-up | Container-specific path resolution |

## Phase 1: SDD Specifications

- [ ] 1.1 Write `openspec/specs/file-reader-port/spec.md` — full spec with Gherkin scenarios, error classification, test requirements
- [ ] 1.2 Write `openspec/changes/file-reader-port/design.md` — architecture decisions, data flow, file changes
- [ ] 1.3 Write `openspec/changes/file-reader-port/tasks.md` — this task breakdown

## Phase 2: Import Safety (fix existing code)

- [ ] 2.1 Fix `src/core_infrastructure/file_reader/adapters/__init__.py` — wrap `LocalFileReaderAdapter` import in `try/except ImportError → None` with `# type: ignore[assignment,misc]`
- [ ] 2.2 Fix `src/core_infrastructure/file_reader/__init__.py` — add `LocalFileReaderAdapter` with safe import wrapping, add `DockerFileReaderAdapter` = `None` placeholder
- [ ] 2.3 Fix `src/core_infrastructure/__init__.py` — add `FileReaderPort` safe import + `LocalFileReaderAdapter` with lazy safety
- [ ] 2.4 Add `docker-file-reader` optional extra to `pyproject.toml` for future Docker support

## Phase 3: Unit Tests

- [ ] 3.1 Create `tests/unit/file_reader/__init__.py` — package init
- [ ] 3.2 Create `tests/unit/file_reader/test_ports.py` — Protocol contract tests (runtime-checkable, all methods, valid/invalid class)
- [ ] 3.3 Create `tests/unit/file_reader/test_local_adapter.py` — adapter tests with tmp_path:
  - read_file roundtrip
  - read_file raises FileNotFoundError for missing
  - read_file raises ValueError for path traversal
  - file_exists returns True/False
  - list_files with glob pattern
  - list_files returns empty for no match
  - read_lines strips trailing newlines
  - Protocol compliance (isinstance check)

## Phase 4: Registry Updates

- [ ] 4.1 Update `AGENTS.md` — add M23 row to the manager table (change "22 Managers" to "23 Managers"), add @ai-directive entry
- [ ] 4.2 Update `llms.txt` — add `file_reader/` to file structure, add M23 to manager reference table
- [ ] 4.3 Update `AGENTS_API.md` — add M23 section with full method signatures

## Phase 5: Quality Gates

- [ ] 5.1 Run `ruff check src/ tests/` — zero errors
- [ ] 5.2 Run `mypy src/core_infrastructure/ --strict` — zero errors
- [ ] 5.3 Run `python -m pytest tests/ -q` — all green

## Phase 6: Version Bump

- [ ] 6.1 Bump version `0.1.2` → `0.1.3` in `pyproject.toml` (new manager addition)
- [ ] 6.2 Update `CHANGELOG.md` with M23 FileReaderPort entry

## Out of Scope (Do NOT Touch in This PR)

- `DockerFileReaderAdapter` implementation — spec/design exists, implementation deferred
- Any adapter implementation beyond `LocalFileReaderAdapter`
- Binary read support (`read_bytes()`) — deferred for future iteration
- Integration tests with Docker — deferred
