"""CoreSettings — root Pydantic model for CENF core configuration.

Validates the minimum bootstrap configuration needed before any other
manager can read its section. All 11 managers extend their own settings
models from sections under this root.

Security: env field determines log verbosity and telemetry sampling rate.
Observability: Schema is auto-discoverable via ConfigManager.get_json_schema().
@ai-directive: Keep this model minimal — per-manager settings go in their
    respective models.py files, not here.

Author: CENF AI Team
Version: 0.1.0
"""

from typing import Literal

from pydantic import BaseModel, Field


class CoreSettings(BaseModel):
    """Root configuration model validated at bootstrap.

    The ConfigManager adapter validates this model on startup. If validation
    fails, bootstrap exits immediately (fail-fast).

    Attributes:
        env: Deployment environment — controls log profiles and sampling.
        app_name: Unique name for this application instance.
        version: Semver string used in health checks and telemetry.
        log_level: Minimum log level emitted by LoggerManager.
    """

    env: Literal["local", "dev", "staging", "prod"] = Field(default="dev")
    app_name: str = Field(min_length=1, max_length=128, default="cenf-core")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+", default="0.1.0")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
