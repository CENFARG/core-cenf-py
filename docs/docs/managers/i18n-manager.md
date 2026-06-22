---
sidebar_position: 17
---

# I18nManager (M17)

Multi-language translation with YAML files per locale. Supports parameter substitution via `str.format()`, dot-notation key traversal, and automatic fallback locale on missing keys. **NEVER throw on missing translation — return `[missing: key]` as a visible fallback.**

## Protocol

`I18nManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.i18n.ports`.

### `set_locale(locale) → None`

Switch the active language locale immediately.

```python
def set_locale(self, locale: str) -> None: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `locale` | `str` | Language code (e.g., `"es"`, `"en"`) |

---

### `t(key, **params) → str`

Translate a key with optional parameter substitution. Traverses nested translations using dot-notation. Falls back to `fallback_locale` if key is missing in active locale. Returns `"[missing: {key}]"` if not found in any locale.

```python
def t(self, key: str, **params: Any) -> str: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `key` | `str` | Dot-notation translation key (e.g., `"greeting"`, `"errors.not_found"`) |
| `**params` | `Any` | Optional format parameters for `str.format()` |

**Returns:** Translated string, or `"[missing: {key}]"` if unfound. **Never raises.**

---

### `get_available_locales() → list[str]`

Return all currently loaded locales, sorted.

```python
def get_available_locales(self) -> list[str]: ...
```

---

### `load_translations(path, locale) → None`

Load translations into a locale. Accepts a dict or a file path to YAML. Merges with existing translations.

```python
def load_translations(self, path: str | dict[str, Any], locale: str) -> None: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `path` | `str \| dict` | Path to YAML file, or a dict of translations |
| `locale` | `str` | Target locale code |

---

### `get_json_schema() → dict[str, Any]`

Return JSON Schema for agent discovery (AX).

```python
def get_json_schema(self) -> dict[str, Any]: ...
```

---

## Models

**File:** `core_infrastructure.i18n.models`

### `I18nConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_locale` | `str` (≥1) | `"en"` | Default active language code |
| `translations_dir` | `str` (≥1) | `"translations"` | Directory with YAML translation files |
| `fallback_locale` | `str` (≥1) | `"en"` | Locale used when key missing in active locale |

---

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `YamlI18nAdapter` | YAML files (per locale) | Production — reads `translations/{locale}.yaml`, deep-merges on load |
| `InMemoryI18nAdapter` | In-memory dict | Testing — pre-load translations directly from dicts |

**Translation format:** YAML files are nested dicts keyed by locale. The active locale is read from ConfigManager (`i18n.locale` key, defaults to `"en"`). Locale switches emit INFO logs. Missing keys emit WARNING.

**YAML file format:**
```yaml
# translations/en.yaml
greeting: "Hello, {name}!"
errors:
  not_found: "The requested resource was not found."
  unauthorized: "You are not authorized to perform this action."
```

---

## Usage Example

```python
from core_infrastructure.i18n.adapters.yaml_i18n_adapter import YamlI18nAdapter
from core_infrastructure.i18n.adapters.in_memory_i18n_adapter import InMemoryI18nAdapter

# Production: YAML file adapter
i18n = YamlI18nAdapter(
    config_manager=config,
    logger_manager=logger,
    fallback_locale="en",
)

# Load translations from YAML files
i18n.load_translations("translations/en.yaml", "en")
i18n.load_translations("translations/es.yaml", "es")

# Translate with parameters
greeting = i18n.t("greeting", name="Alice")
# → "Hello, Alice!"

# Nested keys with dot-notation
error_msg = i18n.t("errors.not_found")
# → "The requested resource was not found."

# Switch locale
i18n.set_locale("es")
# All subsequent t() calls use Spanish

# Missing key fallback
missing = i18n.t("nonexistent.key")
# → "[missing: nonexistent.key]"

# Testing: InMemoryI18nAdapter
test_i18n = InMemoryI18nAdapter(
    translations={
        "en": {"greeting": "Hello, {name}!"},
        "es": {"greeting": "¡Hola, {name}!"},
    },
    default_locale="en",
    fallback_locale="en",
)

test_i18n.set_locale("es")
assert test_i18n.t("greeting", name="Carlos") == "¡Hola, Carlos!"

# Load from dict (merges with existing)
test_i18n.load_translations({"farewell": "Adiós, {name}!"}, "es")
assert test_i18n.t("farewell", name="Carlos") == "Adiós, Carlos!"

# Available locales
assert test_i18n.get_available_locales() == ["en", "es"]
```

---

## @ai-directive

> **NEVER throw on missing translation — return `[missing: key]` as a visible fallback.** Translation keys are developer-controlled; user input is only passed as `**params` for substitution, never as keys. When adding a new locale, update the YAML file AND ensure both adapters handle the new locale correctly. `set_locale()` switches the active language immediately.

## Related

- [ConfigManager](config-manager.md) — supplies `i18n.locale` and `i18n.translations_dir`
- [LoggerManager](logger-manager.md) — locale switches at INFO, missing keys at WARNING
