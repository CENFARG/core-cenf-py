"""CENF ConfigManager — single source of truth for all configuration.

Implements the 12-factor app configuration pattern: YAML files for defaults,
environment variables for overrides. All 11 other managers read their settings
through this module.

Security: No secrets or credentials stored in plain-text config — use
    SecretManager for sensitive values.
Observability: Config reload events emit INFO-level logs via LoggerManager.
@ai-directive: Never read env vars directly outside this module.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.config.adapters.pydantic_config_adapter import PydanticConfigAdapter
from core_infrastructure.config.models import CoreSettings
from core_infrastructure.config.ports import ConfigManager

__all__ = [
    "ConfigManager",
    "CoreSettings",
    "InMemoryConfigAdapter",
    "PydanticConfigAdapter",
]
