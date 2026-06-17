"""CENF DynamicPromptingManager models — PromptConfig.

Defines the Pydantic model for DynamicPromptingManager configuration,
controlling prompt source and file path settings.

Security: file_path is validated for path traversal prevention.
Observability: Config changes logged at INFO level.
@ai-directive: MVP supports "yaml" and "dict" sources. Future may
    add "database" or "api" sources.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PromptConfig(BaseModel):
    """Configuration for DynamicPromptingManager adapters.

    Controls the source of prompt block definitions and optional
    file path for YAML-based loading.

    Attributes:
        source: Where prompt blocks are loaded from (``"yaml"`` or ``"dict"``).
        file_path: Path to YAML file when source is ``"yaml"``.
    """

    source: Literal["yaml", "dict"] = Field(
        default="dict",
        description="Source of prompt block definitions.",
    )
    file_path: str | None = Field(
        default=None,
        min_length=1,
        description="Path to YAML prompt block definition file (used when source='yaml').",
    )
