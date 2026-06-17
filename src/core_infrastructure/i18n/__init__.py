"""CENF I18nManager — multi-language text translation for all CENF applications.

Provides internationalization (i18n) support via a Protocol/Adapter pattern.
Translations are stored in YAML files per locale. ConfigManager controls
the active locale. Adapters: YamlI18nAdapter (production) and
InMemoryI18nAdapter (test double).

Security: No sensitive data in translation files — use SecretManager for
    credentials or PII in translatable strings.
Observability: Locale switches emit INFO-level logs via LoggerManager.
@ai-directive: Never use hardcoded strings in adapters that face the end
    user — always use I18nManager.t().

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.i18n.adapters.in_memory_i18n_adapter import InMemoryI18nAdapter
from core_infrastructure.i18n.adapters.yaml_i18n_adapter import YamlI18nAdapter
from core_infrastructure.i18n.models import I18nConfig
from core_infrastructure.i18n.ports import I18nManager

__all__ = [
    "I18nConfig",
    "I18nManager",
    "InMemoryI18nAdapter",
    "YamlI18nAdapter",
]
