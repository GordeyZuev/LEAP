"""Schemas for automation operations."""

from pydantic import BaseModel, Field


class TriggerJobResponse(BaseModel):
    """Result of triggering automation job."""

    task_id: str
    mode: str = Field(default="dry_run", description="Mode of triggering (dry_run or execute)")
    message: str
