"""UpdateManager adapter implementations."""

from core_infrastructure.update.adapters.in_memory_update_adapter import (
    InMemoryUpdateAdapter,
)
from core_infrastructure.update.adapters.http_update_adapter import (
    HttpUpdateAdapter,
)
from core_infrastructure.update.adapters.pip_update_adapter import (
    PipUpdateAdapter,
)

__all__ = ["InMemoryUpdateAdapter", "HttpUpdateAdapter", "PipUpdateAdapter"]
