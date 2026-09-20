"""Best-effort tracking for public share link views and downloads."""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import UTC, date, datetime, timedelta

from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from ulid import ULID

from api.dependencies import get_async_session_maker, get_redis
from api.middleware.rate_limit import client_ip_for_rate_limit
from api.observability.metrics import (
    share_downloads_total,
    share_event_queue_publish_errors_total,
    share_event_queue_publish_seconds,
    share_page_views_total,
)
from api.repositories.share_event_repo import ShareEventRepository
from database.models import RecordingModel
from database.share_models import ShareAccessEventModel, ShareEventType
from logger import get_logger

logger = get_logger("share.observability")

_VIEW_DEDUP_SECONDS = 30 * 60
_REDIS_VIEW_PREFIX = "share:view:"


async def enqueue_share_event_batch(payload: dict) -> None:
    """Publish an idempotent event batch without blocking the API event loop."""
    from api.tasks.share_events import persist_share_event_batch

    payload.setdefault("queued_at", time.time())
    started = time.perf_counter()
    try:
        # A failed broker publish is persisted by the caller; publisher retries
        # would only hold the public request open before that fallback runs.
        await asyncio.to_thread(persist_share_event_batch.apply_async, kwargs={"payload": payload}, retry=False)
    except Exception:
        share_event_queue_publish_errors_total.inc()
        raise
    finally:
        share_event_queue_publish_seconds.observe(time.perf_counter() - started)


def visitor_key_for_request(subject: str, request: Request) -> str:
    """Stable anonymous key for deduplicating page views (no raw IP stored)."""
    today = datetime.now(UTC).date().isoformat()
    ua = request.headers.get("user-agent") or ""
    ip = client_ip_for_rate_limit(request)
    raw = f"{subject}:{ip}:{ua}:{today}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def _channel_id_from_from_param(
    session,
    request: Request | None,
    *,
    owner_user_id: str | None,
    recording_id: int | None = None,
    playlist_id: int | None = None,
) -> int | None:
    raw = (request.query_params.get("from") or "").strip().lower() if request is not None else ""
    return await _channel_id_from_slug(
        session,
        raw,
        owner_user_id=owner_user_id,
        recording_id=recording_id,
        playlist_id=playlist_id,
    )


async def _channel_id_from_slug(
    session,
    raw: str | None,
    *,
    owner_user_id: str | None,
    recording_id: int | None = None,
    playlist_id: int | None = None,
) -> int | None:
    raw = (raw or "").strip().lower()
    if not raw:
        return None
    from api.repositories.channel_repo import ChannelRepository
    from database.channel_models import ChannelPlaylistModel, ChannelVideoModel
    from database.playlist_models import PlaylistItemModel, PlaylistModel

    channel = await ChannelRepository(session).get_by_slug(raw)
    if channel is None or not channel.share_enabled or channel.user_id != owner_user_id:
        return None
    if playlist_id is not None:
        membership = await session.scalar(
            select(ChannelPlaylistModel.id).where(
                ChannelPlaylistModel.channel_id == channel.id,
                ChannelPlaylistModel.playlist_id == playlist_id,
            )
        )
        return channel.id if membership is not None else None
    if recording_id is not None:
        direct = await session.scalar(
            select(ChannelVideoModel.id).where(
                ChannelVideoModel.channel_id == channel.id,
                ChannelVideoModel.recording_id == recording_id,
            )
        )
        if direct is not None:
            return channel.id
        via_playlist = await session.scalar(
            select(ChannelPlaylistModel.id)
            .join(PlaylistModel, PlaylistModel.id == ChannelPlaylistModel.playlist_id)
            .join(PlaylistItemModel, PlaylistItemModel.playlist_id == PlaylistModel.id)
            .where(
                ChannelPlaylistModel.channel_id == channel.id,
                PlaylistItemModel.recording_id == recording_id,
                PlaylistModel.user_id == owner_user_id,
                PlaylistModel.share_enabled.is_(True),
                PlaylistModel.share_token.is_not(None),
            )
            .limit(1)
        )
        return channel.id if via_playlist is not None else None
    return None


