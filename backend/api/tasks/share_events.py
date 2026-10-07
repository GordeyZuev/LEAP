"""Durable persistence for high-volume public share analytics events."""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

from api.celery_app import celery_app
from api.dependencies import get_async_session_maker
from api.observability.metrics import (
    increment_metric,
    observe_metric,
    share_event_persisted_total,
    share_event_queue_lag_seconds,
)
from api.services.share_observability import _channel_id_from_slug
from database.models import RecordingModel
from database.share_models import ShareAccessEventModel, ShareEngagementEventModel
from logger import get_logger

logger = get_logger("share.events")


@celery_app.task(
    bind=True,
    name="api.tasks.share_events.persist_batch",
    max_retries=8,
    default_retry_delay=2,
    acks_late=True,
    reject_on_worker_lost=True,
    ignore_result=True,
)
def persist_share_event_batch(self, payload: dict) -> dict:
    """Insert an event batch idempotently; Celery retries transient DB failures."""
    try:
        return asyncio.run(_persist_share_event_batch(payload))
    except Exception as exc:
        logger.warning("Share event persistence failed; retrying: {}", exc)
        raise self.retry(exc=exc, countdown=min(60, 2 ** min(self.request.retries, 6)))


async def _persist_share_event_batch(payload: dict) -> dict:
    queued_at = payload.get("queued_at")
    session_maker = get_async_session_maker()
    access_events = payload.get("access_events") or []
    engagement_events = payload.get("engagement_events") or []
    now = datetime.now(UTC)
    event_created_at = datetime.fromtimestamp(queued_at, UTC) if isinstance(queued_at, (int, float)) else now
    inserted_rows = []
    async with session_maker() as session:
        if access_events:
            rows = []
            for event in access_events:
                raw_from = event.get("from_slug")
                channel_id = event.get("channel_id")
                if raw_from:
                    channel_id = await _channel_id_from_slug(
                        session,
                        raw_from,
                        owner_user_id=event.get("owner_user_id"),
                        recording_id=event.get("recording_id"),
                        playlist_id=event.get("playlist_id"),
                    )
                values = {
                    "id": event["id"],
                    "recording_id": event.get("recording_id"),
                    "playlist_id": event.get("playlist_id"),
                    "channel_id": channel_id,
                    "owner_user_id": event["owner_user_id"],
                    "event_type": event["event_type"],
                    "visitor_key": event["visitor_key"],
                    "artifact_type": event.get("artifact_type"),
                    "created_at": event_created_at,
                }
                rows.append(values)
            inserted = await session.execute(
                insert(ShareAccessEventModel)
                .values(rows)
                .on_conflict_do_nothing(index_elements=["id"])
                .returning(ShareAccessEventModel.recording_id, ShareAccessEventModel.event_type)
            )
            inserted_rows = inserted.all()
            view_counts = Counter(
                int(rid) for rid, event_type in inserted_rows if rid is not None and event_type == "page_view"
            )
            download_counts = Counter(
                int(rid) for rid, event_type in inserted_rows if rid is not None and event_type == "file_download"
            )
            for recording_id in view_counts.keys() | download_counts.keys():
                values = {}
                if recording_id in view_counts:
                    values["share_view_count"] = RecordingModel.share_view_count + view_counts[recording_id]
                    values["share_last_viewed_at"] = now
                if recording_id in download_counts:
                    values["share_download_count"] = RecordingModel.share_download_count + download_counts[recording_id]
                    values["share_last_downloaded_at"] = now
                await session.execute(update(RecordingModel).where(RecordingModel.id == recording_id).values(**values))
        if engagement_events:
            inserted_engagement = await session.execute(
                insert(ShareEngagementEventModel)
                .values([{**event, "created_at": event_created_at} for event in engagement_events])
                .on_conflict_do_nothing(index_elements=["id"])
                .returning(ShareEngagementEventModel.id)
            )
            engagement_inserted_count = len(inserted_engagement.all())
        else:
            engagement_inserted_count = 0
        await session.commit()
    if isinstance(queued_at, (int, float)):
        observe_metric(share_event_queue_lag_seconds, max(0.0, time.time() - float(queued_at)))
    for _ in inserted_rows:
        increment_metric(share_event_persisted_total, kind="access")
    for _ in range(engagement_inserted_count):
        increment_metric(share_event_persisted_total, kind="engagement")
    return {"access_events": len(access_events), "engagement_events": len(engagement_events)}
