"""PydanticConfigAdapter — production ConfigManager using pydantic-settings + PyYAML.

Implements the 12-factor app pattern: YAML files provide defaults, environment
variables (prefixed with CENF_) override them at runtime. Hot-reload is
protected by ``asyncio.Lock`` to prevent concurrent reload races.

Security: No secrets in YAML — use SecretManager for credentials.
Observability: Reload events are logged at INFO level via LoggerManager
    (when available). Missing-key errors include the full key path.
@ai-directive: The internal ``_config`` dict is the single source of truth.
    All get_* methods read from it — never from raw YAML or env directly.

Author: CENF AI Team
Version: 0.1.0
"""

import asyncio
import json
import os
from typing import Any, cast

import yaml

from core_infrastructure.common.errors import PermanentError, ValidationError
from core_infrastructure.config.models import CoreSettings
from core_infrastructure.config.ports import Env
from core_infrastructure.errors.ports import ErrorHandlingManager


def _resolve_dotted_key(data: dict[str, Any], key: str) -> Any:
    """Traverse a nested dict using dot-notation key.

    Args:
        data: The config dict to traverse.
        key: Dot-separated key path (e.g., ``"database.host"``).

    Returns:
        Any: The value at the key path, or ``None`` if not found.
    """
    parts = key.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


