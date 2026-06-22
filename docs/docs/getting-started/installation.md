# Installation

How to install core-cenf in your Python project.

## Prerequisites

- **Python 3.12 or later** — core-cenf uses PEP 695 type syntax and `asyncio.TaskGroup`.
  ```bash
  python --version  # must be >= 3.12
  ```

- **UV** (recommended) — fast Python package manager. Install from
  [astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) or use pip:
  ```bash
  pip install uv
  ```

## Install from GitHub

The primary distribution channel is direct from the repository:

```bash
pip install git+https://github.com/CENFARG/core-cenf.git
```

To pin a specific version or branch:

```bash
pip install git+https://github.com/CENFARG/core-cenf.git@v0.1.0
pip install git+https://github.com/CENFARG/core-cenf.git@main
```

## Install from Local Clone

For development, clone and install in editable mode with all dev dependencies:

```bash
git clone https://github.com/CENFARG/core-cenf.git
cd core-cenf

# Create virtual environment
uv venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # macOS/Linux

# Install with dev dependencies
uv pip install -e ".[dev]"
```

The `[dev]` extra includes pytest, ruff, mypy, and other development tools. Available
extras:

| Extra | What it includes |
|-------|-----------------|
| `dev` | pytest, ruff, mypy, faker, coverage |
| `sqlalchemy` | SQLAlchemy 2.0 with async support |
| `postgres` | asyncpg and psycopg drivers |
| `s3` | aioboto3 for AWS S3 |
| `gcs` | gcloud-aio-storage for Google Cloud Storage |
| `azure` | azure-storage-blob for Azure Blob Storage |
| `all` | Everything above combined |

## Verify Installation

Check that the package is importable and the version is reported:

```bash
python -c "import core_infrastructure; print(core_infrastructure.__version__)"
```

Expected output:

```
0.1.0-dev
```

Verify that all protocol imports work (zero optional dependencies required):

```bash
python -c "
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.common.errors import TransientError, PermanentError
from core_infrastructure.common.context import get_correlation_id, new_correlation_id
from core_infrastructure.common.lifecycle import AsyncLifecycle, HealthStatus
print('All core imports OK')
"
```

Expected output:

```
All core imports OK
```

## Pre-Commit Hooks (Recommended)

core-cenf enforces code quality through pre-commit hooks:

```bash
pre-commit install
```

This installs hooks that run on every commit: ruff formatting, mypy strict type checking,
no bare `asyncio.gather`, no hardcoded platform paths, and file length checks.

## Next Steps

Proceed to **[Quick Start](./quick-start)** to bootstrap all 16 managers and run your
first program in under 5 minutes.
