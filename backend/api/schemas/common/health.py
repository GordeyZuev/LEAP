"""Health check endpoint schemas"""

from typing import Literal

from pydantic import BaseModel

from .config import BASE_MODEL_CONFIG


class LivenessResponse(BaseModel):
    """Process is alive."""

    model_config = BASE_MODEL_CONFIG

    status: Literal["ok"] = "ok"


class HealthCheckResult(BaseModel):
    """Per-dependency health result."""

    model_config = BASE_MODEL_CONFIG

    status: Literal["ok", "fail"]
    detail: str | None = None


class ReadinessResponse(BaseModel):
    """Process is ready to serve traffic."""

    model_config = BASE_MODEL_CONFIG

    ready: bool
    checks: dict[str, HealthCheckResult]
