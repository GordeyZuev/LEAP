"""Schemas for automation job CRUD operations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common.pagination import PaginatedResponse

from .filters import AutomationFilters
from .schedule import Schedule


class SyncConfig(BaseModel):
    """Configuration for source synchronization and matching window."""

    sync_days: int | None = Field(
        default=2,
        ge=1,
        le=30,
        description="Inclusive last N calendar days in the job timezone. Null = match all rows; API sync still last 30 days when enabled.",
    )
    max_recordings: int | None = Field(
        default=None,
        ge=1,
        le=5000,
        description="Max full pipelines to start per run. Null = unlimited. MTS wait pings are not capped.",
    )
    sync_on_run: bool = Field(default=True, description="Refresh sources from Zoom/MTS before matching")


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
    is_running: bool = False


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
    is_running: bool = False


class JobListResponse(PaginatedResponse):
    """Paginated list of automation jobs."""

    items: list[AutomationJobListItem]


class AffectedRecording(BaseModel):
    """One recording a job run started (or would start, for preview)."""

    id: int
    name: str = ""
    template_id: int
    template_name: str = ""


class JobRunItem(BaseModel):
    """One recorded execution of an automation job."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str = Field(description="RUNNING | SUCCESS | FAILED | SKIPPED")
    trigger: str = Field(description="SCHEDULE | MANUAL")
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: int | None = None
    synced_count: int
    recordings_found: int
    matched_count: int
    processed_count: int
    error: str | None = None
    affected_recordings: list[AffectedRecording] | None = None


class JobRunListResponse(PaginatedResponse):
    """Paginated run history for one job."""

    items: list[JobRunItem]


class DryRunResult(BaseModel):
    """Celery success payload for automation.dry_run (also nested in GET /tasks/{id})."""

    status: str = "success"
    job_id: int
    user_id: str | None = None
    synced_count: int = 0
    sources_synced: list[int] = Field(default_factory=list)
    recordings_found: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    would_process: list[AffectedRecording] = Field(default_factory=list)
