"""Logger adapters — concrete implementations of LoggerManager Protocol.

- StructlogAdapter: Production adapter using structlog for dev/test/prod profiles.
- InMemoryLoggerAdapter: Test double that collects logs in a list for assertions.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter

__all__ = [
    "InMemoryLoggerAdapter",
    "StructlogAdapter",
]
