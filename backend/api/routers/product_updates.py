"""Public product news, optional newsletter subscriptions, and feedback."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select, text, update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.admin import get_current_admin
from api.auth.device import extract_client_ip
from api.dependencies import get_db_session, get_email_service
from api.repositories.audit_repo import AdminAuditLogRepository
from api.schemas.auth import UserInDB
from api.schemas.product_updates import (
    NewsletterPreferencesRequest,
    NewsletterPreferencesResponse,
    NewsletterSubscribeRequest,
    NewsletterSubscriptionResponse,
    NewsletterTokenRequest,
    ProductFeedbackAdmin,
    ProductFeedbackRequest,
    ProductNewsAudienceCount,
    ProductNewsStats,
    ProductUpdateAdmin,
    ProductUpdatePublic,
    ProductUpdateWrite,
)
from api.services.product_updates import frontend_url, token_hash, verified_subscription_id, verified_unsubscribe_id
from database.product_update_models import (
    NewsletterSubscriptionModel,
    ProductFeedbackModel,
    ProductUpdateDeliveryModel,
    ProductUpdateModel,
)
from logger import get_logger

logger = get_logger("product-updates")
router = APIRouter(tags=["Product news"])

INTERESTS = ("viewers", "course_publishing", "video_processing")


async def _dispatch_update(update_id: str) -> None:
    """Queue delivery only after the recipient snapshot commits."""
    from api.tasks.product_updates import send_product_update_batch

    try:
        send_product_update_batch.delay(update_id)
    except Exception as exc:
        # Delivery rows remain pending and can be safely queued again from Admin.
        logger.error("Could not queue product update id={} ({})", update_id, type(exc).__name__)


@router.get("/api/v1/product-updates", response_model=list[ProductUpdatePublic])
async def list_public_updates(
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(100, ge=1, le=200),
):
    result = await session.execute(
        select(ProductUpdateModel)
        .where(ProductUpdateModel.is_published.is_(True))
        .order_by(ProductUpdateModel.release_date.desc().nulls_last(), ProductUpdateModel.id.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.post(
    "/api/v1/product-news/subscribe",
    response_model=NewsletterSubscriptionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def subscribe_to_product_news(
    data: NewsletterSubscribeRequest,
    session: AsyncSession = Depends(get_db_session),
):
    email = str(data.email).strip().lower()
    subscription = await session.scalar(
        select(NewsletterSubscriptionModel).where(NewsletterSubscriptionModel.email == email).with_for_update()
    )
    now = datetime.now(UTC)
    if subscription and subscription.status == "confirmed":
        # Do not reveal whether an address is subscribed, and do not silently change
        # an existing subscriber's preferences from an unauthenticated form.
        return {"message": "If the address can be subscribed, a confirmation email will arrive shortly."}
    if subscription and subscription.status == "pending" and subscription.updated_at >= now - timedelta(seconds=60):
        return {"message": "If the address can be subscribed, a confirmation email will arrive shortly."}

    email_service = get_email_service()
    if not email_service.product_news_ready:
        raise HTTPException(
            status_code=503,
            detail="Product-news email requires configured SMTP and a public HTTPS frontend URL in EMAIL_BASE_URL.",
        )

    confirmation_token = secrets.token_urlsafe(32)
    if subscription:
        subscription.interests = list(data.interests)
        subscription.status = "pending"
        subscription.confirmation_token_hash = token_hash(confirmation_token)
        subscription.consented_at = now
        subscription.confirmed_at = None
        subscription.unsubscribed_at = None
        subscription.updated_at = now
    else:
        subscription = NewsletterSubscriptionModel(
            email=email,
            interests=list(data.interests),
            status="pending",
            confirmation_token_hash=token_hash(confirmation_token),
            consented_at=now,
        )
        session.add(subscription)
    try:
        await session.commit()
    except IntegrityError as exc:
        # Concurrent first-time opt-ins can race before either creates the row.
        # Keep responses generic; the winning request sends the confirmation.
        await session.rollback()
        if "uq_product_news_subscriptions_email" in str(exc.orig):
            return {"message": "If the address can be subscribed, a confirmation email will arrive shortly."}
        raise

    confirm_url = frontend_url(f"/updates/confirm?token={quote(confirmation_token)}")
    try:
        await email_service.send_product_news_confirmation(email, confirm_url)
    except Exception as exc:
        logger.warning("Product-news confirmation send failed ({})", type(exc).__name__)
        # Allow an immediate retry after a known SMTP failure. The cooldown only
        # suppresses duplicate confirmation emails after successful handoff.
        subscription.updated_at = datetime.now(UTC) - timedelta(seconds=61)
        await session.commit()
        raise HTTPException(
            status_code=503, detail="Could not send confirmation email. Please try again later."
        ) from exc
    return {"message": "If the address can be subscribed, a confirmation email will arrive shortly."}


@router.post("/api/v1/product-news/confirm", response_model=NewsletterSubscriptionResponse)
async def confirm_product_news_subscription(
    data: NewsletterTokenRequest,
    session: AsyncSession = Depends(get_db_session),
):
    subscription = await session.scalar(
        select(NewsletterSubscriptionModel).where(
            NewsletterSubscriptionModel.confirmation_token_hash == token_hash(data.token),
            NewsletterSubscriptionModel.status == "pending",
            NewsletterSubscriptionModel.updated_at >= datetime.now(UTC) - timedelta(hours=24),
        )
    )
    if not subscription:
        raise HTTPException(status_code=400, detail="This confirmation link is invalid or has already been used.")
    subscription.status = "confirmed"
    subscription.confirmed_at = datetime.now(UTC)
    subscription.confirmation_token_hash = None
    subscription.updated_at = datetime.now(UTC)
    await session.commit()
    return {"message": "Your subscription is confirmed."}


@router.post("/api/v1/product-news/unsubscribe", response_model=NewsletterSubscriptionResponse)
async def unsubscribe_from_product_news(
    data: NewsletterTokenRequest,
    session: AsyncSession = Depends(get_db_session),
):
    subscription_id = verified_unsubscribe_id(data.token)
    subscription = await session.get(NewsletterSubscriptionModel, subscription_id) if subscription_id else None
    if subscription and subscription.status != "unsubscribed":
        subscription.status = "unsubscribed"
        subscription.unsubscribed_at = datetime.now(UTC)
        subscription.confirmation_token_hash = None
        subscription.updated_at = datetime.now(UTC)
        await session.commit()
    return {"message": "You have been unsubscribed from LEAP product news."}


@router.put("/api/v1/product-news/preferences", response_model=NewsletterSubscriptionResponse)
async def update_product_news_preferences(
    data: NewsletterPreferencesRequest,
    session: AsyncSession = Depends(get_db_session),
):
    subscription_id = verified_subscription_id(data.token)
    subscription = await session.get(NewsletterSubscriptionModel, subscription_id) if subscription_id else None
    if not subscription or subscription.status != "confirmed":
        raise HTTPException(status_code=400, detail="This subscription link is invalid or no longer active.")
    subscription.interests = list(data.interests)
    subscription.updated_at = datetime.now(UTC)
    await session.commit()
    return {"message": "Your email topics have been updated."}


@router.post("/api/v1/product-news/preferences/validate", response_model=NewsletterPreferencesResponse)
async def get_product_news_preferences(
    data: NewsletterTokenRequest,
    session: AsyncSession = Depends(get_db_session),
):
    subscription_id = verified_subscription_id(data.token)
    subscription = await session.get(NewsletterSubscriptionModel, subscription_id) if subscription_id else None
    if not subscription or subscription.status != "confirmed":
        raise HTTPException(status_code=400, detail="This subscription link is invalid or no longer active.")
    return {"interests": subscription.interests}


@router.post("/api/v1/product-feedback", status_code=status.HTTP_201_CREATED)
async def submit_product_feedback(
    data: ProductFeedbackRequest,
    session: AsyncSession = Depends(get_db_session),
):
    session.add(
        ProductFeedbackModel(
            interests=list(data.interests),
            kind=data.kind,
            message=data.message.strip(),
            reply_email=str(data.reply_email).strip().lower() if data.reply_email else None,
        )
    )
    await session.commit()
    return {"message": "Thank you. Your feedback has been received."}


# Admin-only endpoints -----------------------------------------------------


@router.get("/api/v1/admin/product-updates", response_model=list[ProductUpdateAdmin])
async def admin_list_product_updates(
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
):
    updates = (
        (
            await session.execute(
                select(ProductUpdateModel)
                .order_by(ProductUpdateModel.created_at.desc(), ProductUpdateModel.id.desc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    )
    update_ids = [update.id for update in updates]
    by_update: dict[str, dict[str, int]] = {}
    if update_ids:
        counts = await session.execute(
            select(ProductUpdateDeliveryModel.update_id, ProductUpdateDeliveryModel.status, func.count())
            .where(ProductUpdateDeliveryModel.update_id.in_(update_ids))
            .group_by(ProductUpdateDeliveryModel.update_id, ProductUpdateDeliveryModel.status)
        )
        for update_id, delivery_status, count in counts.all():
            by_update.setdefault(update_id, {})[delivery_status] = count
    return [
        ProductUpdateAdmin.model_validate(update).model_copy(update={"delivery_counts": by_update.get(update.id, {})})
        for update in updates
    ]


@router.post("/api/v1/admin/product-updates", response_model=ProductUpdateAdmin, status_code=201)
async def admin_create_product_update(
    data: ProductUpdateWrite,
    session: AsyncSession = Depends(get_db_session),
    admin: UserInDB = Depends(get_current_admin),
):
    update = ProductUpdateModel(
        version=data.version or None,
        title=data.title.strip(),
        summary=data.summary.strip(),
        audience_bullets=list(data.audience_bullets),
        creator_bullets=list(data.creator_bullets),
        audiences=list(data.audiences),
        newsletter_enabled=data.newsletter_enabled,
        created_by=admin.id,
    )
    session.add(update)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "uq_product_updates_version" in str(exc.orig):
            raise HTTPException(status_code=409, detail="An update with this version already exists") from exc
        raise
    await session.refresh(update)
    return update


@router.patch("/api/v1/admin/product-updates/{update_id}", response_model=ProductUpdateAdmin)
async def admin_edit_product_update(
    update_id: str,
    data: ProductUpdateWrite,
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
):
    update = await session.get(ProductUpdateModel, update_id)
    if not update:
        raise HTTPException(status_code=404, detail="Update not found")
    if update.email_requested_at:
        raise HTTPException(status_code=409, detail="An update cannot be edited after its newsletter is queued")
    update.version = data.version or None
    update.title = data.title.strip()
    update.summary = data.summary.strip()
    update.audience_bullets = list(data.audience_bullets)
    update.creator_bullets = list(data.creator_bullets)
    update.audiences = list(data.audiences)
    update.newsletter_enabled = data.newsletter_enabled
    update.updated_at = datetime.now(UTC)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "uq_product_updates_version" in str(exc.orig):
            raise HTTPException(status_code=409, detail="An update with this version already exists") from exc
        raise
    await session.refresh(update)
    return update


@router.delete("/api/v1/admin/product-updates/{update_id}", status_code=204)
async def admin_delete_product_update(
    update_id: str,
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
):
    update = await session.get(ProductUpdateModel, update_id)
    if not update:
        raise HTTPException(status_code=404, detail="Update not found")
    if update.is_published or update.email_requested_at:
        raise HTTPException(status_code=409, detail="Published updates cannot be deleted")
    await session.delete(update)
    await session.commit()


@router.post("/api/v1/admin/product-updates/{update_id}/publish", response_model=ProductUpdateAdmin)
async def admin_publish_product_update(
    update_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    admin: UserInDB = Depends(get_current_admin),
):
    update = await session.get(ProductUpdateModel, update_id)
    if not update:
        raise HTTPException(status_code=404, detail="Update not found")
    if not update.is_published:
        update.is_published = True
        update.published_at = datetime.now(UTC)
        update.release_date = update.release_date or datetime.now(UTC).date()
        update.updated_at = datetime.now(UTC)
        await AdminAuditLogRepository(session).record(
            actor_id=admin.id,
            actor_email=str(admin.email),
            action="product_update.published",
            target_label=update.title,
            details={"version": update.version},
            ip_address=extract_client_ip(request),
        )
        await session.commit()
        await session.refresh(update)
    return update


@router.post("/api/v1/admin/product-updates/{update_id}/send", response_model=ProductUpdateAdmin)
async def admin_send_product_update(
    update_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    admin: UserInDB = Depends(get_current_admin),
):
    update = await session.scalar(
        select(ProductUpdateModel).where(ProductUpdateModel.id == update_id).with_for_update()
    )
    if not update:
        raise HTTPException(status_code=404, detail="Update not found")
    if not update.is_published:
        raise HTTPException(status_code=409, detail="Publish this update before sending it")
    if not update.newsletter_enabled:
        raise HTTPException(status_code=409, detail="Enable email for this update before sending it")
    if update.email_requested_at:
        raise HTTPException(status_code=409, detail="Email has already been queued for this update")

    if not get_email_service().product_news_ready:
        raise HTTPException(
            status_code=503,
            detail="Product-news email requires configured SMTP and a public HTTPS frontend URL in EMAIL_BASE_URL.",
        )

    query = select(NewsletterSubscriptionModel).where(NewsletterSubscriptionModel.status == "confirmed")
    if update.audiences:
        query = query.where(
            or_(*(NewsletterSubscriptionModel.interests.contains([topic]) for topic in update.audiences))
        )
    subscriptions = (await session.execute(query)).scalars().all()
    if not subscriptions:
        raise HTTPException(status_code=409, detail="There are no confirmed subscribers in the selected audience")

    update.email_requested_at = datetime.now(UTC)
    session.add_all(
        ProductUpdateDeliveryModel(update_id=update.id, subscription_id=sub.id, status="pending")
        for sub in subscriptions
    )
    await AdminAuditLogRepository(session).record(
        actor_id=admin.id,
        actor_email=str(admin.email),
        action="product_update.newsletter_queued",
        target_label=update.title,
        details={"recipient_count": len(subscriptions), "audiences": update.audiences},
        ip_address=extract_client_ip(request),
    )
    await session.commit()
    await session.refresh(update)
    await _dispatch_update(update.id)
    return update


@router.post("/api/v1/admin/product-updates/{update_id}/retry", response_model=ProductUpdateAdmin)
async def admin_retry_product_update(
    update_id: str,
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
):
    update = await session.get(ProductUpdateModel, update_id)
    if not update or not update.email_requested_at:
        raise HTTPException(status_code=404, detail="Mailing not found")
    now = datetime.now(UTC)
    await session.execute(
        sa_update(ProductUpdateDeliveryModel)
        .where(
            ProductUpdateDeliveryModel.update_id == update_id,
            or_(
                ProductUpdateDeliveryModel.status == "failed",
                ProductUpdateDeliveryModel.status == "pending",
                (ProductUpdateDeliveryModel.status == "sending")
                & (ProductUpdateDeliveryModel.updated_at < now - timedelta(minutes=15)),
            ),
        )
        .values(status="pending", last_error=None, updated_at=now)
    )
    await session.commit()
    await _dispatch_update(update.id)
    await session.refresh(update)
    return update


@router.get("/api/v1/admin/product-news/stats", response_model=ProductNewsStats)
async def admin_product_news_stats(
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
):
    result = await session.execute(text("SELECT metric, dimension, value FROM product_communications_current_stats"))
    aggregates: dict[str, dict[str, int]] = {}
    for metric, dimension, value in result.all():
        aggregates.setdefault(str(metric), {})[str(dimension)] = int(value)

    subscription_status = aggregates.get("subscription_status", {})
    delivery_status = aggregates.get("delivery_status", {})
    feedback_kind = aggregates.get("feedback_kind", {})
    subscription_interests: dict[str, int] = dict.fromkeys(INTERESTS, 0)
    subscription_interests.update(aggregates.get("subscription_interest", {}))
    feedback_interests: dict[str, int] = dict.fromkeys(INTERESTS, 0)
    feedback_interests.update(aggregates.get("feedback_interest", {}))
    return ProductNewsStats(
        subscriptions_total=sum(subscription_status.values()),
        subscriptions_pending=subscription_status.get("pending", 0),
        subscriptions_confirmed=subscription_status.get("confirmed", 0),
        subscriptions_unsubscribed=subscription_status.get("unsubscribed", 0),
        interests=subscription_interests,
        feedback_total=sum(feedback_kind.values()),
        feedback_by_kind=feedback_kind,
        feedback_by_interest=feedback_interests,
        delivery_by_status=delivery_status,
    )


@router.get("/api/v1/admin/product-news/audience-count", response_model=ProductNewsAudienceCount)
async def admin_product_news_audience_count(
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
    interests: list[str] = Query(default=[]),
):
    if any(interest not in INTERESTS for interest in interests):
        raise HTTPException(status_code=422, detail="Unknown audience interest")
    query = select(func.count(NewsletterSubscriptionModel.id)).where(NewsletterSubscriptionModel.status == "confirmed")
    if interests:
        query = query.where(or_(*(NewsletterSubscriptionModel.interests.contains([topic]) for topic in interests)))
    return ProductNewsAudienceCount(count=await session.scalar(query) or 0)


@router.get("/api/v1/admin/product-feedback", response_model=list[ProductFeedbackAdmin])
async def admin_list_product_feedback(
    session: AsyncSession = Depends(get_db_session),
    _admin: UserInDB = Depends(get_current_admin),
    limit: int = Query(100, ge=1, le=500),
):
    result = await session.execute(
        select(ProductFeedbackModel)
        .order_by(ProductFeedbackModel.created_at.desc(), ProductFeedbackModel.id.desc())
        .limit(limit)
    )
    return result.scalars().all()
