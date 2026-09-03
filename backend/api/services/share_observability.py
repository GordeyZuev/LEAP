"""Best-effort tracking for public share link views and downloads."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta

from fastapi import Request
from sqlalchemy import func, select, update

from api.dependencies import get_async_session_maker, get_redis
from api.observability.metrics import share_downloads_total, share_page_views_total
from api.repositories.share_event_repo import ShareEventRepository
from database.models import RecordingModel
from database.share_models import ShareEventType
from logger import get_logger

logger = get_logger("share.observability")

_VIEW_DEDUP_SECONDS = 30 * 60
_REDIS_VIEW_PREFIX = "share:view:"


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def visitor_key_for_request(recording_id: int, request: Request) -> str:
    """Stable anonymous key for deduplicating page views (no raw IP stored)."""
    today = datetime.now(UTC).date().isoformat()
    ua = request.headers.get("user-agent") or ""
    ip = _client_ip(request)
    raw = f"{recording_id}:{ip}:{ua}:{today}"
    return hashlib.sha256(raw.encode()).hexdigest()


def fill_daily_series(
    aggregates: list[tuple[datetime, int, int]],
    *,
    days: int,
) -> list[tuple[date, int, int]]:
    """Return consecutive calendar days with zero-filled gaps."""
    counts: dict[date, tuple[int, int]] = {}
    for day_dt, views, downloads in aggregates:
        counts[day_dt.date()] = (views, downloads)

    end = datetime.now(UTC).date()
    start = end - timedelta(days=days - 1)
    series: list[tuple[date, int, int]] = []
    current = start
    while current <= end:
        views, downloads = counts.get(current, (0, 0))
        series.append((current, views, downloads))
        current += timedelta(days=1)
    return series


class ShareObservabilityService:
    """Record share analytics without blocking or failing public endpoints."""

    async def record_page_view(self, recording: RecordingModel, request: Request) -> bool:
        """Return True when a new view was counted."""
        if not recording.user_id:
            return False

        visitor_key = visitor_key_for_request(recording.id, request)
        redis_key = f"{_REDIS_VIEW_PREFIX}{recording.id}:{visitor_key}"

        try:
            redis = await get_redis()
            inserted = await redis.set(redis_key, "1", nx=True, ex=_VIEW_DEDUP_SECONDS)
            if not inserted:
                return False
        except Exception as exc:
            logger.warning("Share view Redis dedup failed, falling back to DB: {}", exc)
            session_maker = get_async_session_maker()
            async with session_maker() as session:
                repo = ShareEventRepository(session)
                if await repo.has_recent_page_view(recording.id, visitor_key):
                    return False

        persisted = await self._persist_event(
            recording,
            event_type=ShareEventType.PAGE_VIEW,
            visitor_key=visitor_key,
            increment_views=True,
        )
        if not persisted:
            return False

        share_page_views_total.inc()
        logger.info(
            "share_event | recording_id={} | type=page_view | view_count={}",
            recording.id,
            recording.share_view_count + 1,
        )
        return True

    async def record_download(self, recording: RecordingModel, request: Request, artifact_type: str) -> None:
        if not recording.user_id:
            return

        visitor_key = visitor_key_for_request(recording.id, request)
        persisted = await self._persist_event(
            recording,
            event_type=ShareEventType.FILE_DOWNLOAD,
            visitor_key=visitor_key,
            artifact_type=artifact_type,
            increment_downloads=True,
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
    ) -> bool:
        session_maker = get_async_session_maker()
        try:
            async with session_maker() as session:
                repo = ShareEventRepository(session)
                await repo.create(
                    recording_id=recording.id,
                    owner_user_id=recording.user_id,
                    event_type=event_type,
                    visitor_key=visitor_key,
                    artifact_type=artifact_type,
                )

                now = datetime.now(UTC)
                if increment_views:
                    await session.execute(
                        update(RecordingModel)
                        .where(RecordingModel.id == recording.id)
                        .values(
                            share_view_count=RecordingModel.share_view_count + 1,
                            share_last_viewed_at=now,
                        )
                    )
                if increment_downloads:
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
            logger.warning("share event persist failed (ignored): {!r}", exc)
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
                    select(func.count()).select_from(RecordingModel).where(RecordingModel.share_token.is_not(None))
                )
                or 0
            )
            return int(total_views), int(total_downloads), int(active_links)
