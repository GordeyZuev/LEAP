"""Health check endpoint schemas"""

from pydantic import BaseModel

from .config import BASE_MODEL_CONFIG


class HealthCheckResponse(BaseModel):
    """Health check response."""

    model_config = BASE_MODEL_CONFIG

    status: str
    service: str
