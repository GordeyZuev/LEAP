"""Base reusable response schemas."""

from pydantic import BaseModel

from .config import BASE_MODEL_CONFIG


class MessageResponse(BaseModel):
    """Simple response with message."""

    model_config = BASE_MODEL_CONFIG

    message: str
    detail: str | None = None


class SuccessResponse(BaseModel):
    """Standard success response."""

    model_config = BASE_MODEL_CONFIG

    success: bool
    message: str | None = None


class TaskQueuedResponse(BaseModel):
    """Response when task is queued."""

    model_config = BASE_MODEL_CONFIG

    task_id: str
    status: str = "queued"
    message: str | None = None


class TaskInfo(BaseModel):
    """Information about task in bulk operation."""

    model_config = BASE_MODEL_CONFIG

    task_id: str
    recording_id: int | None = None
    status: str = "queued"


class BulkOperationResponse(BaseModel):
    """Result of bulk operation."""

    model_config = BASE_MODEL_CONFIG

    queued_count: int
    skipped_count: int
    total: int | None = None
    tasks: list[TaskInfo] | None = None