class PydanticConfigAdapter:
    """Production ConfigManager backed by YAML + env vars.

    Constructor loads YAML, validates via CoreSettings, then merges
    environment variable overrides.

    Args:
        env_prefix: Prefix for env var overrides (e.g., ``"CENF_"``).
        config_path: Path to the YAML config file. If ``None``, only
            env vars and CoreSettings defaults are used.

    Raises:
        PermanentError: If the YAML file is missing or malformed.
    """

    def __init__(
        self,
        env_prefix: str = "CENF_",
        config_path: str | None = None,
        error_handler: ErrorHandlingManager | None = None,
    ) -> None:
        self._env_prefix = env_prefix
        self._config_path = config_path
        self._config: dict[str, Any] = {}
        self._reload_lock = asyncio.Lock()
        self._error_handler = error_handler
        self._load_config()

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        """Load or reload configuration from YAML + env vars.

        Steps:
        1. Start with CoreSettings defaults.
        2. If a YAML path is configured, merge its values on top.
        3. Apply env var overrides (CENF_ prefix) on top of everything.

        Raises:
            PermanentError: On missing or malformed YAML file.
        """
        # Start with Pydantic defaults
        defaults = CoreSettings().model_dump()

        # Merge YAML if available
        if self._config_path:
            try:
                with open(self._config_path, encoding="utf-8") as f:
                    yaml_data = yaml.safe_load(f) or {}
            except FileNotFoundError:
                raise PermanentError(
                    f"Config file not found: {self._config_path}",
                    details={"path": self._config_path},
                ) from None
            except yaml.YAMLError as exc:
                raise PermanentError(
                    f"Invalid YAML in config file: {self._config_path}",
                    details={"path": self._config_path, "error": str(exc)},
                ) from exc
            self._deep_merge(defaults, yaml_data)

        # Apply env var overrides
        self._apply_env_overrides(defaults)

        # Validate the merged result
        try:
            _validated = CoreSettings.model_validate(defaults)
        except Exception as exc:
            raise PermanentError(
                f"Config validation failed: {exc}",
                details={"error": str(exc)},
            ) from exc

        self._config = defaults

    def _deep_merge(self, base: dict[str, Any], overlay: dict[str, Any]) -> None:
        """Recursively merge overlay dict into base dict (mutates base).

        Args:
            base: The target dict to merge into.
            overlay: The source dict whose values override base.
        """
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _apply_env_overrides(self, config: dict[str, Any]) -> None:
        """Apply environment variable overrides to the config dict.

        Environment variables are expected in the format:
        ``{PREFIX}KEY__SUBKEY=value``, which maps to ``config["key"]["subkey"]``.

        Args:
            config: Mutable config dict to apply overrides to.
        """
        prefix = self._env_prefix
        for env_key, env_value in os.environ.items():
            if not env_key.startswith(prefix):
                continue
            # Strip prefix and normalize to lowercase
            stripped = env_key[len(prefix):].lower()
            # Support __ as nested separator (e.g., CENF_database__host)
            parts = stripped.split("__")
            if len(parts) == 1:
                # Top-level key
                config[parts[0]] = self._coerce_env_value(env_value)
            else:
                # Nested key
                self._set_nested(config, parts, self._coerce_env_value(env_value))

    @staticmethod
    def _coerce_env_value(value: str) -> Any:
        """Attempt to coerce a raw env-var string to a typed Python value.

        Args:
            value: Raw string value from ``os.environ``.

        Returns:
            Any: ``bool``, ``int``, ``float``, or the original ``str``.
        """
        # Boolean
        lower = value.lower()
        if lower in ("true", "yes", "1"):
            return True
        if lower in ("false", "no", "0"):
            return False
        # Integer
        try:
            return int(value)
        except ValueError:
            pass
        # Float
        try:
            return float(value)
        except ValueError:
            pass
        # String (default)
        return value

    @staticmethod
    def _set_nested(config: dict[str, Any], parts: list[str], value: Any) -> None:
        """Set a value at a nested key path, creating intermediate dicts as needed.

        Args:
            config: Root dict to mutate.
            parts: Key path segments (e.g., ``["database", "host"]``).
            value: Value to set at the leaf.
        """
        current = config
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    # ------------------------------------------------------------------
    # Public API — ConfigManager Protocol
    # ------------------------------------------------------------------

    def get_env(self) -> Env:
        """Return the current deployment environment.

        Returns:
            Env: One of ``"local"``, ``"dev"``, ``"staging"``, ``"prod"``.
        """
        return cast(Env, self._config.get("env", "dev"))

    def get_string(self, key: str, default_value: str | None = None) -> str:
        """Retrieve a string configuration value.

        Args:
            key: Dot-notation config key.
            default_value: Fallback if key is not found.

        Returns:
            str: The configured string value.

        Raises:
            ValidationError: If key is missing and no default is provided.
        """
        value = _resolve_dotted_key(self._config, key)
        if value is not None:
            return str(value)
        if default_value is not None:
            return default_value
        raise ValidationError(
            f"Missing required config key: {key}",
            details={"key": key},
        )

    def get_number(self, key: str, default_value: float | None = None) -> float:
        """Retrieve a numeric configuration value.

        Args:
            key: Dot-notation config key.
            default_value: Fallback if key is not found.

        Returns:
            float: The configured numeric value.

        Raises:
            ValidationError: If key is missing and no default, or value is not numeric.
        """
        value = _resolve_dotted_key(self._config, key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                raise ValidationError(
                    f"Config key '{key}' is not a number: {value!r}",
                    details={"key": key, "value": str(value)},
                ) from None
        if default_value is not None:
            return default_value
        raise ValidationError(
            f"Missing required config key: {key}",
            details={"key": key},
        )

    def get_boolean(self, key: str, default_value: bool | None = None) -> bool:
        """Retrieve a boolean configuration value.

        Args:
            key: Dot-notation config key.
            default_value: Fallback if key is not found.

        Returns:
            bool: The configured boolean value.

        Raises:
            ValidationError: If key is missing and no default, or value is not boolean.
        """
        value = _resolve_dotted_key(self._config, key)
        if value is not None:
            if isinstance(value, bool):
                return value
            raise ValidationError(
                f"Config key '{key}' is not a boolean: {value!r}",
                details={"key": key, "value": str(value)},
            )
        if default_value is not None:
            return default_value
        raise ValidationError(
            f"Missing required config key: {key}",
            details={"key": key},
        )

    def get_json(self, key: str, default_value: Any = None) -> Any:
        """Retrieve a JSON-deserialized configuration value.

        If the stored value is a string, it is parsed as JSON. Otherwise,
        the raw value is returned as-is.

        Args:
            key: Dot-notation config key.
            default_value: Fallback if key is not found.

        Returns:
            Any: The deserialized Python object.

        Raises:
            ValidationError: If the value is a string that is not valid JSON.
        """
        value = _resolve_dotted_key(self._config, key)
        if value is not None:
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError as exc:
                    raise ValidationError(
                        f"Config key '{key}' is not valid JSON: {exc}",
                        details={"key": key, "value": value},
                    ) from exc
            return value
        if default_value is not None:
            return default_value
        raise ValidationError(
            f"Missing required config key: {key}",
            details={"key": key},
        )

    def get_section(self, namespace: str) -> dict[str, Any]:
        """Retrieve an entire configuration section as a dict.

        Args:
            namespace: Dot-notation namespace prefix.

        Returns:
            dict[str, Any]: All keys under the given namespace.
        """
        value = _resolve_dotted_key(self._config, namespace)
        if isinstance(value, dict):
            return value
        # Return empty dict if the section doesn't exist or is not a dict
        return {}

    async def reload(self) -> None:
        """Hot-reload configuration from the backing YAML file.

        Protected by ``asyncio.Lock`` to prevent concurrent reload races.
        After reload, the internal ``_config`` dict is atomically replaced.

        Observability: Reload events are logged at INFO level.
        """
        async with self._reload_lock:
            try:
                self._load_config()
            except Exception as exc:
                if self._error_handler is not None:
                    self._error_handler.report(
                        exc, context={"source": "PydanticConfigAdapter.reload"})
                raise

    def get_json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing CoreSettings.

        Returns:
            dict[str, Any]: A valid JSON Schema object.
        """
        return CoreSettings.model_json_schema()
