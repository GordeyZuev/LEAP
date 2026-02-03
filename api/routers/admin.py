"""Platform management admin endpoints"""

from datetime import datetime
from decimal import Decimal

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
from database.auth_models import (
    QuotaUsageModel,
    SubscriptionPlanModel,
    UserModel,
    UserSubscriptionModel,
)
from logger import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


@router.get("/stats/overview", response_model=AdminOverviewStats)
async def get_overview_stats(
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
):
    """Get platform overview statistics (admin only)."""
    from database.models import RecordingModel

    current_period = int(datetime.now().strftime("%Y%m"))

    total_users = await session.scalar(select(func.count(UserModel.id))) or 0
    active_users = await session.scalar(select(func.count(UserModel.id)).where(UserModel.is_active == True)) or 0  # noqa: E712
    total_recordings = await session.scalar(select(func.count(RecordingModel.id))) or 0
    total_storage_bytes = (
        await session.scalar(
            select(func.sum(QuotaUsageModel.storage_bytes)).where(QuotaUsageModel.period == current_period)
        )
        or 0
    )
    total_plans = (
        await session.scalar(
            select(func.count(SubscriptionPlanModel.id)).where(SubscriptionPlanModel.is_active == True)  # noqa: E712
        )
        or 0
    )

    result = await session.execute(
        select(SubscriptionPlanModel.name, func.count(UserSubscriptionModel.user_id))
        .join(UserSubscriptionModel, SubscriptionPlanModel.id == UserSubscriptionModel.plan_id)
        .group_by(SubscriptionPlanModel.name)
    )
    users_by_plan = {row[0]: row[1] for row in result.all()}

    return AdminOverviewStats(
        total_users=total_users,
        active_users=active_users,
        total_recordings=total_recordings,
        total_storage_gb=round(total_storage_bytes / (1024**3), 2),
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
    """Get detailed user statistics with quota information (admin only)."""
    current_period = int(datetime.now().strftime("%Y%m"))

    query = (
        select(
            UserModel.id,
            UserModel.email,
            SubscriptionPlanModel.name.label("plan_name"),
            SubscriptionPlanModel.included_recordings_per_month,
            SubscriptionPlanModel.included_storage_gb,
            UserSubscriptionModel.custom_max_recordings_per_month,
            UserSubscriptionModel.custom_max_storage_gb,
            UserSubscriptionModel.pay_as_you_go_enabled,
            QuotaUsageModel.recordings_count,
            QuotaUsageModel.storage_bytes,
            QuotaUsageModel.overage_cost,
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
        recordings_limit = row[5] or row[3]
        storage_limit = row[6] or row[4]
        recordings_used = row[8] or 0
        storage_bytes_used = row[9] or 0

        is_exceeding = (
            (recordings_limit is not None and recordings_used > recordings_limit)
            or (storage_limit is not None and (storage_bytes_used / (1024**3)) > storage_limit)
        )

        if exceeded_only and not is_exceeding:
            continue

        users.append(
            UserQuotaDetails(
                user_id=row[0],
                email=row[1],
                plan_name=row[2],
                recordings_used=recordings_used,
                recordings_limit=recordings_limit,
                storage_used_gb=round(storage_bytes_used / (1024**3), 2),
                storage_limit_gb=storage_limit,
                is_exceeding=is_exceeding,
                overage_enabled=row[7],
                overage_cost=row[10] or Decimal("0"),
            )
        )

    return AdminUserStats(total_count=total_count, users=users, page=page, page_size=page_size)


@router.get("/stats/quotas", response_model=AdminQuotaStats)
async def get_quota_stats(
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
    period: int | None = Query(None, description="Period (YYYYMM), defaults to current"),
):
    """Get quota usage statistics by plan (admin only)."""
    from utils.date_utils import InvalidPeriodError, validate_period

    if not period:
        period = int(datetime.now().strftime("%Y%m"))
    else:
        try:
            period = validate_period(period)
        except InvalidPeriodError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    result = await session.execute(
        select(
            func.sum(QuotaUsageModel.recordings_count),
            func.sum(QuotaUsageModel.storage_bytes),
            func.sum(QuotaUsageModel.overage_cost),
        ).where(QuotaUsageModel.period == period)
    )
    row = result.first()
    total_recordings = row[0] or 0
    total_storage_bytes = row[1] or 0
    total_overage_cost = row[2] or Decimal("0")

    result = await session.execute(
        select(
            SubscriptionPlanModel.name,
            func.count(UserSubscriptionModel.user_id).label("total_users"),
            func.sum(QuotaUsageModel.recordings_count).label("total_recordings"),
            func.sum(QuotaUsageModel.storage_bytes).label("total_storage"),
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
            total_storage_gb=round((row[3] or 0) / (1024**3), 2),
            avg_recordings_per_user=round((row[2] or 0) / row[1], 2) if row[1] > 0 else 0,
            avg_storage_per_user_gb=round(((row[3] or 0) / (1024**3)) / row[1], 2) if row[1] > 0 else 0,
        )
        for row in result.all()
    ]

    return AdminQuotaStats(
        period=period,
        total_recordings=total_recordings,
        total_storage_gb=round(total_storage_bytes / (1024**3), 2),
        total_overage_cost=total_overage_cost,
        plans=plans,
    )
