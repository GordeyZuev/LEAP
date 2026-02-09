"""Base reusable response schemas."""

from pydantic import BaseModel, Field

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


class BulkIdsRequest(BaseModel):
    """Request for bulk operations by IDs."""

    model_config = BASE_MODEL_CONFIG

    ids: list[int] = Field(..., min_length=1, max_length=100, description="List of resource IDs")


class BulkDeleteResult(BaseModel):
    """Result of bulk delete operation."""

    model_config = BASE_MODEL_CONFIG

    deleted_count: int
    skipped_count: int
    details: list[dict]
