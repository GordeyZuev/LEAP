"""Pydantic schemas for user quotas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserQuotaBase(BaseModel):
    """Base schema for quotas."""

    max_recordings_per_month: int = Field(100, ge=0, description="Max recordings per month")
    max_storage_gb: int = Field(50, ge=0, description="Max storage on disk (GB)")
    max_concurrent_tasks: int = Field(3, ge=1, description="Max concurrent tasks")


class UserQuotaCreate(UserQuotaBase):
    """Schema for creating quotas."""

    user_id: str


class UserQuotaUpdate(BaseModel):
    """Schema for updating quotas."""

    max_recordings_per_month: int | None = Field(None, ge=0)
    max_storage_gb: int | None = Field(None, ge=0)
    max_concurrent_tasks: int | None = Field(None, ge=1)
    current_recordings_count: int | None = Field(None, ge=0)
    current_storage_gb: float | None = Field(None, ge=0)
    current_tasks_count: int | None = Field(None, ge=0)
    quota_reset_at: datetime | None = None


class UserQuotaInDB(UserQuotaBase):
    """Schema of quotas in DB."""

    id: int
    user_id: str
    current_recordings_count: int = 0
    current_storage_gb: float = 0.0
    current_tasks_count: int = 0
    quota_reset_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserQuotaResponse(BaseModel):
    """Schema of response with quotas."""

    max_recordings_per_month: int
    max_storage_gb: int
    max_concurrent_tasks: int
    current_recordings_count: int
    current_storage_gb: float
    current_tasks_count: int
    quota_reset_at: datetime

    model_config = ConfigDict(from_attributes=True)
