# Informe Técnico: Eager Import Chain Fix — core-cenf-py

**Para**: Otros agentes que consumen core-cenf-py
**De**: Orchestrator SDD
**Fecha**: 2026-07-14
**Estado**: ✅ COMPLETO — mergeado a `fix/eager-import-chain`, pendiente merge a main

---

## 1. ¿Qué pasaba?

`import core_infrastructure` explotaba con `ModuleNotFoundError` si faltaba **cualquier** dependencia opcional (sqlalchemy, aiofiles, saq), incluso cuando el consumidor no usaba esos managers.

**Causa**: Los `__init__.py` de los sub-paquetes (`database/`, `filestorage/`) importaban adapters de producción **antes** de que el root `__init__.py` pudiera ejecutar sus bloques `try/except ImportError`.

## 2. ¿Qué se hizo?

Se aplicó **Opción A** (try/except en sub-package `__init__.py`) en 2 archivos:

| Archivo | Cambio |
|---------|--------|
| `src/core_infrastructure/database/__init__.py` | Reorden imports (models/ports primero), `SQLAlchemyAdapter` y `MemoryDatabaseAdapter` envueltos en `try/except ImportError` |
| `src/core_infrastructure/filestorage/__init__.py` | Reorden imports (models/ports primero), `LocalStorageAdapter` y `MemoryStorageAdapter` envueltos en `try/except ImportError` |
| `pyproject.toml` | Nuevo extra `[local-storage]` con `aiofiles>=24.0` |
| `tests/test_import_safety.py` | 8 tests de regresión |

## 3. ¿Cómo usarlo desde otro agente?

### Importar core_infrastructure SIN dependencias opcionales

```python
# ✅ Esto NUNCA crashea ahora
import core_infrastructure
from core_infrastructure.database import DatabaseManager  # Protocol — siempre disponible
```

### Usar adapters opcionales con graceful degradation

```python
from core_infrastructure.database import SQLAlchemyAdapter, MemoryDatabaseAdapter

if SQLAlchemyAdapter is not None:
    db = SQLAlchemyAdapter(config, logger)
else:
    db = MemoryDatabaseAdapter(config, logger)  # fallback a in-memory
```

### Tabla de símbolos que pueden ser `None`

| Símbolo | `None` cuando falta | Instalar |
|---------|-------------------|----------|
| `core_infrastructure.database.SQLAlchemyAdapter` | `sqlalchemy` | `pip install "core-cenf[sqlalchemy]"` |
| `core_infrastructure.filestorage.LocalStorageAdapter` | `aiofiles` | `pip install "core-cenf[local-storage]"` |
| `core_infrastructure.cache.RedisCacheAdapter` | `redis` | `pip install "core-cenf[all]"` |
| `core_infrastructure.auth.JwtAuthAdapter` | `python-jose` | `pip install "core-cenf[all]"` |
| `core_infrastructure.secrets.EncryptedSecretAdapter` | `cryptography` | `pip install "core-cenf[all]"` |
| `core_infrastructure.external_api.ResilientHTTPAdapter` | `aiohttp` | `pip install "core-cenf[all]"` |
| `core_infrastructure.observability.OTelAdapter` | `opentelemetry` | `pip install "core-cenf[all]"` |
| `core_infrastructure.permission.CasbinPermissionAdapter` | `pycasbin` | `pip install "core-cenf[all]"` |

**Mem* adapters** (MemoryDatabaseAdapter, MemoryStorageAdapter, InMemoryConfigAdapter, etc.) **NUNCA son `None`** — zero deps externas, siempre disponibles.

### Instalación mínima recomendada

```bash
# Solo lo básico (config, logger, secrets, errors, feature-flags, state-machine)
pip install git+https://github.com/CENFARG/core-cenf-py.git

# Con file storage local
pip install "core-cenf[local-storage] @ git+https://github.com/CENFARG/core-cenf-py.git"

# Todo
pip install "core-cenf[all] @ git+https://github.com/CENFARG/core-cenf-py.git"
```

## 4. Verificación

| Gate | Resultado |
|------|-----------|
| `ruff check src/ tests/` | ✅ Pass |
| `mypy src/core_infrastructure/ --strict` | ✅ Pass (149 files) |
| `python -m pytest tests/ -q` | ✅ 1497 passed |
| `tests/test_import_safety.py` | ✅ 8/8 tests |

## 5. Estructura del fix (para debug)

```
import core_infrastructure
  │
  ├─ from .database.models import DatabaseConfig    # ✅ YA NO CRASHEA
  │     └─ database/__init__.py REORDENADO:
  │           ├─ from .models import ...            # primero (safe)
  │           ├─ from .ports import ...              # segundo (safe)
  │           └─ try: from .adapters.x import ...    # último (try/except)
  │               except ImportError: X = None
  └─ otros managers → todos seguros (core deps o try/except)
```

## 6. Commits

```
9748a4e chore(deps): add [local-storage] optional extra with aiofiles
1d0ec3c fix(imports): lazy adapter imports in database/__init__.py
ff5efc1 fix(imports): lazy adapter imports in filestorage/__init__.py
b2f092d test(imports): add regression test for import safety
6915e8b docs(tasks): mark all eager-import-fix tasks complete
```

**Branch**: `fix/eager-import-chain`
