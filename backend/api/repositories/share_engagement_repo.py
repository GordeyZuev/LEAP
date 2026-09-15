"""Repository for share_engagement_events aggregates and inserts."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.share_models import (
    ShareAccessEventModel,
    ShareEngagementEventModel,
    ShareEngagementEventName,
    ShareEventType,
)


class ShareEngagementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _owner_cond(owner_user_id: str | None) -> list:
        if not owner_user_id:
            return []
        return [ShareEngagementEventModel.owner_user_id == owner_user_id]

    async def insert_many(self, rows: list[ShareEngagementEventModel]) -> None:
        if not rows:
            return
        self.session.add_all(rows)
        await self.session.flush()

    async def count_page_views_in_range(
        self,
        *,
        recording_ids: list[int],
        from_dt: datetime,
        to_dt: datetime,
    ) -> int:
        if not recording_ids:
            return 0
        result = await self.session.execute(
            select(func.count())
            .select_from(ShareAccessEventModel)
            .where(
                ShareAccessEventModel.recording_id.in_(recording_ids),
                ShareAccessEventModel.event_type == ShareEventType.PAGE_VIEW,
                ShareAccessEventModel.created_at >= from_dt,
                ShareAccessEventModel.created_at <= to_dt,
            )
        )
        return int(result.scalar_one() or 0)

    async def count_event(
        self,
        event_name: str,
        *,
        recording_ids: list[int] | None = None,
        recording_id: int | None = None,
        playlist_id: int | None = None,
        from_dt: datetime,
        to_dt: datetime,
        owner_user_id: str | None = None,
    ) -> int:
        cond = [
            ShareEngagementEventModel.event_name == event_name,
            ShareEngagementEventModel.created_at >= from_dt,
            ShareEngagementEventModel.created_at <= to_dt,
            *self._owner_cond(owner_user_id),
        ]
        if recording_id is not None:
            cond.append(ShareEngagementEventModel.recording_id == recording_id)
        elif recording_ids is not None:
            if not recording_ids:
                return 0
            cond.append(ShareEngagementEventModel.recording_id.in_(recording_ids))
        if playlist_id is not None:
            cond.append(ShareEngagementEventModel.playlist_id == playlist_id)
        result = await self.session.execute(select(func.count()).select_from(ShareEngagementEventModel).where(*cond))
        return int(result.scalar_one() or 0)

    async def chapter_seeks_top(
        self,
        *,
        recording_ids: list[int] | None = None,
        recording_id: int | None = None,
        from_dt: datetime,
        to_dt: datetime,
        limit: int = 5,
        owner_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        cond = [
            ShareEngagementEventModel.event_name == ShareEngagementEventName.CHAPTER_SEEK,
            ShareEngagementEventModel.created_at >= from_dt,
            ShareEngagementEventModel.created_at <= to_dt,
            *self._owner_cond(owner_user_id),
        ]
        if recording_id is not None:
            cond.append(ShareEngagementEventModel.recording_id == recording_id)
        elif recording_ids is not None:
            if not recording_ids:
                return []
            cond.append(ShareEngagementEventModel.recording_id.in_(recording_ids))

        label_col = ShareEngagementEventModel.payload["label"].astext
        source_col = ShareEngagementEventModel.payload["source"].astext
        result = await self.session.execute(
            select(label_col, source_col, func.count()).where(*cond).group_by(label_col, source_col)
        )
        by_label: dict[str, dict[str, int]] = defaultdict(
            lambda: {"marker": 0, "sidebar": 0, "transcript": 0, "total": 0}
        )
        for label, source, count in result.all():
            if not label:
                continue
            n = int(count or 0)
            entry = by_label[label]
            entry["total"] += n
            if source in ("marker", "sidebar", "transcript"):
                entry[source] += n
        ranked = sorted(by_label.items(), key=lambda item: item[1]["total"], reverse=True)[:limit]
        return [
            {
                "label": label,
                "count": stats["total"],
                "by_source": {
                    "marker": stats["marker"],
                    "sidebar": stats["sidebar"],
                    "transcript": stats["transcript"],
                },
            }
            for label, stats in ranked
        ]

    async def playlist_navigate_by_from(
        self,
        playlist_id: int,
        *,
        from_dt: datetime,
        to_dt: datetime,
        owner_user_id: str | None = None,
    ) -> dict[str, int]:
        source_col = ShareEngagementEventModel.payload["from"].astext
        result = await self.session.execute(
            select(source_col, func.count())
            .where(
                ShareEngagementEventModel.event_name == ShareEngagementEventName.PLAYLIST_NAVIGATE,
                ShareEngagementEventModel.playlist_id == playlist_id,
                ShareEngagementEventModel.created_at >= from_dt,
                ShareEngagementEventModel.created_at <= to_dt,
                *self._owner_cond(owner_user_id),
            )
            .group_by(source_col)
        )
        out: dict[str, int] = {"sidebar": 0, "landing": 0, "autoplay": 0, "url": 0}
        for source, count in result.all():
            if source in out:
                out[source] = int(count or 0)
        return out

    async def watch_exit_median_ratio(
        self,
        *,
        recording_ids: list[int] | None = None,
        recording_id: int | None = None,
        from_dt: datetime,
        to_dt: datetime,
        owner_user_id: str | None = None,
    ) -> float | None:
        cond = [
            ShareEngagementEventModel.event_name == ShareEngagementEventName.WATCH_EXIT,
            ShareEngagementEventModel.created_at >= from_dt,
            ShareEngagementEventModel.created_at <= to_dt,
            *self._owner_cond(owner_user_id),
        ]
        if recording_id is not None:
            cond.append(ShareEngagementEventModel.recording_id == recording_id)
        elif recording_ids is not None:
            if not recording_ids:
                return None
            cond.append(ShareEngagementEventModel.recording_id.in_(recording_ids))

        pos = cast(ShareEngagementEventModel.payload["position_sec"].astext, Float)
        dur = cast(ShareEngagementEventModel.payload["duration_sec"].astext, Float)
        ratio = pos / func.nullif(dur, 0)
        result = await self.session.execute(select(func.percentile_cont(0.5).within_group(ratio)).where(*cond, dur > 0))
        value = result.scalar_one_or_none()
        if value is None:
            return None
        return float(value)
