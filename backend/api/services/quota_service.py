"""Quota and subscription service."""

import copy
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from api.repositories.subscription_repos import (
    QuotaUsageRepository,
    SubscriptionPlanRepository,
    UserSubscriptionRepository,
)
from api.schemas.auth import (
    QuotaStatusResponse,
    SubscriptionPlanResponse,
    UserSubscriptionResponse,
)
from config.settings import DEFAULT_QUOTAS, get_settings
from file_storage.path_builder import StoragePathBuilder
from logger import get_logger

logger = get_logger()


class QuotaService:
    """Service for checking and managing quotas.

    Default limits are defined in ``config.settings.DEFAULT_QUOTAS``.
    Per-user overrides come from ``user_subscriptions.custom_max_*`` + plan.
    Monthly usage counters are tracked in ``quota_usage``.
    Storage is calculated on-the-fly from the user folder on disk.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.subscription_repo = UserSubscriptionRepository(session)
        self.plan_repo = SubscriptionPlanRepository(session)
        self.usage_repo = QuotaUsageRepository(session)

    # ========================================
    # EFFECTIVE QUOTAS (plan + custom overrides)
    # ========================================

    async def get_effective_quotas(self, user_id: str) -> dict[str, int | None]:
        """Return effective limits for a user.

        Priority: ``custom_max_*`` override > plan defaults > ``DEFAULT_QUOTAS`` constant.
        """
        subscription = await self.subscription_repo.get_by_user_id(user_id)

        if not subscription:
            return copy.deepcopy(DEFAULT_QUOTAS)

        plan = await self.plan_repo.get_by_id(subscription.plan_id)
        if not plan:
            raise ValueError(f"Plan {subscription.plan_id} not found")

        return {
            "max_recordings_per_month": subscription.custom_max_recordings_per_month
            or plan.included_recordings_per_month,
            "max_storage_gb": subscription.custom_max_storage_gb or plan.included_storage_gb,
            "max_concurrent_tasks": subscription.custom_max_concurrent_tasks or plan.max_concurrent_tasks,
            "max_automation_jobs": subscription.custom_max_automation_jobs or plan.max_automation_jobs,
            "min_automation_interval_hours": subscription.custom_min_automation_interval_hours
            or plan.min_automation_interval_hours,
        }

    # ========================================
    # QUOTA CHECKS
    # ========================================

    async def check_recordings_quota(self, user_id: str) -> tuple[bool, str | None]:
        """Check if user can create a new recording this month."""
        quotas = await self.get_effective_quotas(user_id)
        max_recordings = quotas["max_recordings_per_month"]

        if max_recordings is None:
            return True, None

        current_period = int(datetime.now().strftime("%Y%m"))
        usage = await self.usage_repo.get_by_user_and_period(user_id, current_period)
        current_count = usage.recordings_count if usage else 0

        if current_count >= max_recordings:
            return False, f"Monthly recordings quota exceeded: {max_recordings}/month"

        return True, None

    async def check_storage_quota(self, user_id: str, user_slug: int) -> tuple[bool, str | None]:
        """Check if user has exceeded their storage limit (calculated from disk)."""
        quotas = await self.get_effective_quotas(user_id)
        max_storage_gb = quotas["max_storage_gb"]

        if max_storage_gb is None:
            return True, None

        storage_bytes = self._calc_storage_bytes(user_slug)
        max_bytes = max_storage_gb * 1024 * 1024 * 1024

        if storage_bytes >= max_bytes:
            used_gb = round(storage_bytes / (1024**3), 2)
            return False, f"Storage quota exceeded: {used_gb}/{max_storage_gb} GB"

        return True, None

    async def check_concurrent_tasks_quota(self, user_id: str) -> tuple[bool, str | None]:
        """Check if user can start another concurrent task."""
        quotas = await self.get_effective_quotas(user_id)
        max_tasks = quotas["max_concurrent_tasks"]

        if max_tasks is None:
            return True, None

        current_period = int(datetime.now().strftime("%Y%m"))
        usage = await self.usage_repo.get_by_user_and_period(user_id, current_period)
        current_tasks = usage.concurrent_tasks_count if usage else 0

        if current_tasks >= max_tasks:
            return False, f"Concurrent tasks limit exceeded: {max_tasks}"

        return True, None

    # ========================================
    # USAGE TRACKING
    # ========================================

    async def track_recording_created(self, user_id: str) -> None:
        """Increment monthly recording counter."""
        current_period = int(datetime.now().strftime("%Y%m"))
        await self.usage_repo.increment_recordings(user_id, current_period, count=1)

    async def set_concurrent_tasks_count(self, user_id: str, count: int) -> None:
        """Set current concurrent tasks count."""
        current_period = int(datetime.now().strftime("%Y%m"))
        await self.usage_repo.set_concurrent_tasks(user_id, current_period, count)

    # ========================================
    # QUOTA STATUS (for GET /me/quota)
    # ========================================

    async def get_quota_status(self, user_id: str, user_slug: int) -> QuotaStatusResponse:
        """Build a full quota status response for the user."""
        # Effective limits
        quotas = await self.get_effective_quotas(user_id)

        # Current monthly usage
        current_period = int(datetime.now().strftime("%Y%m"))
        usage = await self.usage_repo.get_by_user_and_period(user_id, current_period)

        recordings_used = usage.recordings_count if usage else 0
        tasks_used = usage.concurrent_tasks_count if usage else 0
        storage_bytes = self._calc_storage_bytes(user_slug)
        storage_gb = round(storage_bytes / (1024**3), 3)

        max_recordings = quotas["max_recordings_per_month"]
        max_storage_gb = quotas["max_storage_gb"]
        max_tasks = quotas["max_concurrent_tasks"]
        max_jobs = quotas["max_automation_jobs"]

        # Subscription info (optional)
        subscription = await self.subscription_repo.get_by_user_id(user_id)
        subscription_response = None
        if subscription:
            plan = await self.plan_repo.get_by_id(subscription.plan_id)
            if plan:
                subscription_response = UserSubscriptionResponse(
                    id=subscription.id,
                    user_id=subscription.user_id,
                    plan=SubscriptionPlanResponse.model_validate(plan),
                    custom_max_recordings_per_month=subscription.custom_max_recordings_per_month,
                    custom_max_storage_gb=subscription.custom_max_storage_gb,
                    custom_max_concurrent_tasks=subscription.custom_max_concurrent_tasks,
                    custom_max_automation_jobs=subscription.custom_max_automation_jobs,
                    custom_min_automation_interval_hours=subscription.custom_min_automation_interval_hours,
                    effective_max_recordings_per_month=quotas["max_recordings_per_month"],
                    effective_max_storage_gb=quotas["max_storage_gb"],
                    effective_max_concurrent_tasks=quotas["max_concurrent_tasks"],
                    effective_max_automation_jobs=quotas["max_automation_jobs"],
                    effective_min_automation_interval_hours=quotas["min_automation_interval_hours"],
                    pay_as_you_go_enabled=subscription.pay_as_you_go_enabled,
                    pay_as_you_go_monthly_limit=subscription.pay_as_you_go_monthly_limit,
                    starts_at=subscription.starts_at,
                    expires_at=subscription.expires_at,
                )

        return QuotaStatusResponse(
            subscription=subscription_response,
            current_usage=None,
            recordings={
                "used": recordings_used,
                "limit": max_recordings,
                "available": max_recordings - recordings_used if max_recordings else None,
            },
            storage={
                "used_gb": storage_gb,
                "limit_gb": max_storage_gb,
                "available_gb": round(max_storage_gb - storage_gb, 3) if max_storage_gb else None,
            },
            concurrent_tasks={
                "used": tasks_used,
                "limit": max_tasks,
                "available": max_tasks - tasks_used if max_tasks else None,
            },
            automation_jobs={
                "used": 0,
                "limit": max_jobs,
                "available": max_jobs if max_jobs else None,
            },
            is_overage_enabled=False,
            overage_cost_this_month=Decimal("0"),
            overage_limit=None,
        )

    # ========================================
    # HELPERS
    # ========================================

    @staticmethod
    def _calc_storage_bytes(user_slug: int) -> int:
        """Calculate total disk usage for a user's storage folder."""
        settings = get_settings()
        builder = StoragePathBuilder(settings.storage.local_path)
        return builder.calc_user_storage_bytes(user_slug)
