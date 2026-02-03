"""Schemas for input source sync operations."""

from pydantic import BaseModel

from api.schemas.common import BASE_MODEL_CONFIG


class SyncSourceResponse(BaseModel):
    model_config = BASE_MODEL_CONFIG

    status: str
    recordings_found: int | None = None
    recordings_saved: int | None = None
    recordings_updated: int | None = None
    error: str | None = None


class SyncTaskResponse(BaseModel):
    model_config = BASE_MODEL_CONFIG

    task_id: str
    status: str
    message: str | None = None
