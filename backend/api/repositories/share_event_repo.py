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
        recording_id: int,
        owner_user_id: str,
        event_type: str,
        visitor_key: str = "",
        artifact_type: str | None = None,
    ) -> ShareAccessEventModel:
        event = ShareAccessEventModel(
            recording_id=recording_id,
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
        days: int,
    ) -> list[tuple[datetime, int, int]]:
        since = datetime.now(UTC) - timedelta(days=days)
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
        days: int,
    ) -> dict[str, int]:
        since = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(
            select(ShareAccessEventModel.artifact_type, func.count())
            .where(
                ShareAccessEventModel.recording_id == recording_id,
                ShareAccessEventModel.event_type == ShareEventType.FILE_DOWNLOAD,
                ShareAccessEventModel.created_at >= since,
                ShareAccessEventModel.artifact_type.is_not(None),
            )
            .group_by(ShareAccessEventModel.artifact_type)
        )
        return {str(artifact_type): int(count) for artifact_type, count in result.all()}
