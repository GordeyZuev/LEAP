"""Admin statistics schemas"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common.pagination import PaginatedResponse


class AdminOverviewStats(BaseModel):
    """Overall platform statistics."""

    total_users: int = Field(..., description="Total users")
    active_users: int = Field(..., description="Active users")
    total_recordings: int = Field(..., description="Total recordings")
    total_storage_gb: float = Field(..., description="Total storage used (GB)")
    total_plans: int = Field(..., description="Total plans")
    users_by_plan: dict[str, int] = Field(..., description="Distribution of users by plans")
    exceeding_users_count: int = Field(0, description="Users currently exceeding recordings quota")
    total_share_views: int = Field(0, description="Total public share page views (all time)")
    total_share_downloads: int = Field(0, description="Total public share downloads (all time)")
    active_share_links: int = Field(0, description="Recordings with an active share token")


class UserQuotaDetails(BaseModel):
    """Detailed information about user quotas."""

    user_id: str
    email: str
    plan_name: str
    recordings_used: int
    recordings_limit: int | None
    storage_used_gb: float
    storage_limit_gb: int | None
    is_exceeding: bool = Field(..., description="Are quotas exceeded")
    overage_enabled: bool
    overage_cost: Decimal = Field(default=Decimal("0"))
    share_views_total: int = Field(0, description="Total share views across user's recordings")
    share_downloads_total: int = Field(0, description="Total share downloads across user's recordings")


class AdminUserStats(BaseModel):
    """Statistics by users with filters."""

    total_count: int
    users: list[UserQuotaDetails]
    page: int = 1
    page_size: int = 50


class PlanUsageStats(BaseModel):
    """Statistics of usage by plan."""

    plan_name: str
    total_users: int
    total_recordings: int
    total_storage_gb: float
    avg_recordings_per_user: float
    avg_storage_per_user_gb: float


class AdminQuotaStats(BaseModel):
    """Statistics of quota usage."""

    period: int = Field(..., description="Period (YYYYMM)")
    total_recordings: int
    total_storage_gb: float
    total_overage_cost: Decimal
    plans: list[PlanUsageStats]


# ============================================================
# Admin user management schemas
# ============================================================


class AdminUserProfile(BaseModel):
    """Full user profile for admin view."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    user_slug: int
    role: str
    is_active: bool
    is_verified: bool
    can_transcribe: bool
    can_process_video: bool
    can_upload: bool
    can_update_uploaded_videos: bool
    can_export_data: bool
    created_at: datetime
    last_login_at: datetime | None = None


class AdminUserUpdate(BaseModel):
    """Patch payload for user attributes (admin only)."""

    role: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
    can_transcribe: bool | None = None
    can_process_video: bool | None = None
    can_upload: bool | None = None
    can_update_uploaded_videos: bool | None = None
    can_export_data: bool | None = None


class AdminUserListResponse(BaseModel):
    total_count: int
    users: list[AdminUserProfile]
    page: int
    page_size: int


class UsageEventResponse(BaseModel):
    """Single usage event for history view."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    recording_id: int | None = None
    duration_seconds: float | None = None
    bytes_delta: int | None = None
    event_metadata: dict | None = None
    created_at: datetime


class AdminSubscriptionSet(BaseModel):
    """Set or update a user's subscription."""

    plan_id: int
    custom_max_recordings_per_month: int | None = None
    custom_max_storage_gb: int | None = None
    custom_max_concurrent_tasks: int | None = None
    custom_max_automation_jobs: int | None = None
    custom_min_automation_interval_hours: int | None = None
    custom_max_templates: int | None = None
    custom_max_credentials: int | None = None


class AuditLogItem(BaseModel):
    """One administrative action, as shown on the admin screen."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_email: str
    action: str
    target_user_id: str | None = None
    target_label: str | None = None
    details: dict | None = None
    ip_address: str | None = None
    created_at: datetime


class AuditLogListResponse(PaginatedResponse):
    """Paginated administrative audit trail."""

    items: list[AuditLogItem]
