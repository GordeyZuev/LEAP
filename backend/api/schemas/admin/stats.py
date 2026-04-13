"""Admin statistics schemas"""

from decimal import Decimal

from pydantic import BaseModel, Field


class AdminOverviewStats(BaseModel):
    """Overall platform statistics."""

    total_users: int = Field(..., description="Total users")
    active_users: int = Field(..., description="Active users")
    total_recordings: int = Field(..., description="Total recordings")
    total_storage_gb: float = Field(..., description="Total storage used (GB)")
    total_plans: int = Field(..., description="Total plans")
    users_by_plan: dict[str, int] = Field(..., description="Distribution of users by plans")


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
