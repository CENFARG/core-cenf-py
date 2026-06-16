"""ConfigManager Protocol — the contract every config adapter must satisfy.

Defines the typed configuration interface consumed by all infrastructure
managers. Adapters (pydantic-settings, in-memory test double) implement
this Protocol.

Security: get_env() returns an environment identifier, not raw env values.
Observability: get_json_schema() enables LLM agents to discover available
    configuration keys via structured JSON Schema metadata.
@ai-directive: The generic type parameters on get_json[T] and get_section[T]
    MUST be preserved by all adapter implementations for mypy strict mode.

Author: CENF AI Team
Version: 0.1.0
"""

from typing import Any, Literal, Protocol, runtime_checkable

Env = Literal["local", "dev", "staging", "prod"]


@runtime_checkable
class ConfigManager(Protocol):
    """Configuration contract for the 12-factor app pattern.

    All infrastructure managers read configuration exclusively through this
    interface. Concrete adapters load from YAML + env vars (pydantic-settings)
    or a dict (in-memory test double).

    Rules:
        - get_env() returns the current deployment environment.
        - All get_* methods accept an optional default_value.
        - get_json() and get_section() use generics for type-safe extraction.
        - reload() is async — allows hot-reload without blocking.
        - get_json_schema() returns JSON Schema for LLM agent discovery.

    @ai-directive: When adding a new config key, update CoreSettings AND
        ensure both adapters handle the new key correctly.
    """

    def get_env(self) -> Env:
        """Return the current deployment environment.

        Returns:
            Env: One of ``"local"``, ``"dev"``, ``"staging"``, ``"prod"``.
        """
        ...

    def get_string(self, key: str, default_value: str | None = None) -> str:
        """Retrieve a string configuration value.

        Args:
            key: Dot-notation config key (e.g., ``"app.name"``).
            default_value: Fallback if key is not found.

        Returns:
            str: The configured value.

        Raises:
            ValidationError: If key is missing and no default is provided.
        """
        ...

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
        ...

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
        ...

    def get_json(self, key: str, default_value: Any = None) -> Any:
        """Retrieve a JSON-deserialized configuration value.

        Args:
            key: Dot-notation config key pointing to a JSON string value.
            default_value: Fallback if key is not found.

        Returns:
            Any: The deserialized Python object.

        Raises:
            ValidationError: If the value is not valid JSON.
        """
        ...

    def get_section(self, namespace: str) -> dict[str, Any]:
        """Retrieve an entire configuration section as a dict.

        Args:
            namespace: Dot-notation namespace prefix (e.g., ``"logger"``).

        Returns:
            dict[str, Any]: All keys under the given namespace.
        """
        ...

    async def reload(self) -> None:
        """Hot-reload configuration from the backing store.

        Must be protected by an ``asyncio.Lock`` in adapter implementations
        to prevent concurrent reload races.

        Security: Reload events are logged at INFO level.
        """
        ...

    def get_json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing the CoreSettings model.

        Used by LLM agents for tool discovery (AX — Agent Experience).
        Schema includes field descriptions, types, defaults, and constraints.

        Returns:
            dict[str, Any]: A valid JSON Schema object.
        """
        ...
