"""Platform management admin endpoints."""

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.admin import get_current_admin
from api.auth.device import extract_client_ip
from api.dependencies import get_db_session
from api.repositories.audit_repo import AdminAuditLogRepository, diff_fields
from api.schemas.admin import (
    AdminOverviewStats,
    AdminQuotaStats,
    AdminSubscriptionSet,
    AdminUserListResponse,
    AdminUserProfile,
    AdminUserStats,
    AdminUserUpdate,
    AuditLogListResponse,
    PlanUsageStats,
    UsageEventResponse,
    UserQuotaDetails,
)
from api.schemas.auth import SubscriptionPlanCreate, SubscriptionPlanUpdate, UserInDB
from api.schemas.common.pagination import paginate_list
from api.services.share_observability import ShareObservabilityService
from database.audit_models import AuditAction
from database.auth_models import (
    QuotaUsageModel,
    SubscriptionPlanModel,
    UserModel,
    UserSubscriptionModel,
)
from database.models import RecordingModel
from file_storage.factory import get_storage_backend
from logger import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


async def _user_storage_bytes(user_slug: int) -> int:
    """Calculate storage usage for a single user folder via the active backend."""
    return await get_storage_backend().get_prefix_size(f"users/user_{user_slug:06d}/")


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

    # Total storage from S3/storage backend (all user folders, concurrent)
    rows = await session.execute(select(UserModel.user_slug))
    slugs = [row[0] for row in rows.all()]
    sizes = await asyncio.gather(*(_user_storage_bytes(s) for s in slugs))
    total_storage = sum(sizes)

    # Users exceeding recordings quota this month (DB-only, no S3 check)
    current_period = int(datetime.now().strftime("%Y%m"))
    recordings_limit_col = func.coalesce(
        UserSubscriptionModel.custom_max_recordings_per_month,
        SubscriptionPlanModel.included_recordings_per_month,
    )
    exceeding_count = (
        await session.scalar(
            select(func.count(QuotaUsageModel.user_id))
            .join(UserSubscriptionModel, QuotaUsageModel.user_id == UserSubscriptionModel.user_id)
            .join(SubscriptionPlanModel, UserSubscriptionModel.plan_id == SubscriptionPlanModel.id)
            .where(
                QuotaUsageModel.period == current_period,
                recordings_limit_col.is_not(None),
                QuotaUsageModel.recordings_count > recordings_limit_col,
            )
        )
        or 0
    )

    total_share_views, total_share_downloads, active_share_links = await ShareObservabilityService.platform_totals()

    return AdminOverviewStats(
        total_users=total_users,
        active_users=active_users,
        total_recordings=total_recordings,
        total_storage_gb=round(total_storage / (1024**3), 2),
        total_plans=total_plans,
        users_by_plan=users_by_plan,
        exceeding_users_count=exceeding_count,
        total_share_views=total_share_views,
        total_share_downloads=total_share_downloads,
        active_share_links=active_share_links,
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

    user_ids = [row[0] for row in rows]
    share_totals: dict[str, tuple[int, int]] = {}
    if user_ids:
        share_result = await session.execute(
            select(
                RecordingModel.user_id,
                func.coalesce(func.sum(RecordingModel.share_view_count), 0),
                func.coalesce(func.sum(RecordingModel.share_download_count), 0),
            )
            .where(RecordingModel.user_id.in_(user_ids))
            .group_by(RecordingModel.user_id)
        )
        share_totals = {
            uid: (int(views or 0), int(downloads or 0)) for uid, views, downloads in share_result.all() if uid
        }

    users = []
    for row in rows:
        user_id, email, user_slug, plan, plan_rec, plan_stor, custom_rec, custom_stor, payg, rec_count = row

        recordings_limit = custom_rec or plan_rec
        storage_limit_gb = custom_stor or plan_stor
        recordings_used = rec_count or 0
        storage_bytes = await _user_storage_bytes(user_slug)
        storage_gb = round(storage_bytes / (1024**3), 2)

        is_exceeding = (recordings_limit is not None and recordings_used > recordings_limit) or (
            storage_limit_gb is not None and storage_gb > storage_limit_gb
        )

        if exceeded_only and not is_exceeding:
            continue

        share_views_total, share_downloads_total = share_totals.get(user_id, (0, 0))

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
                share_views_total=share_views_total,
                share_downloads_total=share_downloads_total,
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

    # Total storage from S3/storage backend
    rows = await session.execute(select(UserModel.user_slug))
    slugs = [row[0] for row in rows.all()]
    sizes = await asyncio.gather(*(_user_storage_bytes(s) for s in slugs))
    total_storage = sum(sizes)

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


# =============================================================================
# User management
# =============================================================================


@router.get("/users", response_model=AdminUserListResponse)
async def admin_list_users(
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, description="Filter by email (substring)"),
    role: str | None = Query(None, description="Filter by role"),
    exceeded_only: bool = Query(False, description="Only users exceeding recordings quota"),
):
    """List all users with pagination (admin only)."""
    query = select(UserModel).order_by(UserModel.created_at.desc())
    if search:
        query = query.where(UserModel.email.ilike(f"%{search}%"))
    if role:
        query = query.where(UserModel.role == role)
    if exceeded_only:
        current_period = int(datetime.now().strftime("%Y%m"))
        recordings_limit_col = func.coalesce(
            UserSubscriptionModel.custom_max_recordings_per_month,
            SubscriptionPlanModel.included_recordings_per_month,
        )
        exceeded_ids_subq = (
            select(QuotaUsageModel.user_id)
            .join(UserSubscriptionModel, QuotaUsageModel.user_id == UserSubscriptionModel.user_id)
            .join(SubscriptionPlanModel, UserSubscriptionModel.plan_id == SubscriptionPlanModel.id)
            .where(
                QuotaUsageModel.period == current_period,
                recordings_limit_col.is_not(None),
                QuotaUsageModel.recordings_count > recordings_limit_col,
            )
        )
        query = query.where(UserModel.id.in_(exceeded_ids_subq))

    total_count = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    users = [AdminUserProfile.model_validate(u) for u in result.scalars().all()]

    return AdminUserListResponse(total_count=total_count, users=users, page=page, page_size=page_size)


