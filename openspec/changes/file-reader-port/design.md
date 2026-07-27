# Design: M23 FileReaderPort — Local Filesystem Read Operations

## Technical Approach

Add a new horizontal manager (M23) following the established core-cenf pattern: `ports.py` Protocol + `adapters/` concrete implementations. Unlike most managers, FileReaderPort has no Pydantic models for MVP — the Protocol itself is the contract, and the adapter handles path resolution and validation directly.

The `LocalFileReaderAdapter` uses Python's built-in `pathlib` for resolution + `aiofiles` for async I/O. Path traversal protection is built into the adapter via `_resolve()`.

## Architecture Decisions

| Decision | Options | Tradeoffs | Choice |
|----------|---------|-----------|--------|
| Async I/O library | `aiofiles` / `anyio` / raw `asyncio.to_thread` | `aiofiles`: lightweight, already in tree (local-storage extra); anyio: heavier; to_thread: no buffering control | **aiofiles** — already a dependency via `local-storage` extra |
| Path traversal protection | Resolve + prefix check / realpath comparison / chroot | Resolve+prefix: simple, fast, avoids import of os; realpath: needs os; chroot: too invasive | **Resolve + prefix check** — already implemented, zero extra deps |
| Protocol design | Single `FileReaderPort` / separate `AsyncFileReader` + `SyncFileReader` | Single: simpler, agents need async; Separate: more flexible, unused complexity | **Single `FileReaderPort`** — all agents use async |
| Default root_dir | `Path.cwd()` / required parameter | cwd(): convenient for scripts; Required: forces explicit config | **`Path.cwd()` default** — matches agent expectations |
| Docker adapter | Separate `DockerFileReaderAdapter` / document `root_dir` usage | Separate: unnecessary abstraction; Document: zero code, works with existing adapter | **Document only** — `LocalFileReaderAdapter(root_dir=/app/data)` works inside containers |
| Models / Pydantic | Add `FileReaderConfig` model / no models for MVP | Model: consistency with other managers; No model: simpler, fewer files | **No MVP models** — pure Protocol; add config model if settings are needed later |

## Data Flow

```
Caller → FileReaderPort.read_file("config.yaml")
  → LocalFileReaderAdapter
    → _resolve("config.yaml") — reject traversal
    → aiofiles.open(resolved, "r", encoding="utf-8")
    → return file contents as str
```

```
Caller → FileReaderPort.file_exists("config.yaml")
  → LocalFileReaderAdapter
    → _resolve("config.yaml") — reject traversal
    → resolved.is_file()
    → return bool
```

```
Caller → FileReaderPort.list_files("*.py")
  → LocalFileReaderAdapter
    → self._root.glob("*.py")
    → filter is_file()
    → return relative Paths
```

```
Caller → FileReaderPort.read_lines("log.txt")
  → LocalFileReaderAdapter
    → _resolve("log.txt") — reject traversal
    → aiofiles.open → f.readlines()
    → strip trailing newlines
    → return list[str]
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/core_infrastructure/file_reader/ports.py` | Already done | `FileReaderPort` Protocol with 4 methods |
| `src/core_infrastructure/file_reader/adapters/local_file_reader_adapter.py` | Already done | `LocalFileReaderAdapter` with path traversal protection |
| `src/core_infrastructure/file_reader/__init__.py` | Modify | Add `LocalFileReaderAdapter` with safe import wrapping |
| `src/core_infrastructure/file_reader/adapters/__init__.py` | Modify | Wrap import in try/except for safe degradation |
| `src/core_infrastructure/__init__.py` | Modify | Add `FileReaderPort` safe import + `LocalFileReaderAdapter` lazy import |
| `tests/unit/file_reader/__init__.py` | Create | Package init |
| `tests/unit/file_reader/test_ports.py` | Create | Protocol contract tests |
| `tests/unit/file_reader/test_local_adapter.py` | Create | Adapter unit tests with tmp_path |
| `AGENTS.md` | Modify | Add M23 row to manager table |
| `llms.txt` | Modify | Add file_reader/ to file structure + M23 to manager table |
| `openspec/specs/file-reader-port/spec.md` | Create | Spec document |
| `openspec/changes/file-reader-port/design.md` | Create | This design document |
| `openspec/changes/file-reader-port/tasks.md` | Create | Task breakdown |

## Interfaces / Contracts

```python
# FileReaderPort — ports.py excerpt
class FileReaderPort(Protocol):
    async def read_file(self, path: str | Path) -> str: ...
    async def file_exists(self, path: str | Path) -> bool: ...
    async def list_files(self, pattern: str) -> list[Path]: ...
    async def read_lines(self, path: str | Path) -> list[str]: ...
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Protocol contract (runtime-checkable, methods) | Standard `isinstance` + `hasattr` checks |
| Unit | `LocalFileReaderAdapter` with `tmp_path` | pytest + tmp_path fixture; async read/exists/list/traversal |
| Integration | (future) Docker mount scenario | Mount tmp dir to container, verify root_dir works |

## Migration / Rollout

No migration required. Net-new manager. Existing code is unaffected.

## Open Questions

- [ ] Should FileReaderPort gain a `read_bytes()` method for binary files?
- [ ] Should a DockerFileReaderAdapter be added for container-specific concerns (e.g., reading from container-storage drivers)?
