"""Platform management admin endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.admin import get_current_admin
from api.dependencies import get_db_session
from api.schemas.admin import (
    AdminOverviewStats,
    AdminQuotaStats,
    AdminUserStats,
    PlanUsageStats,
    UserQuotaDetails,
)
from api.schemas.auth import UserInDB
from config.settings import get_settings
from database.auth_models import (
    QuotaUsageModel,
    SubscriptionPlanModel,
    UserModel,
    UserSubscriptionModel,
)
from database.models import RecordingModel
from file_storage.path_builder import StoragePathBuilder
from logger import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


def _user_storage_bytes(user_slug: int) -> int:
    """Calculate disk usage for a single user folder."""
    settings = get_settings()
    builder = StoragePathBuilder(settings.storage.local_path)
    return builder.calc_user_storage_bytes(user_slug)


@router.get("/stats/overview", response_model=AdminOverviewStats)
async def get_overview_stats(
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
):
    """Get platform overview statistics (admin only).

    Recording count comes from the recordings table, storage from disk.
    """
    total_users = await session.scalar(select(func.count(UserModel.id))) or 0
    active_users = (
        await session.scalar(select(func.count(UserModel.id)).where(UserModel.is_active == True))  # noqa: E712
        or 0
    )
    total_recordings = (
        await session.scalar(select(func.count(RecordingModel.id)).where(RecordingModel.deleted.is_(False))) or 0
    )

    total_plans = (
        await session.scalar(
            select(func.count(SubscriptionPlanModel.id)).where(SubscriptionPlanModel.is_active == True)  # noqa: E712
        )
        or 0
    )

    # Users by plan
    result = await session.execute(
        select(SubscriptionPlanModel.name, func.count(UserSubscriptionModel.user_id))
        .join(UserSubscriptionModel, SubscriptionPlanModel.id == UserSubscriptionModel.plan_id)
        .group_by(SubscriptionPlanModel.name)
    )
    users_by_plan = {row[0]: row[1] for row in result.all()}

    # Total storage from disk (all user folders)
    rows = await session.execute(select(UserModel.user_slug))
    total_storage = sum(_user_storage_bytes(row[0]) for row in rows.all())

    return AdminOverviewStats(
        total_users=total_users,
        active_users=active_users,
        total_recordings=total_recordings,
        total_storage_gb=round(total_storage / (1024**3), 2),
        total_plans=total_plans,
        users_by_plan=users_by_plan,
    )


@router.get("/stats/users", response_model=AdminUserStats)
async def get_user_stats(
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Page size"),
    exceeded_only: bool = Query(False, description="Only users exceeding quotas"),
    plan_name: str | None = Query(None, description="Filter by plan name"),
):
    """Get detailed per-user statistics (admin only).

    Recording counts from DB, storage from disk, limits from plan + overrides.
    """
    current_period = int(datetime.now().strftime("%Y%m"))

    query = (
        select(
            UserModel.id,
            UserModel.email,
            UserModel.user_slug,
            SubscriptionPlanModel.name.label("plan_name"),
            SubscriptionPlanModel.included_recordings_per_month,
            SubscriptionPlanModel.included_storage_gb,
            UserSubscriptionModel.custom_max_recordings_per_month,
            UserSubscriptionModel.custom_max_storage_gb,
            UserSubscriptionModel.pay_as_you_go_enabled,
            QuotaUsageModel.recordings_count,
        )
        .join(UserSubscriptionModel, UserModel.id == UserSubscriptionModel.user_id)
        .join(SubscriptionPlanModel, UserSubscriptionModel.plan_id == SubscriptionPlanModel.id)
        .outerjoin(
            QuotaUsageModel,
            (QuotaUsageModel.user_id == UserModel.id) & (QuotaUsageModel.period == current_period),
        )
    )

    if plan_name:
        query = query.where(SubscriptionPlanModel.name == plan_name)

    total_count = await session.scalar(select(func.count()).select_from(query.subquery())) or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await session.execute(query)
    rows = result.all()

    users = []
    for row in rows:
        user_id, email, user_slug, plan, plan_rec, plan_stor, custom_rec, custom_stor, payg, rec_count = row

        recordings_limit = custom_rec or plan_rec
        storage_limit_gb = custom_stor or plan_stor
        recordings_used = rec_count or 0
        storage_bytes = _user_storage_bytes(user_slug)
        storage_gb = round(storage_bytes / (1024**3), 2)

        is_exceeding = (recordings_limit is not None and recordings_used > recordings_limit) or (
            storage_limit_gb is not None and storage_gb > storage_limit_gb
        )

        if exceeded_only and not is_exceeding:
            continue

        users.append(
            UserQuotaDetails(
                user_id=user_id,
                email=email,
                plan_name=plan,
                recordings_used=recordings_used,
                recordings_limit=recordings_limit,
                storage_used_gb=storage_gb,
                storage_limit_gb=storage_limit_gb,
                is_exceeding=is_exceeding,
                overage_enabled=payg,
                overage_cost=0,
            )
        )

    return AdminUserStats(total_count=total_count, users=users, page=page, page_size=page_size)


@router.get("/stats/quotas", response_model=AdminQuotaStats)
async def get_quota_stats(
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
    period: int | None = Query(None, description="Period (YYYYMM), defaults to current"),
):
    """Get quota usage aggregated by plan (admin only)."""
    from utils.date_utils import InvalidPeriodError, validate_period

    if not period:
        period = int(datetime.now().strftime("%Y%m"))
    else:
        try:
            period = validate_period(period)
        except InvalidPeriodError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Total recordings from quota_usage for this period
    totals = await session.execute(
        select(func.sum(QuotaUsageModel.recordings_count)).where(QuotaUsageModel.period == period)
    )
    total_recordings = totals.scalar() or 0

    # Total storage from disk
    rows = await session.execute(select(UserModel.user_slug))
    total_storage = sum(_user_storage_bytes(row[0]) for row in rows.all())

    # Per-plan breakdown
    result = await session.execute(
        select(
            SubscriptionPlanModel.name,
            func.count(UserSubscriptionModel.user_id).label("total_users"),
            func.sum(QuotaUsageModel.recordings_count).label("total_recordings"),
        )
        .join(UserSubscriptionModel, SubscriptionPlanModel.id == UserSubscriptionModel.plan_id)
        .outerjoin(
            QuotaUsageModel,
            (QuotaUsageModel.user_id == UserSubscriptionModel.user_id) & (QuotaUsageModel.period == period),
        )
        .group_by(SubscriptionPlanModel.name)
    )

    plans = [
        PlanUsageStats(
            plan_name=row[0],
            total_users=row[1],
            total_recordings=row[2] or 0,
            total_storage_gb=0,  # Plan-level storage breakdown not available without per-user scan
            avg_recordings_per_user=round((row[2] or 0) / row[1], 2) if row[1] > 0 else 0,
            avg_storage_per_user_gb=0,
        )
        for row in result.all()
    ]

    return AdminQuotaStats(
        period=period,
        total_recordings=total_recordings,
        total_storage_gb=round(total_storage / (1024**3), 2),
        total_overage_cost=0,
        plans=plans,
    )