@router.get("/users/{user_id}", response_model=AdminUserProfile)
async def admin_get_user(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
):
    """Get a single user's profile (admin only)."""
    result = await session.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AdminUserProfile.model_validate(user)


@router.patch("/users/{user_id}", response_model=AdminUserProfile)
async def admin_update_user(
    request: Request,
    user_id: str,
    data: AdminUserUpdate,
    session: AsyncSession = Depends(get_db_session),
    admin: UserInDB = Depends(get_current_admin),
):
    """Update user role, active state, or feature permissions (admin only)."""
    result = await session.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    updates = data.model_dump(exclude_unset=True)
    before = {field: getattr(user, field, None) for field in updates}
    for field, value in updates.items():
        setattr(user, field, value)

    changes = diff_fields(before, updates)
    if changes:
        await _audit(
            request,
            session,
            admin,
            AuditAction.USER_UPDATED,
            target_user_id=user_id,
            target_label=user.email,
            details=changes,
        )

    await session.commit()
    await session.refresh(user)
    return AdminUserProfile.model_validate(user)


@router.get("/users/{user_id}/events", response_model=list[UsageEventResponse])
async def admin_get_user_events(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
    event_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get usage event history for a user (admin only)."""
    from api.repositories.usage_event_repo import UsageEventRepository

    events = await UsageEventRepository(session).list_for_user(
        user_id, event_type=event_type, limit=limit, offset=offset
    )
    return [UsageEventResponse.model_validate(e) for e in events]


# =============================================================================
# Subscription management
# =============================================================================


@router.get("/users/{user_id}/subscription")
async def admin_get_user_subscription(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
):
    """Get a user's subscription, effective quotas, and current usage (admin only)."""
    from api.repositories.subscription_repos import UserSubscriptionRepository
    from api.services.quota_service import QuotaService

    user = (await session.execute(select(UserModel).where(UserModel.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    quota_service = QuotaService(session)
    quotas = await quota_service.get_effective_quotas(user_id)
    quota_status = await quota_service.get_quota_status(user_id, user.user_slug)
    sub = await UserSubscriptionRepository(session).get_by_user_id(user_id)
    return {
        "user_id": user_id,
        "subscription": sub,
        "effective_quotas": quotas,
        "quota_status": quota_status,
    }


@router.post("/users/{user_id}/subscription", status_code=status.HTTP_201_CREATED)
async def admin_set_user_subscription(
    request: Request,
    user_id: str,
    data: AdminSubscriptionSet,
    session: AsyncSession = Depends(get_db_session),
    admin: UserInDB = Depends(get_current_admin),
):
    """Assign or replace a user's subscription plan (admin only)."""
    from api.repositories.subscription_repos import (
        SubscriptionPlanRepository,
        UserSubscriptionRepository,
    )
    from api.schemas.auth import UserSubscriptionCreate, UserSubscriptionUpdate

    plan = await SubscriptionPlanRepository(session).get_by_id(data.plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan {data.plan_id} not found")

    sub_repo = UserSubscriptionRepository(session)
    existing = await sub_repo.get_by_user_id(user_id)
    payload = data.model_dump(exclude={"plan_id"}, exclude_unset=True)

    if existing:
        update = UserSubscriptionUpdate(plan_id=data.plan_id, **payload)
        sub = await sub_repo.update(user_id, update)
    else:
        create = UserSubscriptionCreate(user_id=user_id, plan_id=data.plan_id, **payload)
        sub = await sub_repo.create(create)

    await _audit(
        request,
        session,
        admin,
        AuditAction.SUBSCRIPTION_ASSIGNED,
        target_user_id=user_id,
        target_label=plan.display_name,
        details={"plan_id": data.plan_id},
    )
    await session.commit()
    return {"user_id": user_id, "subscription": sub}


@router.patch("/users/{user_id}/subscription")
async def admin_patch_user_subscription(
    request: Request,
    user_id: str,
    data: AdminSubscriptionSet,
    session: AsyncSession = Depends(get_db_session),
    admin: UserInDB = Depends(get_current_admin),
):
    """Update custom quota overrides on an existing subscription (admin only)."""
    from api.repositories.subscription_repos import UserSubscriptionRepository
    from api.schemas.auth import UserSubscriptionUpdate

    sub_repo = UserSubscriptionRepository(session)
    existing = await sub_repo.get_by_user_id(user_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    update_data = data.model_dump(exclude_unset=True)
    sub = await sub_repo.update(user_id, UserSubscriptionUpdate(**update_data))
    await _audit(
        request,
        session,
        admin,
        AuditAction.SUBSCRIPTION_UPDATED,
        target_user_id=user_id,
        details=update_data,
    )
    await session.commit()
    return {"user_id": user_id, "subscription": sub}


@router.delete("/users/{user_id}/subscription", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_user_subscription(
    request: Request,
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    admin: UserInDB = Depends(get_current_admin),
) -> None:
    """Remove a user's subscription (admin only). User falls back to DEFAULT_QUOTAS."""
    from api.repositories.subscription_repos import UserSubscriptionRepository

    deleted = await UserSubscriptionRepository(session).delete(user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    await _audit(request, session, admin, AuditAction.SUBSCRIPTION_REMOVED, target_user_id=user_id)
    await session.commit()


async def _audit(
    request: Request,
    session: AsyncSession,
    admin: UserInDB,
    action: str,
    *,
    target_user_id: str | None = None,
    target_label: str | None = None,
    details: dict | None = None,
) -> None:
    """Append one audit entry for the current admin. Caller owns the commit."""
    await AdminAuditLogRepository(session).record(
        actor_id=admin.id,
        actor_email=admin.email,
        action=action,
        target_user_id=target_user_id,
        target_label=target_label,
        details=details,
        ip_address=extract_client_ip(request),
    )


@router.get("/audit-log", response_model=AuditLogListResponse)
async def admin_list_audit_log(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
):
    """Administrative actions, newest first (admin only)."""
    entries = await AdminAuditLogRepository(session).list_recent()
    items, total, total_pages = paginate_list(entries, page, per_page, "created_at", "desc")
    return AuditLogListResponse(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


# =============================================================================
# Plans management
# =============================================================================


@router.get("/plans")
async def admin_list_plans(
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
    active_only: bool = Query(True),
):
    """List subscription plans (admin only)."""
    from api.repositories.subscription_repos import SubscriptionPlanRepository

    plans = await SubscriptionPlanRepository(session).get_all(active_only=active_only)
    return {"plans": plans}


@router.post("/plans", status_code=status.HTTP_201_CREATED)
async def admin_create_plan(
    request: Request,
    data: SubscriptionPlanCreate,
    session: AsyncSession = Depends(get_db_session),
    admin: UserInDB = Depends(get_current_admin),
):
    """Create a subscription plan (admin only)."""
    from api.repositories.subscription_repos import SubscriptionPlanRepository

    plan = await SubscriptionPlanRepository(session).create(data)
    await _audit(request, session, admin, AuditAction.PLAN_CREATED, target_label=plan.display_name)
    await session.commit()
    return {"plan": plan}


@router.patch("/plans/{plan_id}")
async def admin_update_plan(
    request: Request,
    plan_id: int,
    data: SubscriptionPlanUpdate,
    session: AsyncSession = Depends(get_db_session),
    admin: UserInDB = Depends(get_current_admin),
):
    """Update a subscription plan (admin only)."""
    from api.repositories.subscription_repos import SubscriptionPlanRepository

    plan = await SubscriptionPlanRepository(session).update(plan_id, data)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan {plan_id} not found")

    await _audit(
        request,
        session,
        admin,
        AuditAction.PLAN_UPDATED,
        target_label=plan.display_name,
        details=data.model_dump(exclude_unset=True),
    )
    await session.commit()
    return {"plan": plan}