def fill_daily_series(
    aggregates: list[tuple[datetime, int, int]],
    *,
    days: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[tuple[date, int, int]]:
    """Return consecutive calendar days with zero-filled gaps."""
    counts: dict[date, tuple[int, int]] = {}
    for day_dt, views, downloads in aggregates:
        counts[day_dt.date()] = (views, downloads)

    if from_date is not None and to_date is not None:
        start, end = from_date, to_date
    elif days is not None:
        end = datetime.now(UTC).date()
        start = end - timedelta(days=days - 1)
    else:
        raise ValueError("fill_daily_series requires days or from_date/to_date")

    series: list[tuple[date, int, int]] = []
    current = start
    while current <= end:
        views, downloads = counts.get(current, (0, 0))
        series.append((current, views, downloads))
        current += timedelta(days=1)
    return series


def fill_daily_metrics(
    metrics_by_date: dict[date, dict[str, float | int | None]],
    *,
    from_date: date,
    to_date: date,
    metric_keys: tuple[str, ...],
) -> list[dict[str, date | float | int | None]]:
    """Zero-fill consecutive calendar days for the given metric keys."""
    series: list[dict[str, date | float | int | None]] = []
    current = from_date
    while current <= to_date:
        row: dict[str, date | float | int | None] = {"date": current}
        day_metrics = metrics_by_date.get(current, {})
        for key in metric_keys:
            row[key] = day_metrics.get(key, 0)
        series.append(row)
        current += timedelta(days=1)
    return series


class ShareObservabilityService:
    """Record share analytics without blocking or failing public endpoints."""

    async def record_page_view(
        self, recording: RecordingModel, request: Request, *, playlist_id: int | None = None
    ) -> bool:
        """Return True when a new view was counted."""
        if not recording.user_id:
            return False

        visitor_key = visitor_key_for_request(f"recording:{recording.id}", request)
        redis_key = f"{_REDIS_VIEW_PREFIX}{recording.id}:{visitor_key}"

        redis_available = True
        try:
            redis = await get_redis()
            inserted = await redis.set(redis_key, "1", nx=True, ex=_VIEW_DEDUP_SECONDS)
            if not inserted:
                return False
        except Exception as exc:
            redis_available = False
            logger.warning("Share view Redis dedup failed, falling back to DB: {}", exc)
            session_maker = get_async_session_maker()
            async with session_maker() as session:
                repo = ShareEventRepository(session)
                if await repo.has_recent_page_view(recording.id, visitor_key):
                    return False

        event = {
            "id": str(ULID()),
            "recording_id": recording.id,
            "owner_user_id": recording.user_id,
            "event_type": ShareEventType.PAGE_VIEW,
            "visitor_key": visitor_key,
            "playlist_id": playlist_id,
            "from_slug": request.query_params.get("from"),
        }
        try:
            if not redis_available:
                raise RuntimeError("Redis deduplication unavailable")
            await enqueue_share_event_batch({"access_events": [event]})
        except Exception as exc:
            logger.warning("Share view queue failed, persisting synchronously: {}", exc)
            persisted = await self._persist_event(
                recording,
                event_type=ShareEventType.PAGE_VIEW,
                visitor_key=visitor_key,
                increment_views=True,
                request=request,
                playlist_id=playlist_id,
                event_id=str(event["id"]),
            )
            if not persisted:
                if redis_available:
                    try:
                        redis = await get_redis()
                        await redis.delete(redis_key)
                    except Exception as cleanup_exc:
                        logger.warning("Share view Redis cleanup failed: {}", cleanup_exc)
                return False

        share_page_views_total.inc()
        logger.info(
            "share_event | recording_id={} | type=page_view | view_count={}",
            recording.id,
            recording.share_view_count + 1,
        )
        return True

    async def record_surface_view(
        self,
        *,
        owner_user_id: str,
        request: Request,
        playlist_id: int | None = None,
        channel_id: int | None = None,
    ) -> bool:
        if not owner_user_id or (playlist_id is None and channel_id is None):
            return False
        subject = f"playlist:{playlist_id}" if playlist_id is not None else f"channel:{channel_id}"
        visitor_key = visitor_key_for_request(subject, request)
        redis_key = f"{_REDIS_VIEW_PREFIX}{subject}:{visitor_key}"
        redis_available = True
        try:
            redis = await get_redis()
            inserted = await redis.set(redis_key, "1", nx=True, ex=_VIEW_DEDUP_SECONDS)
            if not inserted:
                return False
        except Exception as exc:
            redis_available = False
            logger.warning("Share view Redis dedup failed, falling back to DB: {}", exc)

        event = {
            "id": str(ULID()),
            "owner_user_id": owner_user_id,
            "event_type": ShareEventType.PAGE_VIEW,
            "visitor_key": visitor_key,
            "playlist_id": playlist_id,
            "channel_id": channel_id,
        }
        try:
            if not redis_available:
                raise RuntimeError("Redis deduplication unavailable")
            await enqueue_share_event_batch({"access_events": [event]})
        except Exception as exc:
            logger.info("share surface queue failed; falling back to DB: {!r}", exc)
            session_maker = get_async_session_maker()
            try:
                async with session_maker() as session:
                    if not redis_available:
                        recent = await session.scalar(
                            select(ShareAccessEventModel.id)
                            .where(
                                ShareAccessEventModel.owner_user_id == owner_user_id,
                                ShareAccessEventModel.event_type == ShareEventType.PAGE_VIEW,
                                ShareAccessEventModel.visitor_key == visitor_key,
                                ShareAccessEventModel.playlist_id == playlist_id,
                                ShareAccessEventModel.channel_id == channel_id,
                                ShareAccessEventModel.created_at
                                >= datetime.now(UTC) - timedelta(seconds=_VIEW_DEDUP_SECONDS),
                            )
                            .limit(1)
                        )
                        if recent is not None:
                            return False
                    await session.execute(
                        insert(ShareAccessEventModel)
                        .values(
                            id=event["id"],
                            owner_user_id=owner_user_id,
                            event_type=ShareEventType.PAGE_VIEW,
                            visitor_key=visitor_key,
                            playlist_id=playlist_id,
                            channel_id=channel_id,
                        )
                        .on_conflict_do_nothing(index_elements=["id"])
                    )
                    await session.commit()
            except Exception as persist_exc:
                logger.info("share surface persist failed (ignored): {!r}", persist_exc)
                if redis_available:
                    try:
                        redis = await get_redis()
                        await redis.delete(redis_key)
                    except Exception as cleanup_exc:
                        logger.warning("Share surface Redis cleanup failed: {}", cleanup_exc)
                return False
        share_page_views_total.inc()
        return True

    async def record_download(self, recording: RecordingModel, request: Request, artifact_type: str) -> None:
        if not recording.user_id:
            return

        visitor_key = visitor_key_for_request(f"recording:{recording.id}", request)
        event = {
            "id": str(ULID()),
            "recording_id": recording.id,
            "owner_user_id": recording.user_id,
            "event_type": ShareEventType.FILE_DOWNLOAD,
            "visitor_key": visitor_key,
            "artifact_type": artifact_type,
            "from_slug": request.query_params.get("from"),
        }
        try:
            await enqueue_share_event_batch({"access_events": [event]})
        except Exception as exc:
            logger.warning("Share download queue failed, persisting synchronously: {}", exc)
            persisted = await self._persist_event(
                recording,
                event_type=ShareEventType.FILE_DOWNLOAD,
                visitor_key=visitor_key,
                artifact_type=artifact_type,
                increment_downloads=True,
                request=request,
                event_id=str(event["id"]),
            )
            if not persisted:
                return

        share_downloads_total.labels(artifact_type=artifact_type).inc()
        logger.info(
            "share_event | recording_id={} | type=file_download | artifact={}",
            recording.id,
            artifact_type,
        )

    async def _persist_event(
        self,
        recording: RecordingModel,
        *,
        event_type: str,
        visitor_key: str,
        artifact_type: str | None = None,
        increment_views: bool = False,
        increment_downloads: bool = False,
        request: Request | None = None,
        playlist_id: int | None = None,
        event_id: str | None = None,
    ) -> bool:
        session_maker = get_async_session_maker()
        try:
            async with session_maker() as session:
                channel_id = await _channel_id_from_from_param(
                    session,
                    request,
                    owner_user_id=recording.user_id,
                    playlist_id=playlist_id,
                    recording_id=recording.id if playlist_id is None else None,
                )
                inserted = await session.scalar(
                    insert(ShareAccessEventModel)
                    .values(
                        id=event_id or str(ULID()),
                        recording_id=recording.id,
                        playlist_id=playlist_id,
                        owner_user_id=recording.user_id,
                        event_type=event_type,
                        visitor_key=visitor_key,
                        artifact_type=artifact_type,
                        channel_id=channel_id,
                    )
                    .on_conflict_do_nothing(index_elements=["id"])
                    .returning(ShareAccessEventModel.id)
                )

                now = datetime.now(UTC)
                if inserted is not None and increment_views:
                    await session.execute(
                        update(RecordingModel)
                        .where(RecordingModel.id == recording.id)
                        .values(
                            share_view_count=RecordingModel.share_view_count + 1,
                            share_last_viewed_at=now,
                        )
                    )
                if inserted is not None and increment_downloads:
                    await session.execute(
                        update(RecordingModel)
                        .where(RecordingModel.id == recording.id)
                        .values(
                            share_download_count=RecordingModel.share_download_count + 1,
                            share_last_downloaded_at=now,
                        )
                    )

                await session.commit()
            return True
        except Exception as exc:
            logger.info("share event persist failed (ignored): {!r}", exc)
            return False

    @staticmethod
    async def platform_totals() -> tuple[int, int, int]:
        """Return (total_views, total_downloads, active_share_links)."""
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            total_views = await session.scalar(select(func.coalesce(func.sum(RecordingModel.share_view_count), 0))) or 0
            total_downloads = (
                await session.scalar(select(func.coalesce(func.sum(RecordingModel.share_download_count), 0))) or 0
            )
            active_links = (
                await session.scalar(
                    select(func.count())
                    .select_from(RecordingModel)
                    .where(RecordingModel.share_token.is_not(None), RecordingModel.share_enabled.is_(True))
                )
                or 0
            )
            return int(total_views), int(total_downloads), int(active_links)


async def build_catalog_analytics(
    session,
    *,
    recording_ids: list[int],
    from_date: date,
    to_date: date,
    from_dt: datetime,
    to_dt: datetime,
    owner_user_id: str,
    channel_id: int | None = None,
    playlist_id: int | None = None,
):
    from api.schemas.share import ShareAnalyticsResponse, ShareDailyPoint, ShareStatsSummary

    repo = ShareEventRepository(session)
    traffic = await repo.daily_aggregates_for_recordings(recording_ids, from_dt=from_dt, to_dt=to_dt)
    opens_rows = await repo.daily_opens(channel_id=channel_id, playlist_id=playlist_id, from_dt=from_dt, to_dt=to_dt)
    traffic_map = {day.date(): (views, downloads) for day, views, downloads in traffic}
    opens_map = {day.date(): n for day, n in opens_rows}
    daily: list[ShareDailyPoint] = []
    current = from_date
    while current <= to_date:
        views, downloads = traffic_map.get(current, (0, 0))
        daily.append(ShareDailyPoint(date=current, views=views, downloads=downloads, opens=opens_map.get(current, 0)))
        current += timedelta(days=1)
    view_total, download_total = await repo.totals_for_recordings(recording_ids)
    open_total = await repo.total_opens(channel_id=channel_id, playlist_id=playlist_id)
    downloads_by_type = await repo.downloads_by_type_for_recordings(recording_ids, from_dt=from_dt, to_dt=to_dt)
    from api.services.share_engagement import ShareEngagementService

    engagement_svc = ShareEngagementService()
    engagement = await engagement_svc.build_summary(
        session,
        from_dt=from_dt,
        to_dt=to_dt,
        recording_ids=recording_ids,
        playlist_id=playlist_id,
        include_playlist_navigation=playlist_id is not None,
        owner_user_id=owner_user_id,
    )
    return ShareAnalyticsResponse(
        summary=ShareStatsSummary(
            view_count=view_total,
            download_count=download_total,
            open_count=open_total,
        ),
        daily=daily,
        downloads_by_type=downloads_by_type,
        engagement=engagement,
    )
