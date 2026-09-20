"""Background email delivery for product updates."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from urllib.parse import quote

from sqlalchemy import select, update as sa_update

from api.celery_app import celery_app
from api.dependencies import get_async_session_maker, get_email_service
from api.services.product_updates import frontend_url, unsubscribe_token
from database.product_update_models import (
    NewsletterSubscriptionModel,
    ProductUpdateDeliveryModel,
    ProductUpdateModel,
)
from logger import get_logger

logger = get_logger("product-updates.delivery")
BATCH_SIZE = 25


@celery_app.task(
    bind=True,
    name="api.tasks.product_updates.send_batch",
    max_retries=8,
    default_retry_delay=5,
    acks_late=True,
    reject_on_worker_lost=True,
)
def send_product_update_batch(self, update_id: str) -> dict:
    try:
        result = asyncio.run(_send_batch(update_id))
    except Exception as exc:
        logger.warning("Product update delivery batch failed update_id={} ({})", update_id, type(exc).__name__)
        raise self.retry(exc=exc, countdown=min(300, 2 ** min(self.request.retries, 8)))
    if result["remaining"]:
        send_product_update_batch.apply_async(args=[update_id], countdown=1)
    return result


async def _send_batch(update_id: str) -> dict[str, int]:
    session_maker = get_async_session_maker()
    async with session_maker() as session:
        rows = (
            (
                await session.execute(
                    select(ProductUpdateDeliveryModel.id)
                    .where(
                        ProductUpdateDeliveryModel.update_id == update_id,
                        ProductUpdateDeliveryModel.status == "pending",
                    )
                    .order_by(ProductUpdateDeliveryModel.id)
                    .limit(BATCH_SIZE)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            remaining = await session.scalar(
                select(ProductUpdateDeliveryModel.id)
                .where(
                    ProductUpdateDeliveryModel.update_id == update_id,
                    ProductUpdateDeliveryModel.status == "pending",
                )
                .limit(1)
            )
            return {"sent": 0, "failed": 0, "remaining": int(remaining is not None)}
        now = datetime.now(UTC)
        await session.execute(
            sa_update(ProductUpdateDeliveryModel)
            .where(ProductUpdateDeliveryModel.id.in_(rows))
            .values(status="sending", attempts=ProductUpdateDeliveryModel.attempts + 1, updated_at=now)
        )
        await session.commit()

    sent = failed = 0
    for delivery_id in rows:
        async with session_maker() as session:
            result = await session.execute(
                select(ProductUpdateDeliveryModel, NewsletterSubscriptionModel, ProductUpdateModel)
                .join(
                    NewsletterSubscriptionModel,
                    NewsletterSubscriptionModel.id == ProductUpdateDeliveryModel.subscription_id,
                )
                .join(ProductUpdateModel, ProductUpdateModel.id == ProductUpdateDeliveryModel.update_id)
                .where(ProductUpdateDeliveryModel.id == delivery_id)
            )
            item = result.first()
            if not item:
                continue
            delivery, subscription, update = item
            if subscription.status != "confirmed":
                delivery.status = "skipped"
                delivery.updated_at = datetime.now(UTC)
                await session.commit()
                continue

            unsubscribe_url = frontend_url(f"/updates/unsubscribe?token={quote(unsubscribe_token(subscription.id))}")
            preferences_url = frontend_url(f"/updates/preferences?token={quote(unsubscribe_token(subscription.id))}")
            update_url = frontend_url(f"/updates#{update.id}")
            try:
                await get_email_service().send_product_update(
                    subscription.email,
                    update.title,
                    update.summary,
                    update.audience_bullets,
                    update.creator_bullets,
                    update_url,
                    unsubscribe_url,
                    preferences_url,
                )
            except Exception as exc:
                delivery.status = "failed"
                delivery.last_error = type(exc).__name__
                delivery.updated_at = datetime.now(UTC)
                failed += 1
                logger.warning(
                    "Product update email failed update_id={} delivery_id={} ({})",
                    update.id,
                    delivery.id,
                    type(exc).__name__,
                )
            else:
                delivery.status = "sent"
                delivery.last_error = None
                delivery.sent_at = datetime.now(UTC)
                delivery.updated_at = delivery.sent_at
                sent += 1
            await session.commit()

    async with session_maker() as session:
        remaining = await session.scalar(
            select(ProductUpdateDeliveryModel.id)
            .where(
                ProductUpdateDeliveryModel.update_id == update_id,
                ProductUpdateDeliveryModel.status == "pending",
            )
            .limit(1)
        )
    return {"sent": sent, "failed": failed, "remaining": int(remaining is not None)}
