"""InMemoryConfigAdapter — dict-backed ConfigManager test double.

Provides a zero-dependency ConfigManager implementation for unit tests.
All configuration values are stored in a plain dict — no YAML, no env vars,
no file I/O. Use ``set_value()`` to inject test data dynamically.

Security: No credentials should be stored even in test doubles — use
    meaningless placeholder values in tests.
Observability: Adapter is fully deterministic — no side effects, no logging.
@ai-directive: This adapter exists solely for testing. NEVER use it in
    production code paths.

Author: CENF AI Team
Version: 0.1.0
"""

import json
from copy import deepcopy
from typing import Any, cast

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.config.models import CoreSettings
from core_infrastructure.config.ports import Env


def _resolve_dotted_key(data: dict[str, Any], key: str) -> Any:
    """Traverse a nested dict using dot-notation key.

    Args:
        data: The config dict to traverse.
        key: Dot-separated key path.

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


def _set_dotted_key(data: dict[str, Any], key: str, value: Any) -> None:
    """Set a value at a dotted key path, creating intermediate dicts.

    Args:
        data: Root dict to mutate.
        key: Dot-separated key path.
        value: Value to set at the leaf node.
    """
    parts = key.split(".")
    current = data
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


class InMemoryConfigAdapter:
    """Dict-backed ConfigManager for unit testing.

    All configuration values are stored in a plain dict. The adapter
    satisfies the ``ConfigManager`` Protocol and can be used as a drop-in
    replacement in any test that needs a config provider.

    Args:
        initial_data: Optional dict of initial configuration values.
            Merged on top of CoreSettings defaults.
    """

    def __init__(self, initial_data: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = deepcopy(CoreSettings().model_dump())
        if initial_data:
            self._merge(self._config, initial_data)

    @staticmethod
    def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> None:
        """Recursively merge overlay into base (mutates base)."""
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                InMemoryConfigAdapter._merge(base[key], value)
            else:
                base[key] = deepcopy(value) if isinstance(value, dict) else value

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
            dict[str, Any]: All keys under the given namespace, or ``{}``
                if the namespace does not exist.
        """
        value = _resolve_dotted_key(self._config, namespace)
        if isinstance(value, dict):
            return deepcopy(value)
        return {}

    async def reload(self) -> None:
        """Hot-reload is a noop for in-memory adapter.

        The in-memory adapter has no backing store to reload from.
        This method exists to satisfy the Protocol contract and does nothing.
        """
        return

    def get_json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing CoreSettings.

        Returns:
            dict[str, Any]: A valid JSON Schema object.
        """
        return CoreSettings.model_json_schema()

    # ------------------------------------------------------------------
    # Test-specific helpers (not part of ConfigManager Protocol)
    # ------------------------------------------------------------------

    def set_value(self, key: str, value: Any) -> None:
        """Inject a configuration value for testing purposes.

        This is a test-only method — not part of the ConfigManager Protocol.
        Use it in test fixtures to set up specific config scenarios.

        Args:
            key: Dot-notation key path (e.g., ``"database.host"``).
            value: Value to store at the key path.
        """
        _set_dotted_key(self._config, key, value)
