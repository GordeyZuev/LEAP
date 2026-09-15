"""Repository for share_access_events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.share_models import ShareAccessEventModel, ShareEventType


class ShareEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        owner_user_id: str,
        event_type: str,
        recording_id: int | None = None,
        playlist_id: int | None = None,
        channel_id: int | None = None,
        visitor_key: str = "",
        artifact_type: str | None = None,
    ) -> ShareAccessEventModel:
        event = ShareAccessEventModel(
            recording_id=recording_id,
            playlist_id=playlist_id,
            channel_id=channel_id,
            owner_user_id=owner_user_id,
            event_type=event_type,
            visitor_key=visitor_key,
            artifact_type=artifact_type,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def has_recent_page_view(
        self,
        recording_id: int,
        visitor_key: str,
        *,
        within_minutes: int = 30,
    ) -> bool:
        since = datetime.now(UTC) - timedelta(minutes=within_minutes)
        result = await self.session.execute(
            select(ShareAccessEventModel.id)
            .where(
                ShareAccessEventModel.recording_id == recording_id,
                ShareAccessEventModel.event_type == ShareEventType.PAGE_VIEW,
                ShareAccessEventModel.visitor_key == visitor_key,
                ShareAccessEventModel.created_at >= since,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def daily_aggregates(
        self,
        recording_id: int,
        *,
        days: int | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> list[tuple[datetime, int, int]]:
        if from_dt is not None and to_dt is not None:
            since = from_dt
            until = to_dt
        elif days is not None:
            since = datetime.now(UTC) - timedelta(days=days)
            until = datetime.now(UTC)
        else:
            raise ValueError("daily_aggregates requires days or from_dt/to_dt")

        day_col = func.date_trunc("day", ShareAccessEventModel.created_at).label("day")
        views_col = func.sum(case((ShareAccessEventModel.event_type == ShareEventType.PAGE_VIEW, 1), else_=0)).label(
            "views"
        )
        downloads_col = func.sum(
            case((ShareAccessEventModel.event_type == ShareEventType.FILE_DOWNLOAD, 1), else_=0)
        ).label("downloads")

        result = await self.session.execute(
            select(day_col, views_col, downloads_col)
            .where(
                ShareAccessEventModel.recording_id == recording_id,
                ShareAccessEventModel.created_at >= since,
                ShareAccessEventModel.created_at <= until,
            )
            .group_by(day_col)
            .order_by(day_col)
        )
        rows: list[tuple[datetime, int, int]] = []
        for day, views, downloads in result.all():
            rows.append((day, int(views or 0), int(downloads or 0)))
        return rows

    async def downloads_by_type(
        self,
        recording_id: int,
        *,
        days: int | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> dict[str, int]:
        if from_dt is not None and to_dt is not None:
            since = from_dt
            until = to_dt
        elif days is not None:
            since = datetime.now(UTC) - timedelta(days=days)
            until = datetime.now(UTC)
        else:
            raise ValueError("downloads_by_type requires days or from_dt/to_dt")

        result = await self.session.execute(
            select(ShareAccessEventModel.artifact_type, func.count())
            .where(
                ShareAccessEventModel.recording_id == recording_id,
                ShareAccessEventModel.event_type == ShareEventType.FILE_DOWNLOAD,
                ShareAccessEventModel.created_at >= since,
                ShareAccessEventModel.created_at <= until,
                ShareAccessEventModel.artifact_type.is_not(None),
            )
            .group_by(ShareAccessEventModel.artifact_type)
        )
        return {str(artifact_type): int(count) for artifact_type, count in result.all()}

    async def daily_opens(
        self,
        *,
        channel_id: int | None = None,
        playlist_id: int | None = None,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[tuple[datetime, int]]:
        cond = [
            ShareAccessEventModel.event_type == ShareEventType.PAGE_VIEW,
            ShareAccessEventModel.recording_id.is_(None),
            ShareAccessEventModel.created_at >= from_dt,
            ShareAccessEventModel.created_at <= to_dt,
        ]
        if channel_id is not None:
            cond.append(ShareAccessEventModel.channel_id == channel_id)
        if playlist_id is not None:
            cond.append(ShareAccessEventModel.playlist_id == playlist_id)
        day_col = func.date_trunc("day", ShareAccessEventModel.created_at).label("day")
        result = await self.session.execute(
            select(day_col, func.count()).where(*cond).group_by(day_col).order_by(day_col)
        )
        return [(day, int(n or 0)) for day, n in result.all()]

    async def daily_aggregates_for_recordings(
        self,
        recording_ids: list[int],
        *,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[tuple[datetime, int, int]]:
        if not recording_ids:
            return []
        day_col = func.date_trunc("day", ShareAccessEventModel.created_at).label("day")
        views_col = func.sum(case((ShareAccessEventModel.event_type == ShareEventType.PAGE_VIEW, 1), else_=0)).label(
            "views"
        )
        downloads_col = func.sum(
            case((ShareAccessEventModel.event_type == ShareEventType.FILE_DOWNLOAD, 1), else_=0)
        ).label("downloads")
        result = await self.session.execute(
            select(day_col, views_col, downloads_col)
            .where(
                ShareAccessEventModel.recording_id.in_(recording_ids),
                ShareAccessEventModel.created_at >= from_dt,
                ShareAccessEventModel.created_at <= to_dt,
            )
            .group_by(day_col)
            .order_by(day_col)
        )
        return [(day, int(views or 0), int(downloads or 0)) for day, views, downloads in result.all()]

    async def totals_for_recordings(self, recording_ids: list[int]) -> tuple[int, int]:
        if not recording_ids:
            return 0, 0
        result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(case((ShareAccessEventModel.event_type == ShareEventType.PAGE_VIEW, 1), else_=0)), 0
                ),
                func.coalesce(
                    func.sum(case((ShareAccessEventModel.event_type == ShareEventType.FILE_DOWNLOAD, 1), else_=0)), 0
                ),
            ).where(ShareAccessEventModel.recording_id.in_(recording_ids))
        )
        views, downloads = result.one()
        return int(views or 0), int(downloads or 0)

    async def total_opens(self, *, channel_id: int | None = None, playlist_id: int | None = None) -> int:
        cond = [
            ShareAccessEventModel.event_type == ShareEventType.PAGE_VIEW,
            ShareAccessEventModel.recording_id.is_(None),
        ]
        if channel_id is not None:
            cond.append(ShareAccessEventModel.channel_id == channel_id)
        if playlist_id is not None:
            cond.append(ShareAccessEventModel.playlist_id == playlist_id)
        result = await self.session.execute(select(func.count()).where(*cond))
        return int(result.scalar_one() or 0)
