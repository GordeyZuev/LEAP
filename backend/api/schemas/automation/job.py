"""Schemas for automation job CRUD operations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common.pagination import PaginatedResponse

from .filters import AutomationFilters
from .schedule import Schedule


class SyncConfig(BaseModel):
    """Configuration for source synchronization."""

    sync_days: int = Field(default=2, ge=1, le=30, description="Sync recordings from last N days")


class AutomationJobCreate(BaseModel):
    """Schema for creating new automation job."""

    name: str = Field(min_length=1, max_length=200, description="Job name")
    description: str | None = Field(default=None, description="Job description")
    template_ids: list[int] = Field(min_length=1, description="Template IDs to use (required, non-empty)")
    schedule: Schedule = Field(description="Schedule configuration")
    sync_config: SyncConfig = Field(default_factory=SyncConfig, description="Sync configuration")
    filters: AutomationFilters | None = Field(None, description="Filters to select recordings for processing")
    processing_config: dict | None = Field(
        None,
        description="Override config (highest priority in automation context)",
    )


class AutomationJobUpdate(BaseModel):
    """Schema for updating automation job."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    template_ids: list[int] | None = None
    schedule: Schedule | None = None
    sync_config: SyncConfig | None = None
    filters: AutomationFilters | None = None
    processing_config: dict | None = None
    is_active: bool | None = None


class AutomationJobListItem(BaseModel):
    """Lightweight job for list views (excludes schedule, config, filters)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_active: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    run_count: int
    created_at: datetime
    updated_at: datetime


class AutomationJobResponse(BaseModel):
    """Full job detail including schedule, config, filters."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    name: str
    description: str | None
    template_ids: list[int]
    schedule: dict
    sync_config: dict
    filters: dict | None
    processing_config: dict | None
    is_active: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    run_count: int
    created_at: datetime
    updated_at: datetime


class JobListResponse(PaginatedResponse):
    """Paginated list of automation jobs."""

    items: list[AutomationJobListItem]


class DryRunResult(BaseModel):
    """Result of dry-run preview."""

    job_id: int
    estimated_new_recordings: int = Field(description="Estimated number of new recordings to sync")
    estimated_matched_recordings: int = Field(description="Estimated number of recordings that will match templates")
    templates_to_apply: list[int] = Field(description="Template IDs that will be applied")
    estimated_duration_minutes: int = Field(description="Estimated total duration in minutes")
