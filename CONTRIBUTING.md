# Contributing to core-cenf

## Development Methodology

core-cenf follows **SDD (Spec-Driven Development)** + **TDD (Test-Driven Development)** strictly. All changes must go through the full SDD pipeline: explore → propose → spec → design → tasks → apply → verify → archive.

## Getting Started

```bash
git clone <repo-url>
cd core-cenf
uv venv .venv
.venv\Scripts\activate
uv pip install -e ".[dev]"
python -m pytest tests/
```

## Branch Strategy

- `main` — stable, merge-only
- `pr/NNN-description` — feature branches (stacked-to-main or feature-branch-chain)
- Commit granularity: one commit per TDD task (RED → GREEN → REFACTOR cycle)

## Code Standards (CENF Rules)

1. **Max 250 lines per file** — split adapters into helpers if needed
2. **File headers** required on every `.py` file: what, why, version, author (max 10 lines)
3. **Google-style docstrings** on all public functions with Security, Observability, @ai-directive sections
4. **English only** for all code, identifiers, comments, and documentation
5. **No hardcoded values** — everything through ConfigManager
6. **@functools.wraps(func)** on ALL decorators
7. **ParamSpec/TypeVar** for generic decorators
8. **asyncio.TaskGroup** — never bare asyncio.gather
9. **Implicit context propagation** via contextvars — never pass context as argument

## Adding a New Manager

1. **Spec**: Write spec at `openspec/specs/<new-manager>/spec.md` with Protocol, Gherkin scenarios, RED metrics, error taxonomy
2. **Ports**: Create `src/core_infrastructure/<new-manager>/ports.py` — Protocol class
3. **Models**: `models.py` — Pydantic V2 boundary validation
4. **Adapters**: At least one production adapter + one in-memory test double
5. **Tests**: Unit tests for ports + both adapters, integration tests for cross-manager flows
6. **Exports**: Update `src/core_infrastructure/__init__.py`
7. **AGENTS.md**: Update the manager table and @ai-directive reference

## Testing

```bash
# Unit tests
python -m pytest tests/unit/ -v

# Integration tests
python -m pytest tests/integration/ -v

# E2E tests
python -m pytest tests/e2e/ -v -m e2e

# Full suite
python -m pytest tests/ -v
```

## Quality Gates (CI would enforce these)

```bash
ruff check src/ tests/
mypy src/core_infrastructure/ --strict
python -m pytest tests/ -q
```

All three must pass before merge.
