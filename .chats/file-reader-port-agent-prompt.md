📋 Mensaje para el agente que necesita FileReaderPort

✅ FileReaderPort YA EXISTE en core-cenf-py (M23, mergeado a main).

GitHub: https://github.com/CENFARG/core-cenf-py
PR: https://github.com/CENFARG/core-cenf-py/pull/2 (mergeado)
Repositorio local: C:\Dropbox\DOC.RECA\06-Software\core-cenf-py

INSTALACIÓN:

```bash
# Actualizar a la última versión (v0.1.3+)
pip install --upgrade git+https://github.com/CENFARG/core-cenf-py.git

# O en desarrollo
cd C:\Dropbox\DOC.RECA\06-Software\core-cenf-py
pip install -e ".[dev]"
```

USO:

```python
from core_infrastructure.file_reader.adapters import LocalFileReaderAdapter

# Crear reader con root_dir (por defecto: cwd)
reader = LocalFileReaderAdapter(root_dir="/app/data")

# API completa (4 métodos, todos async):
content = await reader.read_file("config.yaml")        # → str
exists  = await reader.file_exists("config.yaml")       # → bool
files   = await reader.list_files("**/*.py")            # → list[Path]
lines   = await reader.read_lines("config.yaml")        # → list[str]
```

SEGURIDAD:
- Sandbox: todas las rutas se resuelven dentro de root_dir
- Path traversal: rechaza paths que intentan escapar (../../etc/passwd → ValueError)
- Read-only: no hay operaciones de escritura

PROTOCOLO:
```python
from core_infrastructure.file_reader import FileReaderPort
# Protocol runtime-checkable. Implementá tu propio adapter si necesitás
# leer desde otro origen (Docker, network, etc.)
```

ESTRUCTURA DE ARCHIVOS:
```
src/core_infrastructure/file_reader/
├── ports.py                              FileReaderPort protocol
├── __init__.py
└── adapters/
    ├── __init__.py
    └── local_file_reader_adapter.py       Implementación local
```

TESTS:
```
tests/unit/file_reader/
├── test_ports.py                         7 tests (protocol contract)
└── test_local_adapter.py                18 tests (funcionalidad + seguridad)
```

DOCKER:
LocalFileReaderAdapter funciona dentro de contenedores Docker sin cambios. Solo configurar root_dir al path del volumen montado. DockerFileReaderAdapter queda como follow-up (documentado en design.md).

NOTA: FileReaderPort (M23) es SEPARADO de FileStorageManager (M09).
- M09 → blob storage (upload/download bytes a S3/buckets)
- M23 → lectura local (cat, read, glob, líneas)

DOCUMENTACIÓN COMPLETA:
- AGENTS.md: tabla de managers, fila M23
- openspec/specs/file-reader-port/spec.md: especificación con Gherkin scenarios
- openspec/changes/file-reader-port/design.md: decisiones de arquitectura
- openspec/changes/file-reader-port/tasks.md: 15 tasks (todas completadas)
