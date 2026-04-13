"""Celery task status schemas"""

from pydantic import BaseModel, Field

from api.schemas.common import BASE_MODEL_CONFIG


class TaskProgressInfo(BaseModel):
    """Information about progress of task."""

    model_config = BASE_MODEL_CONFIG

    status: str
    progress: int = Field(0, ge=0, le=100, description="Progress of execution (0-100)")
    step: str | None = None


class TaskResult(BaseModel):
    """Result of execution of task."""

    model_config = BASE_MODEL_CONFIG

    recording_id: int | None = None
    output_url: str | None = None
    file_path: str | None = None
    message: str | None = None

    # Additional fields for different types of tasks
    transcription_text: str | None = None
    topics: list[str] | None = None
    duration_seconds: float | None = Field(None, ge=0, description="Duration in seconds")


class TaskStatusResponse(BaseModel):
    """Status of Celery task."""

    model_config = BASE_MODEL_CONFIG

    task_id: str
    state: str
    status: str
    progress: int = Field(0, ge=0, le=100)
    result: dict | None = None
    error: str | None = None


class TaskCancelResponse(BaseModel):
    """Result of cancellation of task."""

    model_config = BASE_MODEL_CONFIG

    task_id: str
    status: str
    message: str
