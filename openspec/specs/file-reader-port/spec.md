---
Spec_ID: SPEC_M23
Title: FileReaderPort Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [file-reader, filesystem, aiofiles, path-traversal]
Dependency_Hashes: []
Last_Updated: "2026-07-27"
---

# SPEC_M23: FileReaderPort

## Purpose

Provide a simple, safe local filesystem read abstraction for agents and workflow engines. Separate from M09 FileStorageManager (blob storage) — this port is for reading local files as an agent would with `cat` or `read`. Used by workflow engines, prompt loaders, and any component that needs filesystem access.

**Does NOT**: Provide blob storage, write operations, file management, or remote filesystem access.

**Docker note**: The `LocalFileReaderAdapter` works inside Docker containers by setting `root_dir` to the container's mounted volume path (e.g., `/app/data`). No separate Docker adapter is needed.

## Python Protocol

```python
from __future__ import annotations
from pathlib import Path
from typing import Protocol, runtime_checkable

@runtime_checkable
class FileReaderPort(Protocol):
    """@ai-directive: All paths are resolved relative to the adapter's root directory.
    Never pass absolute user-supplied paths without validation."""

    async def read_file(self, path: str | Path) -> str:
        """Read entire file contents as a UTF-8 string."""
        ...

    async def file_exists(self, path: str | Path) -> bool:
        """Check if a file exists at the given path."""
        ...

    async def list_files(self, pattern: str) -> list[Path]:
        """List files matching a glob pattern."""
        ...

    async def read_lines(self, path: str | Path) -> list[str]:
        """Read a file line by line, stripping trailing newlines."""
        ...
```

## Boundary Validation

Path traversal protection is implemented at the adapter level via `_resolve()`. No Pydantic models are required for MVP — the Protocol itself is the contract.

| Rule | Behaviour |
|------|-----------|
| Path traversal (`../../etc/passwd`) | `ValueError` — rejected before filesystem access |
| Non-existent file | `FileNotFoundError` |
| Non-file path (symlink to dir) | `FileNotFoundError` from `is_file()` check |
| Empty pattern in `list_files` | Behaves as `*` — lists all files in root |
| Absolute path input | Resolved relative to root; if it escapes, rejected as traversal |

## Gherkin Scenarios

### Scenario: Read file by relative path

- GIVEN a `LocalFileReaderAdapter` with `root_dir=/tmp/test`
- AND file `/tmp/test/hello.txt` exists with content `"Hello, World!"`
- WHEN `read_file("hello.txt")` is called
- THEN it returns `"Hello, World!"`

### Scenario: Read non-existent file raises FileNotFoundError

- GIVEN a `LocalFileReaderAdapter` with `root_dir=/tmp/test`
- AND file `/tmp/test/missing.txt` does NOT exist
- WHEN `read_file("missing.txt")` is called
- THEN it raises `FileNotFoundError`

### Scenario: Path traversal is rejected

- GIVEN a `LocalFileReaderAdapter` with `root_dir=/tmp/test`
- WHEN `read_file("../../etc/passwd")` is called
- THEN it raises `ValueError` with message containing "Path traversal detected"

### Scenario: file_exists returns True for existing files

- GIVEN a `LocalFileReaderAdapter` with `root_dir=/tmp/test`
- AND file `/tmp/test/config.yaml` exists
- WHEN `file_exists("config.yaml")` is called
- THEN it returns `True`

### Scenario: file_exists returns False for missing files

- GIVEN a `LocalFileReaderAdapter` with `root_dir=/tmp/test`
- WHEN `file_exists("nope.txt")` is called
- THEN it returns `False`

### Scenario: list_files with glob pattern

- GIVEN a `LocalFileReaderAdapter` with `root_dir=/tmp/test`
- AND files `/tmp/test/foo.py` and `/tmp/test/bar.py` exist
- AND file `/tmp/test/readme.md` also exists
- WHEN `list_files("*.py")` is called
- THEN it returns `[Path("foo.py"), Path("bar.py")]`

### Scenario: read_lines strips trailing newlines

- GIVEN a `LocalFileReaderAdapter` with `root_dir=/tmp/test`
- AND file `/tmp/test/lines.txt` contains `"line1\nline2\nline3\n"`
- WHEN `read_lines("lines.txt")` is called
- THEN it returns `["line1", "line2", "line3"]`

### Scenario: Docker container with mounted volume

- GIVEN a `LocalFileReaderAdapter` with `root_dir=/app/data`
- AND the adapter is running inside a Docker container
- AND file `/app/data/config.yaml` exists
- WHEN `read_file("config.yaml")` is called
- THEN it returns the file contents

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Path traversal | PERMANENT | Raise `ValueError` immediately |
| File not found | PERMANENT | Raise `FileNotFoundError` |
| Permission denied | PERMANENT | Raise `PermissionError` (from OS) |
| `aiofiles` not installed | N/A | `LocalFileReaderAdapter = None` (safe import) |

## Test Requirements

- **Unit**: `LocalFileReaderAdapter` with `tmp_path` fixture — verify read, exists, list, traversal rejection.
- **Protocol**: Verify `FileReaderPort` is runtime-checkable, all methods defined.
- **Integration**: (future) Test with real filesystem, large files, concurrent reads.

## Do's and Don'ts

**Do**:
- Use `pathlib` for all path resolution
- Reject path traversal attempts before filesystem access
- Return relative paths from `list_files`
- Use `aiofiles` for async file I/O
- Document Docker usage: just set `root_dir` to the container mount path

**Don't**:
- Accept or resolve absolute user-supplied paths
- Implement write operations (this is a read-only port)
- Cache file contents — always read fresh
- Use blocking `open()` calls in async methods
