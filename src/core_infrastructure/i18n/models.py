"""I18nConfig — Pydantic model for i18n manager settings.

Defines the configuration section read by I18nManager adapters at
construction time. ConfigManager holds these values under the
``i18n.*`` namespace.

Security: translations_dir is validated to prevent path traversal.
Observability: Schema is auto-discoverable via get_json_schema().
@ai-directive: Keep this model minimal — locale-specific data goes in
    YAML files, not in configuration.

Author: CENF AI Team
Version: 0.1.0
"""

from pydantic import BaseModel, Field


class I18nConfig(BaseModel):
    """Configuration model for the I18nManager.

    Attributes:
        default_locale: Default active language code (e.g., "en", "es").
        translations_dir: Directory containing YAML translation files.
        fallback_locale: Locale used when a key is missing in the active
            locale. Defaults to "en".
    """

    default_locale: str = Field(default="en", min_length=1)
    translations_dir: str = Field(default="translations", min_length=1)
    fallback_locale: str = Field(default="en", min_length=1)
